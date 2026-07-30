//! Reading and querying the Oxidizer corpus.
//!
//! The corpus is produced by `skills/oxidizer/scripts/mirror.py`, but nothing
//! here shells out to Python: the index is plain JSON and the retrieval logic
//! is reimplemented natively so an MCP client needs only this binary.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
pub struct Toolchain {
    #[serde(default)]
    pub rustc_version: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SourceInfo {
    pub id: String,
    pub title: String,
    pub role: String,
    pub url: String,
    pub doc_count: usize,
    pub total_tokens: usize,
    #[serde(default)]
    pub origin: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Totals {
    pub docs: usize,
    pub tokens: usize,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Manifest {
    #[serde(default)]
    pub generated_at: String,
    #[serde(default)]
    pub toolchain: Option<Toolchain>,
    pub sources: Vec<SourceInfo>,
    pub totals: Totals,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Doc {
    pub id: String,
    pub source: String,
    #[serde(default)]
    pub kind: String,
    pub title: String,
    #[serde(default)]
    pub path: Option<String>,
    #[serde(default)]
    pub headings: Vec<String>,
    #[serde(default)]
    pub members: Vec<String>,
    #[serde(default)]
    pub summary: String,
    pub url: String,
    pub tokens: usize,
    pub file: String,
}

#[derive(Deserialize)]
struct IndexFile {
    docs: Vec<Doc>,
}

/// Lowercased, noise-stripped views of a document, built once at load.
#[derive(Debug, Clone, Default)]
pub struct Fields {
    pub title: String,
    pub path: String,
    pub doc_id: String,
    pub heads: String,
    pub members: String,
    pub summary: String,
}

impl Fields {
    /// Boosts layered on top of the BM25 body score, not a scoring scheme in
    /// their own right — hence much smaller than the old flat weights.
    fn iter(&self) -> [(&str, f64); 6] {
        [
            (self.title.as_str(), 3.0),
            (self.path.as_str(), 2.5),
            (self.members.as_str(), 2.0),
            (self.heads.as_str(), 1.5),
            (self.doc_id.as_str(), 1.5),
            (self.summary.as_str(), 0.5),
        ]
    }
}

fn field_bonus(f: &Fields, weighted: &HashMap<String, f64>) -> f64 {
    let mut bonus = 0.0;
    for (term, weight) in weighted {
        for (blob, boost) in f.iter() {
            if blob.is_empty() || !blob.contains(term.as_str()) {
                continue;
            }
            bonus += boost * weight * if whole_word(blob, term) { 1.0 } else { 0.3 };
        }
    }
    bonus
}

/// rustdoc emits these as headings on nearly every page; left in, a search for
/// "trait objects" scores every std type equally on the word "trait".
const HEADING_NOISE: &[&str] = &[
    "trait implementations",
    "auto trait implementations",
    "blanket implementations",
    "implementations",
    "methods from deref",
    "required methods",
    "provided methods",
    "implementors",
    "aliased type",
    "members",
    "examples",
    "panics",
    "errors",
    "safety",
];

const KIND_PREFIXES: &[&str] = &[
    "struct ", "enum ", "trait ", "fn ", "macro ", "type ", "constant ",
    "static ", "union ", "primitive ", "keyword ", "module ", "derive ", "attr ",
];

/// Question scaffolding. Left in, "difference between anyhow and thiserror"
/// retrieves `btree_set::Difference` on the word "difference". That was a real
/// result before these were removed.
const STOPWORDS: &[&str] = &[
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "to",
    "of", "in", "on", "for", "and", "or", "it", "this", "that", "with", "as",
    "at", "by", "from", "how", "what", "why", "when", "where", "do", "does",
    "did", "can", "could", "should", "would", "will", "i", "my", "me", "you",
    "your", "we", "our", "rust", "code", "use", "using", "used", "get", "make",
    "difference", "between", "vs", "versus", "way", "ways", "best", "good",
    "want", "need", "trying", "try", "help", "please", "something", "thing",
    "things", "any", "some", "all", "into", "about", "there", "here", "have",
    "has", "but", "not", "if", "then", "than", "so", "just", "only", "also",
    "work", "works", "working", "handle", "handling", "mean", "means", "one",
    "two", "let", "like", "know", "tell", "show", "give", "take", "put",
];

/// What users say -> what the canon calls it. The single largest measured
/// failure class was questions sharing no vocabulary at all with the document
/// that answers them, which no amount of reweighting can fix. Expansions are
/// discounted so they widen recall without overriding the user's own wording.
const ALIASES: &[(&str, &[&str])] = &[
    ("passing", &["move", "ownership", "transfer"]),
    ("passed", &["move", "ownership"]),
    ("giving", &["move", "ownership"]),
    ("consumed", &["move", "ownership", "drop"]),
    ("reuse", &["move", "ownership", "borrow"]),
    ("copy", &["clone", "copy", "move"]),
    ("freed", &["drop", "deallocate", "scope"]),
    ("dangling", &["lifetime", "borrow", "dangling"]),
    ("outlives", &["lifetime", "outlives"]),
    ("tick", &["lifetime", "annotation"]),
    ("annotation", &["lifetime", "generic"]),
    ("change", &["mutable", "mutability", "borrow"]),
    ("modify", &["mutable", "mutability", "borrow"]),
    ("mutate", &["mutable", "mutability"]),
    ("threads", &["thread", "concurrency", "send", "sync"]),
    ("thread", &["thread", "concurrency", "spawn"]),
    ("share", &["shared", "arc", "mutex", "state"]),
    ("shared", &["arc", "mutex", "state", "sync"]),
    ("counter", &["mutex", "arc", "atomic", "shared"]),
    ("parallel", &["thread", "concurrency", "spawn"]),
    ("concurrently", &["concurrency", "async", "spawn", "join"]),
    ("lock", &["mutex", "rwlock", "guard"]),
    ("await", &["async", "future", "poll"]),
    ("asynchronous", &["async", "future"]),
    ("blocking", &["async", "thread", "block"]),
    ("string", &["string", "str", "utf8", "chars"]),
    ("text", &["string", "str", "utf8"]),
    ("characters", &["chars", "utf8", "grapheme"]),
    ("substring", &["slice", "str", "chars"]),
    ("vector", &["vec", "vector", "slice"]),
    ("array", &["array", "slice", "vec"]),
    ("list", &["vec", "slice", "linked"]),
    ("dictionary", &["hashmap", "map", "btreemap"]),
    ("sort", &["sort", "sort_by", "sort_by_key", "ord"]),
    ("sorting", &["sort", "sort_by_key", "ord"]),
    ("iterate", &["iterator", "iter", "loop", "next"]),
    ("iterating", &["iterator", "iter", "enumerate"]),
    ("index", &["index", "indexing", "enumerate", "position"]),
    ("group", &["entry", "hashmap", "fold", "collect"]),
    ("filter", &["filter", "iterator", "retain"]),
    ("error", &["error", "result", "err"]),
    ("errors", &["error", "result", "err"]),
    ("failure", &["error", "result", "panic"]),
    ("crash", &["panic", "unwrap", "abort"]),
    ("propagate", &["question", "result", "from", "error"]),
    ("interface", &["trait", "impl", "dyn"]),
    ("inheritance", &["trait", "composition", "dyn"]),
    ("constraint", &["bound", "where", "trait"]),
    ("polymorphism", &["trait", "dyn", "generic"]),
    ("allocating", &["allocation", "heap", "capacity", "reserve"]),
    ("allocation", &["heap", "capacity", "with_capacity", "reserve"]),
    ("memory", &["heap", "stack", "allocation", "drop"]),
    ("file", &["module", "mod", "crate", "path"]),
    ("files", &["module", "mod", "crate"]),
    ("import", &["use", "path", "module"]),
    ("visibility", &["pub", "private", "module"]),
    ("dependency", &["dependencies", "cargo", "crate"]),
    ("feature", &["features", "cargo", "cfg"]),
    ("test", &["test", "tests", "assert"]),
    ("testing", &["test", "tests", "assert"]),
    ("benchmark", &["bench", "profile", "release"]),
    ("pointer", &["pointer", "raw", "unsafe", "reference"]),
];

/// Widely used crates deliberately not mirrored. Naming one reliably means the
/// canon cannot answer the question, and saying so beats returning the
/// closest-looking std page.
const NON_CANON_CRATES: &[&str] = &[
    "serde", "serde_json", "tokio", "anyhow", "thiserror", "clap", "rayon",
    "reqwest", "axum", "actix", "hyper", "tracing", "log", "env_logger",
    "regex", "chrono", "uuid", "rand", "itertools", "futures", "async_std",
    "crossbeam", "parking_lot", "bytes", "nom", "syn", "quote", "proc_macro2",
    "diesel", "sqlx", "bevy", "egui", "wgpu", "criterion", "proptest",
    "quickcheck", "mockall", "eyre", "smallvec", "indexmap", "dashmap",
    "once_cell", "lazy_static", "ndarray", "polars", "petgraph", "image",
    "ratatui", "crossterm", "pyo3", "wasm_bindgen",
];

/// Query terms mapped to a weight; alias expansions are discounted.
pub fn expand(qterms: &[String], query: &str) -> HashMap<String, f64> {
    let mut out: HashMap<String, f64> = qterms.iter().map(|t| (t.clone(), 1.0)).collect();
    // Lifetime syntax survives neither tokenisation nor stopword removal.
    if lifetime_syntax(query) {
        for t in ["lifetime", "annotation"] {
            out.entry(t.to_string()).or_insert(0.45);
        }
    }
    for t in qterms {
        if let Some((_, aliases)) = ALIASES.iter().find(|(k, _)| k == t) {
            for a in *aliases {
                out.entry((*a).to_string()).or_insert(0.45);
            }
        }
    }
    out
}

fn lifetime_syntax(query: &str) -> bool {
    let b = query.as_bytes();
    b.iter().enumerate().any(|(i, &c)| {
        c == b'\'' && b.get(i + 1).is_some_and(|n| n.is_ascii_lowercase())
    })
}

pub fn detect_non_canon(query: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    for tok in tokenize(query) {
        if NON_CANON_CRATES.contains(&tok.as_str()) && !out.contains(&tok) {
            out.push(tok);
        }
    }
    out
}

#[derive(Debug, Deserialize)]
pub struct Postings {
    pub docs: Vec<String>,
    pub lengths: Vec<u32>,
    pub avg_length: f64,
    /// term -> [[doc_ordinal, term_frequency], ..]
    pub terms: HashMap<String, Vec<[u32; 2]>>,
}

/// How far to trust a result set. Reported to the caller so an agent can tell
/// "the canon answers this" from "the closest thing I could find".
#[derive(Debug, Clone)]
pub struct Assessment {
    pub confidence: String,
    pub coverage: f64,
    pub matched_terms: usize,
    pub query_terms: usize,
    pub non_canon: Vec<String>,
    pub reason: String,
}

impl Assessment {
    fn none(reason: &str) -> Self {
        Self {
            confidence: "none".into(),
            coverage: 0.0,
            matched_terms: 0,
            query_terms: 0,
            non_canon: Vec::new(),
            reason: reason.to_string(),
        }
    }
}

const K1: f64 = 1.2; // BM25 term-frequency saturation
const B: f64 = 0.75; // BM25 length normalisation

pub struct Corpus {
    pub root: PathBuf,
    pub manifest: Manifest,
    pub docs: Vec<Doc>,
    fields: Vec<Fields>,
    postings: Option<Postings>,
    by_key: HashMap<String, usize>,
    by_path: HashMap<String, usize>,
    by_name: HashMap<String, Vec<usize>>,
}

impl Corpus {
    pub fn load(root: &Path) -> Result<Self> {
        let manifest_path = root.join("MANIFEST.json");
        let raw = std::fs::read_to_string(&manifest_path).with_context(|| {
            format!(
                "no corpus at {}\n  build it with: python3 skills/oxidizer/scripts/mirror.py",
                root.display()
            )
        })?;
        let manifest: Manifest =
            serde_json::from_str(&raw).context("MANIFEST.json is not valid JSON")?;

        let mut docs = Vec::new();
        for src in &manifest.sources {
            let idx = root.join(&src.id).join("INDEX.json");
            if !idx.exists() {
                continue;
            }
            let text = std::fs::read_to_string(&idx)
                .with_context(|| format!("reading {}", idx.display()))?;
            let parsed: IndexFile = serde_json::from_str(&text)
                .with_context(|| format!("parsing {}", idx.display()))?;
            docs.extend(parsed.docs);
        }
        if docs.is_empty() {
            bail!("corpus at {} contains no documents", root.display());
        }

        let fields: Vec<Fields> = docs.iter().map(build_fields).collect();

        // Concrete items beat modules when case-folding collides them
        // (`std::vec` the module vs `std::Vec` the struct).
        let mut by_path: HashMap<String, usize> = HashMap::new();
        let mut by_name: HashMap<String, Vec<usize>> = HashMap::new();
        for (i, d) in docs.iter().enumerate() {
            let Some(p) = d.path.as_ref() else { continue };
            let key = p.to_lowercase();
            match by_path.get(&key) {
                Some(&prev) if docs[prev].kind != "module" || d.kind == "module" => {}
                _ => {
                    by_path.insert(key, i);
                }
            }
            let leaf = p.rsplit("::").next().unwrap_or(p).to_lowercase();
            by_name.entry(leaf).or_default().push(i);
        }
        for v in by_name.values_mut() {
            v.sort_by_key(|&i| (kind_rank(&docs[i].kind), docs[i].path.as_ref().map_or(0, |p| p.len())));
        }

        let by_key: HashMap<String, usize> = docs
            .iter()
            .enumerate()
            .map(|(i, d)| (format!("{}/{}", d.source, d.id), i))
            .collect();

        // Absent on a corpus built before postings existed; search reports that
        // rather than silently returning nothing.
        let postings = std::fs::read_to_string(root.join("POSTINGS.json"))
            .ok()
            .and_then(|t| serde_json::from_str::<Postings>(&t).ok());

        Ok(Self {
            root: root.to_path_buf(),
            manifest,
            docs,
            fields,
            postings,
            by_key,
            by_path,
            by_name,
        })
    }

    pub fn read(&self, doc: &Doc) -> Result<String> {
        let path = self.root.join(&doc.source).join(&doc.file);
        let text = std::fs::read_to_string(&path)
            .with_context(|| format!("reading {}", path.display()))?;
        Ok(strip_provenance(&text))
    }

    pub fn find(&self, id: &str, source: Option<&str>) -> Option<&Doc> {
        let want = id.to_lowercase();
        self.docs.iter().find(|d| {
            source.is_none_or(|s| d.source == s)
                && (d.id.to_lowercase() == want
                    || format!("{}/{}", d.source, d.id).to_lowercase() == want)
        })
    }

    /// Ranked search: BM25 over document bodies plus a boost for matches in
    /// high-signal fields, mirroring `oxidize.py` exactly.
    ///
    /// `prefer` is a soft prior from the routing table rather than a filter —
    /// routing is a guess, and hard-scoping to it makes the right document
    /// unreachable when the guess is wrong.
    pub fn search(
        &self,
        query: &str,
        sources: &[String],
        limit: usize,
        prefer: &[String],
    ) -> (Vec<(f64, &Doc)>, Assessment) {
        let qterms = terms(query);
        if qterms.is_empty() {
            return (Vec::new(), Assessment::none("query has no content terms"));
        }
        let weighted = expand(&qterms, query);
        let non_canon = detect_non_canon(query);

        let Some(post) = self.postings.as_ref() else {
            return (Vec::new(), Assessment::none("corpus has no postings index; rebuild with mirror.py"));
        };

        let allowed: Option<Vec<bool>> = if sources.is_empty() {
            None
        } else {
            Some(
                post.docs
                    .iter()
                    .map(|k| {
                        k.split_once('/')
                            .is_some_and(|(src, _)| sources.iter().any(|s| s == src))
                    })
                    .collect(),
            )
        };

        // BM25 accumulation over the postings lists of the query terms.
        let n = post.docs.len() as f64;
        let avg = if post.avg_length > 0.0 { post.avg_length } else { 1.0 };
        let mut raw: HashMap<u32, f64> = HashMap::new();
        for (term, weight) in &weighted {
            let Some(plist) = post.terms.get(term.as_str()) else { continue };
            let df = plist.len() as f64;
            let idf = (1.0 + (n - df + 0.5) / (df + 0.5)).ln();
            for entry in plist {
                let (ordinal, tf) = (entry[0], entry[1] as f64);
                if let Some(mask) = &allowed
                    && !mask.get(ordinal as usize).copied().unwrap_or(false)
                {
                    continue;
                }
                let dl = *post.lengths.get(ordinal as usize).unwrap_or(&1) as f64;
                let denom = tf + K1 * (1.0 - B + B * dl / avg);
                *raw.entry(ordinal).or_insert(0.0) += weight * idf * (tf * (K1 + 1.0)) / denom;
            }
        }
        if raw.is_empty() {
            let mut a = Assessment::none("no document contains any of the query terms");
            a.non_canon = non_canon;
            return (Vec::new(), a);
        }

        let mut ranked: Vec<(u32, f64)> = raw.into_iter().collect();
        ranked.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        ranked.truncate(limit.saturating_mul(12).max(limit));

        let phrase = query.trim().to_lowercase();
        let mut scored: Vec<(f64, &Doc)> = Vec::new();
        for (ordinal, base) in ranked {
            let Some(key) = post.docs.get(ordinal as usize) else { continue };
            let Some(&i) = self.by_key.get(key.as_str()) else { continue };
            let f = &self.fields[i];
            let doc = &self.docs[i];
            let mut total = base + field_bonus(f, &weighted);
            if phrase.len() > 8 && f.title.contains(&phrase) {
                total += 8.0;
            }
            if doc.id.ends_with("index") || doc.kind == "module" {
                total *= 0.6;
            }
            if prefer.contains(&doc.source) {
                total *= 1.4;
            }
            scored.push((total, doc));
        }
        scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
        scored.truncate(limit);

        let assessment = self.assess(&scored, &qterms, non_canon);
        (scored, assessment)
    }

    /// How much of the question the best hit actually covers.
    ///
    /// Raw scores are not comparable across queries or across source filters,
    /// so they are useless as a confidence signal. Term coverage is comparable,
    /// and is what gets reported.
    fn assess(&self, hits: &[(f64, &Doc)], qterms: &[String], non_canon: Vec<String>) -> Assessment {
        let Some((_, top)) = hits.first() else {
            let mut a = Assessment::none("nothing matched");
            a.non_canon = non_canon;
            return a;
        };
        let post = self.postings.as_ref();
        let key = format!("{}/{}", top.source, top.id);
        let ordinal = post.and_then(|p| p.docs.iter().position(|d| *d == key));

        let mut covered = 0usize;
        if let (Some(p), Some(o)) = (post, ordinal) {
            for t in qterms {
                if p.terms
                    .get(t.as_str())
                    .is_some_and(|pl| pl.iter().any(|e| e[0] as usize == o))
                {
                    covered += 1;
                }
            }
        }
        let coverage = covered as f64 / qterms.len().max(1) as f64;

        let (confidence, reason) = if !non_canon.is_empty() {
            ("low", format!(
                "question names {}, which the canon does not cover — say so rather \
                 than substituting a std page",
                non_canon.join(", ")
            ))
        } else if coverage >= 0.6 {
            ("high", "top result contains most of the question's terms".to_string())
        } else if coverage >= 0.34 {
            ("medium", "top result contains some of the question's terms".to_string())
        } else {
            ("low", "top result contains few of the question's terms; the canon may \
                     not answer this".to_string())
        };

        Assessment {
            confidence: confidence.to_string(),
            coverage,
            matched_terms: covered,
            query_terms: qterms.len(),
            non_canon,
            reason,
        }
    }

    /// Resolve an API path like `std::vec::Vec::retain`, `Vec::retain`, or
    /// `Vec` to a document and an optional member name.
    ///
    /// A candidate is only accepted if it actually carries the requested
    /// member, which is what keeps `Option::map` on the `Option` enum rather
    /// than on `std::iter::Map`.
    pub fn resolve_api(&self, query: &str) -> Option<(&Doc, Option<String>)> {
        let normalised = query.trim().replace('.', "::");
        let parts: Vec<&str> = normalised
            .split("::")
            .filter(|p| !p.is_empty())
            .collect();
        if parts.is_empty() {
            return None;
        }

        let mut fallback: Option<(usize, Option<String>)> = None;
        for cut in (1..=parts.len()).rev() {
            let remainder = &parts[cut..];
            for &i in &self.candidates(&parts[..cut]) {
                if remainder.is_empty() {
                    return Some((&self.docs[i], None));
                }
                let want = remainder[0].to_lowercase();
                if self.docs[i].members.iter().any(|m| m.to_lowercase() == want) {
                    return Some((&self.docs[i], Some(remainder.join("::"))));
                }
                if fallback.is_none() {
                    fallback = Some((i, Some(remainder.join("::"))));
                }
            }
        }
        fallback.map(|(i, m)| (&self.docs[i], m))
    }

    fn candidates(&self, prefix: &[&str]) -> Vec<usize> {
        let joined = prefix.join("::").to_lowercase();
        let mut out: Vec<usize> = Vec::new();
        for key in [joined.clone(), format!("std::{joined}")] {
            if let Some(&i) = self.by_path.get(&key)
                && !out.contains(&i)
            {
                out.push(i);
            }
        }
        if let Some(named) = self.by_name.get(&prefix[prefix.len() - 1].to_lowercase()) {
            for &i in named {
                // Only accept a name match that actually ends with the
                // qualifiers given, so `vec::Vec` cannot match `foo::Vec`.
                let p = self.docs[i].path.as_deref().unwrap_or("").to_lowercase();
                if p.ends_with(&joined) && !out.contains(&i) {
                    out.push(i);
                }
            }
        }
        out.sort_by_key(|&i| {
            (kind_rank(&self.docs[i].kind), self.docs[i].path.as_ref().map_or(0, |p| p.len()))
        });
        out
    }

    pub fn lint(&self, name: &str) -> Option<&Doc> {
        let raw = name.trim().replace('-', "_");
        let bare = raw.rsplit("::").next().unwrap_or(&raw).to_lowercase();
        let lints = || self.docs.iter().filter(|d| d.source == "lints");
        lints()
            .find(|d| d.path.as_deref().unwrap_or("").eq_ignore_ascii_case(&raw))
            .or_else(|| {
                lints().find(|d| {
                    d.path
                        .as_deref()
                        .unwrap_or("")
                        .rsplit("::")
                        .next()
                        .is_some_and(|l| l.eq_ignore_ascii_case(&bare))
                })
            })
    }

    pub fn near_lints(&self, name: &str) -> Vec<String> {
        let bare = name.trim().replace('-', "_").to_lowercase();
        let bare = bare.rsplit("::").next().unwrap_or(&bare).to_string();
        self.docs
            .iter()
            .filter(|d| d.source == "lints")
            .filter_map(|d| d.path.clone())
            .filter(|p| p.to_lowercase().contains(&bare))
            .take(8)
            .collect()
    }
}

// -- helpers ---------------------------------------------------------------

fn build_fields(d: &Doc) -> Fields {
    let mut title = d.title.to_lowercase();
    if d.path.is_some() {
        for p in KIND_PREFIXES {
            if let Some(rest) = title.strip_prefix(p) {
                title = rest.to_string();
                break;
            }
        }
    }
    let mut heads = d.headings.join(" ").to_lowercase();
    for noise in HEADING_NOISE {
        heads = heads.replace(noise, " ");
    }
    Fields {
        title,
        path: d.path.clone().unwrap_or_default().to_lowercase(),
        doc_id: d.id.to_lowercase().replace(['/', '-', '_'], " "),
        heads,
        members: d.members.join(" ").to_lowercase(),
        summary: d.summary.to_lowercase(),
    }
}

fn kind_rank(kind: &str) -> u8 {
    match kind {
        "struct" | "enum" | "trait" => 0,
        "primitive" => 1,
        "fn" => 2,
        "macro" | "type" => 3,
        "constant" | "static" | "union" => 4,
        "keyword" => 5,
        "module" => 9,
        _ => 6,
    }
}

fn whole_word(blob: &str, term: &str) -> bool {
    let bytes = blob.as_bytes();
    let mut from = 0usize;
    while let Some(rel) = blob[from..].find(term) {
        let start = from + rel;
        let end = start + term.len();
        let before_ok = start == 0 || !is_word_byte(bytes[start - 1]);
        let after_ok = end >= bytes.len() || !is_word_byte(bytes[end]);
        if before_ok && after_ok {
            return true;
        }
        from = start + 1;
        if from >= blob.len() {
            break;
        }
    }
    false
}

fn is_word_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

/// Tokenise exactly as `extract.py` does at index time. If the two ever
/// diverge, query terms silently stop matching the postings they should.
/// Identifiers are also split on `_` and at camelCase boundaries and the parts
/// emitted alongside the whole, so "capacity" finds `with_capacity`.
pub fn tokenize(text: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let bytes = text.as_bytes();
    let mut i = 0usize;
    while i < bytes.len() {
        let c = bytes[i];
        if !(c.is_ascii_alphabetic() || c == b'_') {
            i += 1;
            continue;
        }
        let start = i;
        while i < bytes.len() && (bytes[i].is_ascii_alphanumeric() || bytes[i] == b'_') {
            i += 1;
        }
        let raw = &text[start..i];
        let low = raw.to_ascii_lowercase();
        if low.len() > 1 {
            out.push(low.clone());
        }
        if raw.contains('_') {
            out.extend(low.split('_').filter(|p| p.len() > 1).map(str::to_string));
        } else if !raw.chars().all(|c| c.is_lowercase() || !c.is_alphabetic())
            && !raw.chars().all(|c| c.is_uppercase() || !c.is_alphabetic())
        {
            for part in split_camel(raw) {
                if part.len() > 1 {
                    out.push(part.to_ascii_lowercase());
                }
            }
        }
    }
    out
}

fn split_camel(s: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut cur = String::new();
    for ch in s.chars() {
        if ch.is_uppercase() && !cur.is_empty() {
            parts.push(std::mem::take(&mut cur));
        }
        cur.push(ch);
    }
    if !cur.is_empty() {
        parts.push(cur);
    }
    if parts.len() > 1 { parts } else { Vec::new() }
}

/// Content terms of a query, in order, without duplicates.
pub fn terms(query: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    for tok in tokenize(query) {
        if tok.len() > 1 && !STOPWORDS.contains(&tok.as_str()) && !out.contains(&tok) {
            out.push(tok);
        }
    }
    out
}

fn strip_provenance(text: &str) -> String {
    match text.strip_prefix("<!-- oxidizer:") {
        Some(rest) => rest
            .split_once("-->")
            .map(|(_, body)| body.trim_start_matches(['\n', '\r']).to_string())
            .unwrap_or_else(|| text.to_string()),
        None => text.to_string(),
    }
}

pub fn estimate_tokens(text: &str) -> usize {
    (text.len() / 4).max(1)
}

/// Truncate on a paragraph boundary so the tail is never a half sentence.
pub fn budget_text(text: &str, max_tokens: usize) -> (String, bool) {
    let limit = max_tokens.saturating_mul(4);
    if text.len() <= limit {
        return (text.to_string(), false);
    }
    // Never split inside a multi-byte character.
    let mut hard = limit.min(text.len());
    while hard > 0 && !text.is_char_boundary(hard) {
        hard -= 1;
    }
    let cut = text[..hard].rfind("\n\n").filter(|&c| c > limit / 2).unwrap_or(hard);
    (text[..cut].trim_end().to_string(), true)
}

/// Split a markdown document into `(level, heading, body)` triples.
pub fn split_sections(md: &str) -> Vec<(usize, String, String)> {
    let mut heads: Vec<(usize, usize, String)> = Vec::new(); // (offset, level, text)
    for (offset, line) in line_offsets(md) {
        let trimmed = line.trim_start();
        let level = trimmed.chars().take_while(|&c| c == '#').count();
        if (1..=6).contains(&level) && trimmed[level..].starts_with(' ') {
            heads.push((offset, level, trimmed[level + 1..].trim().to_string()));
        }
    }
    let mut out = Vec::with_capacity(heads.len());
    for (i, (offset, level, text)) in heads.iter().enumerate() {
        let body_start = md[*offset..]
            .find('\n')
            .map(|n| offset + n + 1)
            .unwrap_or(md.len());
        let end = heads.get(i + 1).map(|(o, _, _)| *o).unwrap_or(md.len());
        out.push((*level, text.clone(), md[body_start.min(end)..end].trim().to_string()));
    }
    out
}

fn line_offsets(s: &str) -> Vec<(usize, &str)> {
    let mut out = Vec::new();
    let mut start = 0usize;
    for line in s.split_inclusive('\n') {
        out.push((start, line.trim_end_matches(['\n', '\r'])));
        start += line.len();
    }
    out
}
