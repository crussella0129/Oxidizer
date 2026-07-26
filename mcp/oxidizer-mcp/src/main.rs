//! Oxidizer MCP server — situational access to the Rust canon over stdio.
//!
//! Exposes the same retrieval surface as `scripts/oxidize.py` to any MCP
//! client, which is what makes the skill agent-agnostic: an editor or agent
//! that speaks MCP gets the routed, budgeted canon without knowing anything
//! about Claude skills or having Python installed.
//!
//! Run with the corpus discoverable via `--corpus`, `OXIDIZER_CORPUS`, or the
//! default `corpus/` directory at the repository root.

mod corpus;

use std::path::PathBuf;
use std::sync::Arc;

use corpus::{Corpus, Doc, budget_text, estimate_tokens, split_sections};
use rmcp::{
    ErrorData as McpError, ServerHandler, ServiceExt,
    handler::server::{router::tool::ToolRouter, wrapper::Parameters},
    model::*,
    schemars, tool, tool_handler, tool_router,
    transport::stdio,
};
use serde::Deserialize;

const DEFAULT_BUDGET: usize = 2000;

fn default_budget() -> usize {
    DEFAULT_BUDGET
}

fn default_limit() -> usize {
    5
}

// -- tool parameter types --------------------------------------------------

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct RouteArgs {
    /// The user's Rust question, in their own words.
    pub question: String,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct SearchArgs {
    /// What to look for. Prefer distinctive terms over full sentences.
    pub query: String,
    /// Restrict to these sources, e.g. ["book"] or ["std"]. Empty means all.
    #[serde(default)]
    pub sources: Vec<String>,
    /// Maximum hits to return.
    #[serde(default = "default_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct ShowArgs {
    /// Document id as `source/id`, e.g. `book/ch04-01-what-is-ownership`.
    pub doc_id: String,
    /// Return only the section with this heading, if given.
    #[serde(default)]
    pub section: Option<String>,
    /// Token budget for the returned text.
    #[serde(default = "default_budget")]
    pub max_tokens: usize,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct ExplainArgs {
    /// A compiler error code such as `E0502`.
    pub code: String,
    #[serde(default = "default_budget")]
    pub max_tokens: usize,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct ApiArgs {
    /// An item or member path: `Vec`, `Vec::retain`, `std::vec::Vec::retain`.
    pub path: String,
    #[serde(default = "default_budget")]
    pub max_tokens: usize,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct LintArgs {
    /// A lint name, with or without the `clippy::` prefix.
    pub name: String,
    #[serde(default = "default_budget")]
    pub max_tokens: usize,
}

// -- routing ---------------------------------------------------------------

struct Rule {
    domain: &'static str,
    sources: &'static [&'static str],
    why: &'static str,
    triggers: &'static [&'static str],
}

/// Kept in step with `ROUTING` in `oxidize.py` and with `domains/*/CONTEXT.md`.
/// Substring triggers rather than regexes: the routing decision is coarse by
/// design, and a dependency-free match keeps the two implementations aligned.
const ROUTING: &[Rule] = &[
    Rule {
        domain: "01_diagnose",
        sources: &["error-index", "book", "reference", "nomicon"],
        why: "A compile actually failed; the error index is authoritative.",
        triggers: &[
            "borrow", "borrowck", "does not live long enough", "cannot move out",
            "moved value", "lifetime", "compile error", "compiler error",
            "won't compile", "doesn't compile", "error[", "mismatched types",
            "type mismatch", "trait bound", "not satisfied",
        ],
    },
    Rule {
        domain: "02_learn",
        sources: &["book", "brown-book", "rust-by-example"],
        why: "Conceptual understanding; the Book teaches, the Reference does not.",
        triggers: &[
            "explain", "what is", "how does", "how do", "learn", "understand",
            "teach", "difference between", "when should i", "concept",
            "new to rust", "intro",
        ],
    },
    Rule {
        domain: "03_api",
        sources: &["std", "core", "alloc"],
        why: "API surface question; answer from signatures, not prose.",
        triggers: &[
            "std::", "signature", "method", "which function", "api",
            "return type", "vec", "hashmap", "option", "result", "string",
            "iterator",
        ],
    },
    Rule {
        domain: "04_spec",
        sources: &["reference", "edition-guide"],
        why: "Normative question; only the Reference is binding.",
        triggers: &[
            "is it legal", "guarantee", "spec", "specification", "well-defined",
            "well defined", "semantics", "drop order", "coercion", "precedence",
            "edition",
        ],
    },
    Rule {
        domain: "05_unsafe",
        sources: &["nomicon", "reference", "std"],
        why: "Unsafe code has invariants the Book does not cover.",
        triggers: &[
            "unsafe", "undefined behavior", "undefined behaviour", "ffi",
            "raw pointer", "transmute", "variance", "phantomdata", "send",
            "sync", "maybeuninit", "extern \"c\"", "miri",
        ],
    },
    Rule {
        domain: "06_idiom",
        sources: &["lints", "style-guide", "cargo", "book"],
        why: "Style/idiom question; clippy encodes the community consensus.",
        triggers: &[
            "idiomatic", "clippy", "lint", "refactor", "cleaner", "best practice",
            "convention", "naming", "cargo.toml", "feature flag", "workspace",
        ],
    },
    Rule {
        domain: "07_migrate",
        sources: &["crp-phrasebook", "book", "nomicon", "reference"],
        why: "Translation task; map source-language idiom to Rust idiom.",
        triggers: &[
            "c++", "port", "porting", "migrat", "rewrite", "equivalent of",
            "coming from", "shared_ptr", "unique_ptr", "std::vector", "raii",
        ],
    },
];

// -- server ----------------------------------------------------------------

#[derive(Clone)]
struct Oxidizer {
    corpus: Arc<Corpus>,
    // Read by the code `#[tool_handler]` generates, which dead-code analysis
    // does not see through.
    #[allow(dead_code)]
    tool_router: ToolRouter<Oxidizer>,
}

fn text_result(body: String) -> Result<CallToolResult, McpError> {
    Ok(CallToolResult::success(vec![ContentBlock::text(body)]))
}

fn provenance(doc: &Doc, returned: usize, truncated: bool) -> String {
    let mut s = format!("\n\nSource: {} ({})", doc.url, doc.source);
    if truncated {
        s.push_str(&format!(
            "\n[truncated: returned ~{returned} of ~{} tokens — raise max_tokens \
             or request a single section]",
            doc.tokens
        ));
    }
    s
}

#[tool_router]
impl Oxidizer {
    fn new(corpus: Arc<Corpus>) -> Self {
        Self { corpus, tool_router: Self::tool_router() }
    }

    #[tool(
        name = "oxidizer_route",
        description = "Decide which Rust knowledge domain a question belongs to \
                       before retrieving anything. Returns the domain contract to \
                       load and the sources that are authoritative for it. Use \
                       this first when unsure where to look."
    )]
    fn route(&self, Parameters(args): Parameters<RouteArgs>) -> Result<CallToolResult, McpError> {
        let q = args.question.to_lowercase();
        let mut scored: Vec<(usize, &Rule)> = ROUTING
            .iter()
            .map(|r| (r.triggers.iter().filter(|t| q.contains(**t)).count(), r))
            .filter(|(n, _)| *n > 0)
            .collect();
        scored.sort_by_key(|(n, _)| std::cmp::Reverse(*n));

        let picked: Vec<&Rule> = if scored.is_empty() {
            vec![ROUTING.iter().find(|r| r.domain == "02_learn").unwrap()]
        } else {
            scored.iter().take(2).map(|(_, r)| *r).collect()
        };

        let available: Vec<&str> =
            self.corpus.manifest.sources.iter().map(|s| s.id.as_str()).collect();

        let mut out = format!("Question: {}\n\n", args.question);
        for rule in &picked {
            let have: Vec<&str> = rule
                .sources
                .iter()
                .copied()
                .filter(|s| available.contains(s))
                .collect();
            out.push_str(&format!("-> load  domains/{}/CONTEXT.md\n", rule.domain));
            out.push_str(&format!("   why:  {}\n", rule.why));
            out.push_str(&format!("   sources: {}\n", have.join(", ")));
            let missing: Vec<&str> = rule
                .sources
                .iter()
                .copied()
                .filter(|s| !available.contains(s))
                .collect();
            if !missing.is_empty() {
                out.push_str(&format!(
                    "   note: {} not in this corpus\n",
                    missing.join(", ")
                ));
            }
            out.push('\n');
        }

        // A literal error code short-circuits routing entirely.
        for code in error_codes(&args.question) {
            out.push_str(&format!("   direct: oxidizer_explain {{\"code\": \"{code}\"}}\n"));
        }
        out.push_str(
            "\nLoad exactly one domain contract. Loading all seven is the failure \
             mode this skill exists to prevent.",
        );
        text_result(out)
    }

    #[tool(
        name = "oxidizer_search",
        description = "Search the mirrored Rust canon (The Book, Rust By Example, \
                       the Reference, the Rustonomicon, std docs, the error index, \
                       Cargo book, lints, and the Brown University sources). \
                       Returns ranked titles and summaries with token costs — these \
                       are not sources; follow up with oxidizer_show or oxidizer_api \
                       and read the document before answering."
    )]
    fn search(&self, Parameters(args): Parameters<SearchArgs>) -> Result<CallToolResult, McpError> {
        let limit = args.limit.clamp(1, 25);
        let hits = self.corpus.search(&args.query, &args.sources, limit);
        if hits.is_empty() {
            return text_result(format!(
                "No matches for {:?}. Try fewer or more general terms, or drop the \
                 source filter.",
                args.query
            ));
        }
        let mut out = format!("{} hit(s) for {:?}\n\n", hits.len(), args.query);
        for (rank, (_, d)) in hits.iter().enumerate() {
            out.push_str(&format!(
                "[{}] {}   ({}, ~{} tok)\n     show: {}/{}\n",
                rank + 1,
                d.title,
                d.source,
                d.tokens,
                d.source,
                d.id
            ));
            if !d.summary.is_empty() {
                let s: String = d.summary.chars().take(220).collect();
                out.push_str(&format!("     {s}\n"));
            }
            out.push_str(&format!("     {}\n\n", d.url));
        }
        out.push_str("Retrieve one before answering — search shows summaries, not sources.");
        text_result(out)
    }

    #[tool(
        name = "oxidizer_show",
        description = "Read one document from the canon, or one section of it, \
                       under a token budget. Pass the `source/id` returned by \
                       oxidizer_search. Use `section` to narrow rather than \
                       raising max_tokens."
    )]
    fn show(&self, Parameters(args): Parameters<ShowArgs>) -> Result<CallToolResult, McpError> {
        let doc = self
            .corpus
            .find(&args.doc_id, None)
            .ok_or_else(|| McpError::invalid_params(
                format!("no document {:?}; use oxidizer_search to find its id", args.doc_id),
                None,
            ))?;

        let mut md = self
            .corpus
            .read(doc)
            .map_err(|e| McpError::internal_error(e.to_string(), None))?;

        if let Some(section) = &args.section {
            let want = section.to_lowercase();
            let sections = split_sections(&md);
            let picked = sections.iter().find(|(_, h, _)| h.to_lowercase().contains(&want));
            match picked {
                Some((lvl, head, body)) => {
                    md = format!("{} {}\n\n{}", "#".repeat(*lvl), head, body);
                }
                None => {
                    let avail: Vec<&str> =
                        sections.iter().take(25).map(|(_, h, _)| h.as_str()).collect();
                    return Err(McpError::invalid_params(
                        format!(
                            "no section matching {section:?} in {}. Sections: {}",
                            doc.id,
                            avail.join(", ")
                        ),
                        None,
                    ));
                }
            }
        }

        let (text, truncated) = budget_text(&md, args.max_tokens.clamp(100, 50_000));
        let returned = estimate_tokens(&text);
        let mut out = format!("# {}\n\n{}", doc.title, text);
        out.push_str(&provenance(doc, returned, truncated));
        if truncated {
            let heads: Vec<String> = split_sections(&md)
                .into_iter()
                .take(20)
                .map(|(_, h, _)| h)
                .collect();
            if !heads.is_empty() {
                out.push_str(&format!("\nSections available: {}", heads.join(", ")));
            }
        }
        text_result(out)
    }

    #[tool(
        name = "oxidizer_explain",
        description = "Explain a Rust compiler error code (E0502, E0382, E0106, \
                       ...) from the official error index, with a minimal \
                       reproduction and the fix. Use whenever an error code \
                       appears in compiler output."
    )]
    fn explain(&self, Parameters(args): Parameters<ExplainArgs>) -> Result<CallToolResult, McpError> {
        let code = error_codes(&args.code)
            .into_iter()
            .next()
            .ok_or_else(|| McpError::invalid_params(
                format!("{:?} is not a compiler error code (expected e.g. E0502)", args.code),
                None,
            ))?;
        let doc = self.corpus.find(&code, Some("error-index")).ok_or_else(|| {
            McpError::invalid_params(format!("unknown error code {code}"), None)
        })?;
        let md = self
            .corpus
            .read(doc)
            .map_err(|e| McpError::internal_error(e.to_string(), None))?;
        let (text, truncated) = budget_text(&md, args.max_tokens.clamp(100, 50_000));
        let returned = estimate_tokens(&text);
        text_result(format!("{text}{}", provenance(doc, returned, truncated)))
    }

    #[tool(
        name = "oxidizer_api",
        description = "Look up a Rust standard library item or one of its methods \
                       and return the exact signature and docs. Accepts `Vec`, \
                       `Vec::retain`, or `std::vec::Vec::retain`. Always prefer \
                       asking for a specific method — whole container types run to \
                       tens of thousands of tokens."
    )]
    fn api(&self, Parameters(args): Parameters<ApiArgs>) -> Result<CallToolResult, McpError> {
        let (doc, member) = self.corpus.resolve_api(&args.path).ok_or_else(|| {
            McpError::invalid_params(
                format!(
                    "no std item matching {:?}; try oxidizer_search with sources \
                     [\"std\"]",
                    args.path
                ),
                None,
            )
        })?;

        let md = self
            .corpus
            .read(doc)
            .map_err(|e| McpError::internal_error(e.to_string(), None))?;
        let path = doc.path.clone().unwrap_or_else(|| doc.title.clone());

        let (body, anchor) = match &member {
            Some(m) => {
                let sections = split_sections(&md);
                let exact = sections.iter().find(|(_, h, _)| h.eq_ignore_ascii_case(m));
                let loose = sections
                    .iter()
                    .find(|(_, h, _)| h.to_lowercase().contains(&m.to_lowercase()));
                let (_, head, sec) = exact.or(loose).ok_or_else(|| {
                    McpError::invalid_params(
                        format!(
                            "{path} has no member {m:?}. Members: {}",
                            doc.members.iter().take(40).cloned().collect::<Vec<_>>().join(", ")
                        ),
                        None,
                    )
                })?;
                (format!("# {path}::{head}\n\n{sec}"), format!("#method.{head}"))
            }
            None => (md.clone(), String::new()),
        };

        let (text, truncated) = budget_text(&body, args.max_tokens.clamp(100, 50_000));
        let mut out = text;
        out.push_str(&format!("\n\nSource: {}{anchor}", doc.url));
        if truncated && member.is_none() {
            out.push_str(&format!(
                "\n[truncated — {path} is ~{} tokens. Ask for one member instead. \
                 Members: {}]",
                doc.tokens,
                doc.members.iter().take(30).cloned().collect::<Vec<_>>().join(", ")
            ));
        }
        text_result(out)
    }

    #[tool(
        name = "oxidizer_lint",
        description = "Look up a rustc or clippy lint by name (with or without the \
                       `clippy::` prefix, dashes or underscores) and return what it \
                       wants, its default level, and how to silence it."
    )]
    fn lint(&self, Parameters(args): Parameters<LintArgs>) -> Result<CallToolResult, McpError> {
        let doc = self.corpus.lint(&args.name).ok_or_else(|| {
            let near = self.corpus.near_lints(&args.name);
            McpError::invalid_params(
                if near.is_empty() {
                    format!("no lint named {:?}", args.name)
                } else {
                    format!("no lint named {:?}. Did you mean: {}", args.name, near.join(", "))
                },
                None,
            )
        })?;
        let md = self
            .corpus
            .read(doc)
            .map_err(|e| McpError::internal_error(e.to_string(), None))?;
        let (text, truncated) = budget_text(&md, args.max_tokens.clamp(100, 50_000));
        let returned = estimate_tokens(&text);
        text_result(format!("{text}{}", provenance(doc, returned, truncated)))
    }

    #[tool(
        name = "oxidizer_manifest",
        description = "Report what is mirrored in the corpus, which toolchain it \
                       was built against, and whether it has gone stale. Use when \
                       an answer depends on the Rust version, or when another \
                       Oxidizer tool reports something missing."
    )]
    fn manifest(&self) -> Result<CallToolResult, McpError> {
        let m = &self.corpus.manifest;
        let mut out = format!(
            "corpus:    {}\nbuilt:     {}\ntoolchain: {}\ntotals:    {} docs, ~{}k tokens\n\n",
            self.corpus.root.display(),
            m.generated_at,
            m.toolchain.as_ref().map_or("unknown", |t| t.rustc_version.as_str()),
            m.totals.docs,
            m.totals.tokens / 1000
        );
        out.push_str(&format!(
            "{:<16} {:>6} {:>9} {:<9} role\n",
            "source", "docs", "tokens", "origin"
        ));
        for s in &m.sources {
            out.push_str(&format!(
                "{:<16} {:>6} {:>8}k {:<9} {}\n",
                s.id,
                s.doc_count,
                s.total_tokens / 1000,
                s.origin,
                s.role
            ));
        }
        out.push_str("\nUpstream:\n");
        for s in &m.sources {
            out.push_str(&format!("  {:<16} {}  — {}\n", s.id, s.url, s.title));
        }
        if let Some(built) = m.toolchain.as_ref().map(|t| t.rustc_version.as_str())
            && let Some(current) = current_rustc_version()
            && current != built
        {
            out.push_str(&format!(
                "\nSTALE: toolchain is now {current}, corpus was built for {built}. \
                 Re-run scripts/mirror.py.\n"
            ));
        }
        text_result(out)
    }
}

#[tool_handler]
impl ServerHandler for Oxidizer {
    fn get_info(&self) -> ServerInfo {
        let sources: Vec<&str> =
            self.corpus.manifest.sources.iter().map(|s| s.id.as_str()).collect();
        // Not `Implementation::from_build_env()`: its `env!` expands inside the
        // rmcp crate, so it would report the SDK's name rather than ours.
        ServerInfo::new(ServerCapabilities::builder().enable_tools().build())
            .with_server_info(
                Implementation::new(env!("CARGO_PKG_NAME"), env!("CARGO_PKG_VERSION"))
                    .with_title("Oxidizer — the Rust canon, routed"),
            )
            .with_instructions(format!(
                "Oxidizer serves the official Rust canon, mirrored locally and \
                 pinned to {}. Answer Rust questions from these tools rather than \
                 from memory: Rust's rules are version-specific and this mirror \
                 agrees with the compiler that will actually build the user's code.\n\n\
                 Start with oxidizer_route when unsure where to look; use \
                 oxidizer_explain for any error code, oxidizer_api for signatures, \
                 oxidizer_lint for idiom. oxidizer_search returns summaries, not \
                 sources — follow it with oxidizer_show and read the document \
                 before answering. Every result carries its doc.rust-lang.org URL; \
                 cite it.\n\n\
                 Mirrored sources: {}.",
                self.corpus
                    .manifest
                    .toolchain
                    .as_ref()
                    .map_or("an unknown toolchain", |t| t.rustc_version.as_str()),
                sources.join(", ")
            ))
    }
}

// -- helpers ---------------------------------------------------------------

/// Extract `E####` codes from arbitrary text (a question, or raw rustc output).
fn error_codes(text: &str) -> Vec<String> {
    let bytes = text.as_bytes();
    let mut out = Vec::new();
    for (i, _) in text.match_indices(['E', 'e']) {
        let digits = &bytes[i + 1..];
        if digits.len() >= 4 && digits[..4].iter().all(|b| b.is_ascii_digit()) {
            let code = format!("E{}", std::str::from_utf8(&digits[..4]).unwrap());
            if !out.contains(&code) {
                out.push(code);
            }
        }
    }
    out
}

fn current_rustc_version() -> Option<String> {
    let out = std::process::Command::new("rustc").arg("--version").output().ok()?;
    Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn resolve_corpus_dir() -> PathBuf {
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        if a == "--corpus" {
            if let Some(p) = args.next() {
                return PathBuf::from(p);
            }
        } else if let Some(p) = a.strip_prefix("--corpus=") {
            return PathBuf::from(p);
        }
    }
    if let Ok(p) = std::env::var("OXIDIZER_CORPUS") {
        return PathBuf::from(p);
    }
    // Default: `corpus/` at the repository root that contains this crate.
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .ancestors()
        .nth(2)
        .map(|r| r.join("corpus"))
        .unwrap_or_else(|| PathBuf::from("corpus"))
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // stdout is the MCP transport — every log line must go to stderr or the
    // protocol stream is corrupted.
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_env_filter(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "oxidizer_mcp=info".into()),
        )
        .init();

    let dir = resolve_corpus_dir();
    let corpus = Arc::new(Corpus::load(&dir)?);
    tracing::info!(
        corpus = %dir.display(),
        docs = corpus.manifest.totals.docs,
        sources = corpus.manifest.sources.len(),
        "oxidizer corpus loaded"
    );

    let service = Oxidizer::new(corpus).serve(stdio()).await?;
    service.waiting().await?;
    Ok(())
}
