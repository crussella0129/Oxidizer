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
    #[serde(default)]
    pub keywords: Vec<String>,
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
    pub keywords: String,
}

impl Fields {
    fn iter(&self) -> [(&str, f64); 7] {
        [
            (self.title.as_str(), 10.0),
            (self.path.as_str(), 8.0),
            (self.doc_id.as_str(), 5.0),
            (self.heads.as_str(), 3.0),
            (self.members.as_str(), 6.0),
            (self.summary.as_str(), 2.0),
            (self.keywords.as_str(), 1.5),
        ]
    }

    fn any_contains(&self, term: &str) -> bool {
        self.iter().iter().any(|(b, _)| b.contains(term))
    }
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

const STOPWORDS: &[&str] = &[
    "the", "a", "an", "is", "are", "was", "were", "be", "to", "of", "in", "on",
    "for", "and", "or", "it", "this", "that", "with", "as", "at", "by", "from",
    "how", "what", "why", "do", "does", "did", "can", "i", "my", "me", "you",
    "rust", "code", "use", "using", "get", "make",
];

pub struct Corpus {
    pub root: PathBuf,
    pub manifest: Manifest,
    pub docs: Vec<Doc>,
    fields: Vec<Fields>,
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

        Ok(Self { root: root.to_path_buf(), manifest, docs, fields, by_path, by_name })
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

    /// Ranked search. Mirrors `oxidize.py`: IDF-weighted field matching, with
    /// whole-word hits worth more than incidental substrings.
    pub fn search(&self, query: &str, sources: &[String], limit: usize) -> Vec<(f64, &Doc)> {
        let qterms = terms(query);
        if qterms.is_empty() {
            return Vec::new();
        }
        let phrase = query.trim().to_lowercase();

        let pool: Vec<usize> = (0..self.docs.len())
            .filter(|&i| sources.is_empty() || sources.contains(&self.docs[i].source))
            .collect();

        // Terms that appear on nearly every page carry almost no signal.
        let n = pool.len().max(1) as f64;
        let idf: HashMap<&str, f64> = qterms
            .iter()
            .map(|t| {
                let df = pool.iter().filter(|&&i| self.fields[i].any_contains(t)).count() as f64;
                (t.as_str(), (1.0 + n / (1.0 + df)).ln())
            })
            .collect();

        let mut scored: Vec<(f64, &Doc)> = pool
            .iter()
            .map(|&i| (self.score(i, &qterms, &phrase, &idf), &self.docs[i]))
            .filter(|(s, _)| *s > 0.0)
            .collect();
        scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
        scored.truncate(limit);
        scored
    }

    fn score(&self, i: usize, qterms: &[String], phrase: &str, idf: &HashMap<&str, f64>) -> f64 {
        let f = &self.fields[i];
        let doc = &self.docs[i];
        let mut s = 0.0;
        let mut matched = 0usize;

        for t in qterms {
            let w = idf.get(t.as_str()).copied().unwrap_or(1.0);
            let mut hit = false;
            for (blob, weight) in f.iter() {
                if blob.is_empty() || !blob.contains(t.as_str()) {
                    continue;
                }
                s += weight * w * if whole_word(blob, t) { 1.0 } else { 0.35 };
                hit = true;
            }
            if hit {
                matched += 1;
            }
        }

        if phrase.len() > 4 {
            if f.title.contains(phrase) {
                s += 25.0;
            } else if f.heads.contains(phrase) {
                s += 12.0;
            } else if f.summary.contains(phrase) {
                s += 6.0;
            }
        }
        if s > 0.0 {
            s *= 0.35 + 0.65 * (matched as f64 / qterms.len() as f64);
        }
        // Index and landing pages are rarely the answer.
        if doc.id.ends_with("index") || doc.kind == "module" {
            s *= 0.55;
        }
        s
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
        keywords: d.keywords.join(" ").to_lowercase(),
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

pub fn terms(query: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut cur = String::new();
    for ch in query.chars() {
        if ch.is_ascii_alphanumeric() || ch == '_' {
            cur.push(ch.to_ascii_lowercase());
        } else if !cur.is_empty() {
            push_term(&mut out, std::mem::take(&mut cur));
        }
    }
    if !cur.is_empty() {
        push_term(&mut out, cur);
    }
    out
}

fn push_term(out: &mut Vec<String>, t: String) {
    // A term must start with a letter or underscore, matching the Python side.
    if t.len() > 1 && !t.starts_with(|c: char| c.is_ascii_digit()) && !STOPWORDS.contains(&t.as_str())
    {
        out.push(t);
    }
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
