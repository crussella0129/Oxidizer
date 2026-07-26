#!/usr/bin/env python3
"""Oxidizer retrieval CLI — situational access to the Rust canon.

The corpus is roughly 3 million tokens. A single std page (``Vec``) is ~96k on
its own, which would eat half a context window to answer "what does retain do".
Every command here therefore returns a *slice* under an explicit token budget
and tells you what it withheld, so the agent can decide whether to spend more.

Commands:
    route     <question>        which domain contract to load, and what to run
    search    <query>           ranked hits across the corpus
    show      <doc-id>          one document, or one section of it
    explain   <E0502>           compiler error index entry
    api       <std::vec::Vec::retain>   one item or one method
    lint      <needless_range_loop>     one clippy lint
    diagnose  <file.rs|dir>     compile it, then retrieve docs for what broke
    manifest                    what is mirrored, and how fresh it is

Every command accepts --max-tokens (default 2000) and --json.
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_BUDGET = 2000

# Which sources answer which kind of question. Mirrors domains/*/CONTEXT.md;
# `route` uses this to point at a domain contract instead of guessing.
ROUTING: list[dict] = [
    {
        "domain": "01_diagnose",
        "sources": ["error-index", "book", "reference", "nomicon"],
        "triggers": [
            r"\bE\d{4}\b", r"borrow", r"borrowck", r"does not live long enough",
            r"cannot move out", r"moved value", r"lifetime", r"compile[r]? error",
            r"won'?t compile", r"doesn'?t compile", r"error\[", r"type mismatch",
            r"mismatched types", r"trait bound", r"not satisfied", r"why.*fail",
        ],
        "why": "A compile actually failed; the error index is authoritative.",
    },
    {
        "domain": "02_learn",
        "sources": ["book", "brown-book", "rust-by-example"],
        "triggers": [
            r"\bexplain\b", r"what is\b", r"how do(?:es)? .* work", r"\blearn\b",
            r"\bunderstand\b", r"\bteach\b", r"difference between", r"when should i",
            r"\bconcept\b", r"new to rust", r"\bintro",
        ],
        "why": "Conceptual understanding; the Book teaches, the Reference does not.",
    },
    {
        "domain": "03_api",
        "sources": ["std", "core", "alloc"],
        "triggers": [
            r"\bstd::", r"\bsignature\b", r"\bmethod\b", r"which function",
            r"\bapi\b", r"does .* have a", r"\breturn type\b", r"\btrait impl",
            r"\bVec\b|\bHashMap\b|\bOption\b|\bResult\b|\bString\b|\bIterator\b",
        ],
        "why": "API surface question; answer from signatures, not prose.",
    },
    {
        "domain": "04_spec",
        "sources": ["reference", "edition-guide"],
        "triggers": [
            r"\bis it legal\b", r"\bguarantee", r"\bspec\b", r"\bspecification\b",
            r"\bwell.?defined\b", r"\bexactly\b.*\bmean", r"\bsemantics\b",
            r"\bdrop order\b", r"\bcoercion\b", r"\bprecedence\b", r"\bedition\b",
        ],
        "why": "Normative question; only the Reference is binding.",
    },
    {
        "domain": "05_unsafe",
        "sources": ["nomicon", "reference", "std"],
        "triggers": [
            r"\bunsafe\b", r"\bUB\b", r"undefined behaviou?r", r"\bFFI\b",
            r"\braw pointer", r"\btransmute\b", r"\bvariance\b", r"\bPhantomData\b",
            r"\bSend\b|\bSync\b", r"\bMaybeUninit\b", r"extern \"C\"", r"\bmiri\b",
        ],
        "why": "Unsafe code has invariants the Book does not cover.",
    },
    {
        "domain": "06_idiom",
        "sources": ["lints", "style-guide", "cargo", "book"],
        "triggers": [
            r"\bidiomatic\b", r"\bclippy\b", r"\blint\b", r"\brefactor\b",
            r"\bcleaner?\b", r"\bbest practice", r"\bconvention\b", r"\bnaming\b",
            r"\bCargo\.toml\b", r"\bfeature flag", r"\bworkspace\b", r"\bcrate\b.*\bpublish",
        ],
        "why": "Style/idiom question; clippy encodes the community consensus.",
    },
    {
        "domain": "07_migrate",
        "sources": ["crp-phrasebook", "book", "nomicon", "reference"],
        "triggers": [
            r"\bC\+\+\b", r"\bport(?:ing)?\b", r"\bmigrat", r"\brewrite .* in rust",
            r"\bequivalent of\b", r"\bcoming from\b", r"\bin (?:C|Java|Go|Python)\b",
            r"\bshared_ptr\b|\bunique_ptr\b|\bstd::vector\b|\bRAII\b",
        ],
        "why": "Translation task; map source-language idiom to Rust idiom.",
    },
]

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "to", "of", "in", "on",
    "for", "and", "or", "it", "this", "that", "with", "as", "at", "by", "from",
    "how", "what", "why", "do", "does", "did", "can", "i", "my", "me", "you",
    "rust", "code", "use", "using", "get", "make",
}


# --------------------------------------------------------------------------
# corpus access


def corpus_dir() -> Path:
    if os.environ.get("OXIDIZER_CORPUS"):
        return Path(os.environ["OXIDIZER_CORPUS"])
    return Path(__file__).resolve().parents[3] / "corpus"


class Corpus:
    def __init__(self, root: Path):
        self.root = root
        if not (root / "MANIFEST.json").exists():
            die(f"no corpus at {root}\n"
                f"  build it with:  python3 {Path(__file__).parent}/mirror.py")
        self.manifest = json.loads((root / "MANIFEST.json").read_text())

    @functools.cached_property
    def docs(self) -> list[dict]:
        out: list[dict] = []
        for src in self.manifest["sources"]:
            idx = self.root / src["id"] / "INDEX.json"
            if idx.exists():
                out.extend(json.loads(idx.read_text())["docs"])
        return out

    @functools.cached_property
    def by_path(self) -> dict[str, dict]:
        """Lowercased path -> doc.

        ``std::vec`` (module) and ``std::Vec`` collide once case is folded, and
        a bare ``Vec`` should land on the struct, not the module that holds it.
        Concrete items therefore win collisions.
        """
        out: dict[str, dict] = {}
        for d in self.docs:
            if not d.get("path"):
                continue
            key = d["path"].lower()
            prev = out.get(key)
            if prev is None or (prev.get("kind") == "module"
                                and d.get("kind") != "module"):
                out[key] = d
        return out

    @functools.cached_property
    def by_name(self) -> dict[str, list[dict]]:
        """Final path segment -> docs, concrete items before modules."""
        out: dict[str, list[dict]] = {}
        rank = {"struct": 0, "enum": 0, "trait": 0, "primitive": 1, "fn": 2,
                "macro": 2, "type": 3, "constant": 4, "static": 4, "union": 4,
                "keyword": 5, "module": 9}
        for d in self.docs:
            if d.get("path"):
                out.setdefault(d["path"].split("::")[-1].lower(), []).append(d)
        for docs in out.values():
            docs.sort(key=lambda d: (rank.get(d.get("kind"), 6), len(d["path"])))
        return out

    def read(self, doc: dict) -> str:
        text = (self.root / doc["source"] / doc["file"]).read_text(encoding="utf-8")
        return re.sub(r"^<!-- oxidizer:.*?-->\n\n", "", text, flags=re.S)

    def find(self, doc_id: str, source: str | None = None) -> dict | None:
        want = doc_id.lower()
        cands = [d for d in self.docs
                 if (source is None or d["source"] == source)
                 and (d["id"].lower() == want
                      or f"{d['source']}/{d['id']}".lower() == want)]
        return cands[0] if cands else None


# --------------------------------------------------------------------------
# helpers


def die(msg: str) -> None:
    print(f"oxidize: {msg}", file=sys.stderr)
    sys.exit(1)


def tokens_of(text: str) -> int:
    return max(1, len(text) // 4)


def terms(query: str) -> list[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z_0-9]+", query.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def budget_text(text: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate on a paragraph boundary so the tail is never a half sentence."""
    limit = max_tokens * 4
    if len(text) <= limit:
        return text, False
    cut = text.rfind("\n\n", 0, limit)
    if cut < limit // 2:
        cut = limit
    return text[:cut].rstrip(), True


def split_sections(md: str) -> list[tuple[int, str, str]]:
    """(level, heading, body) for each heading in a document."""
    parts: list[tuple[int, str, str]] = []
    matches = list(re.finditer(r"^(#{1,6})\s+(.*)$", md, re.M))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        parts.append((len(m.group(1)), m.group(2).strip(), md[m.end():end].strip()))
    return parts


def emit(payload: dict, text: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(text)


# --------------------------------------------------------------------------
# search


# Boilerplate rustdoc emits as headings on essentially every page. Left in, a
# query for "trait objects" scores every std type equally on the word "trait".
_HEADING_NOISE = re.compile(
    r"\b(?:trait implementations|implementations|auto trait implementations|"
    r"blanket implementations|methods from deref|examples|panics|errors|safety|"
    r"required methods|provided methods|implementors|members|aliased type)\b")


def doc_fields(doc: dict) -> dict[str, str]:
    heads = " ".join(doc.get("headings", [])).lower()
    title = doc.get("title", "").lower()
    if doc.get("path"):
        # rustdoc titles are "struct std::mem::Assume". Left intact, the literal
        # kind word makes every std type a strong hit for any query containing
        # "struct" or "trait", which is almost never what was meant.
        title = re.sub(r"^(?:struct|enum|trait|fn|macro|type|constant|static|"
                       r"union|primitive|keyword|module|derive|attr)\s+", "", title)
    return {
        "title": title,
        "path": (doc.get("path") or "").lower(),
        "doc_id": doc["id"].lower().replace("/", " ").replace("-", " ").replace("_", " "),
        "heads": _HEADING_NOISE.sub(" ", heads),
        "members": " ".join(doc.get("members", [])).lower(),
        "summary": (doc.get("summary") or "").lower(),
        "keywords": " ".join(doc.get("keywords", [])),
    }


_FIELD_WEIGHT = {"title": 10.0, "path": 8.0, "doc_id": 5.0,
                 "heads": 3.0, "members": 6.0, "summary": 2.0, "keywords": 1.5}


def compute_idf(qterms: list[str], fields: list[dict[str, str]]) -> dict[str, float]:
    """Inverse document frequency for the query terms over the search pool.

    Without this a word like "trait" or "iterator" — which literally appears on
    every page of std — outweighs the rare word that actually identifies what
    the user is asking about.
    """
    n = max(1, len(fields))
    idf: dict[str, float] = {}
    for t in qterms:
        df = sum(1 for f in fields if any(t in blob for blob in f.values()))
        idf[t] = math.log(1 + n / (1 + df))
    return idf


def score(doc: dict, qterms: list[str], phrase: str,
          idf: dict[str, float], fields: dict[str, str] | None = None) -> float:
    f = fields or doc_fields(doc)

    s = 0.0
    matched = 0
    for t in qterms:
        w = idf.get(t, 1.0)
        hit = False
        for name, weight in _FIELD_WEIGHT.items():
            blob = f[name]
            if not blob or t not in blob:
                continue
            # Whole-word matches are worth more than incidental substrings
            # ("map" inside "unwrap_or", "vec" inside "vecdeque").
            exact = re.search(rf"(?:^|[^a-z0-9_]){re.escape(t)}(?:[^a-z0-9_]|$)", blob)
            s += weight * w * (1.0 if exact else 0.35)
            hit = True
        if hit:
            matched += 1

    if phrase and len(phrase) > 4:
        if phrase in f["title"]:
            s += 25
        elif phrase in f["heads"]:
            s += 12
        elif phrase in f["summary"]:
            s += 6

    if s and qterms:
        # Reward covering more of the query rather than hammering one term.
        s *= 0.35 + 0.65 * (matched / len(qterms))
    # Index/landing pages are rarely the answer.
    if doc["id"].endswith("index") or doc.get("kind") == "module":
        s *= 0.55
    return s


def cmd_search(c: Corpus, a) -> None:
    qterms = terms(a.query)
    if not qterms:
        die("query has no searchable terms")
    phrase = a.query.lower().strip()
    pool = [d for d in c.docs if not a.source or d["source"] in a.source]
    if not pool:
        die(f"no documents for source(s): {', '.join(a.source)}")

    fields = [doc_fields(d) for d in pool]
    idf = compute_idf(qterms, fields)
    ranked = sorted(((score(d, qterms, phrase, idf, f), d)
                     for d, f in zip(pool, fields)), key=lambda x: -x[0])
    hits = [(s, d) for s, d in ranked if s > 0][: a.limit]
    if not hits:
        emit({"query": a.query, "hits": []},
             f"No matches for {a.query!r}. Try fewer or more general terms.", a.json)
        return

    payload = {
        "query": a.query,
        "hits": [{
            "rank": i, "score": round(s, 1), "source": d["source"], "id": d["id"],
            "title": d["title"], "path": d.get("path"), "tokens": d["tokens"],
            "url": d["url"], "summary": d.get("summary", ""),
        } for i, (s, d) in enumerate(hits, 1)],
    }
    lines = [f"{len(hits)} hit(s) for {a.query!r}\n"]
    for h in payload["hits"]:
        lines.append(f"[{h['rank']}] {h['title']}   ({h['source']}, ~{h['tokens']} tok)")
        lines.append(f"    show: oxidize show {h['source']}/{h['id']}")
        if h["summary"]:
            lines.append(f"    {h['summary'][:220]}")
        lines.append(f"    {h['url']}\n")
    lines.append("Retrieve one before answering — search shows summaries, not sources.")
    emit(payload, "\n".join(lines), a.json)


# --------------------------------------------------------------------------
# show / explain / api / lint


def cmd_show(c: Corpus, a) -> None:
    src, _, ident = a.doc_id.partition("/")
    doc = c.find(a.doc_id) or c.find(ident, src) or c.find(a.doc_id.replace("/", "", 1))
    if doc is None:
        matches = [d for d in c.docs if a.doc_id.lower() in d["id"].lower()][:5]
        hint = "\n".join(f"  {d['source']}/{d['id']}" for d in matches)
        die(f"no document {a.doc_id!r}" + (f"\nDid you mean:\n{hint}" if hint else ""))

    md = c.read(doc)
    section_used = None
    if a.section:
        want = a.section.lower()
        sections = split_sections(md)
        picked = [s for s in sections if want in s[1].lower()]
        if not picked:
            avail = ", ".join(s[1] for s in sections[:25])
            die(f"no section matching {a.section!r} in {doc['id']}\nSections: {avail}")
        lvl, head, body = picked[0]
        section_used = head
        md = "#" * lvl + " " + head + "\n\n" + body

    text, truncated = budget_text(md, a.max_tokens)
    payload = {"source": doc["source"], "id": doc["id"], "title": doc["title"],
               "url": doc["url"], "section": section_used,
               "tokens_returned": tokens_of(text), "tokens_total": doc["tokens"],
               "truncated": truncated, "content": text}
    header = (f"# {doc['title']}\nsource: {doc['source']} | {doc['url']}\n"
              f"returned ~{tokens_of(text)} of ~{doc['tokens']} tokens\n"
              + ("-" * 60) + "\n")
    footer = ""
    if truncated:
        heads = [h for _, h, _ in split_sections(md)][:20]
        footer = ("\n\n" + "-" * 60 +
                  f"\n[truncated at {a.max_tokens} tokens]\n"
                  f"Sections available: {', '.join(heads) if heads else '(none)'}\n"
                  f"Narrow with: oxidize show {doc['source']}/{doc['id']} "
                  f"--section '<heading>'  or raise --max-tokens")
    emit(payload, header + text + footer, a.json)


def cmd_explain(c: Corpus, a) -> None:
    code = a.code.upper()
    if not re.fullmatch(r"E\d{4}", code):
        m = re.search(r"E\d{4}", code)
        if not m:
            die(f"{a.code!r} is not a compiler error code (expected e.g. E0502)")
        code = m.group(0)
    doc = c.find(code, "error-index")
    if doc is None:
        # rustc knows codes the mirrored index may lag behind on.
        try:
            out = subprocess.run(["rustc", "--explain", code], capture_output=True,
                                 text=True, check=True).stdout
            emit({"code": code, "content": out, "origin": "rustc --explain"},
                 out, a.json)
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            die(f"unknown error code {code}")
    md = c.read(doc)
    text, truncated = budget_text(md, a.max_tokens)
    # Point at the prose that explains the rule the compiler enforced. The
    # error index says what went wrong; the Book and Reference say why.
    prose = [d for d in c.docs
             if d["source"] in ("book", "reference", "nomicon", "brown-book")]
    qterms = terms(doc.get("summary", ""))[:8]
    related = []
    if qterms and prose:
        pfields = [doc_fields(d) for d in prose]
        pidf = compute_idf(qterms, pfields)
        scored = sorted(((score(d, qterms, "", pidf, f), d)
                         for d, f in zip(prose, pfields)), key=lambda x: -x[0])
        related = [d for s, d in scored[:3] if s > 0]
    payload = {"code": code, "url": doc["url"], "truncated": truncated,
               "tokens_returned": tokens_of(text), "content": text,
               "related": [{"id": f"{d['source']}/{d['id']}", "title": d["title"]}
                           for d in related]}
    tail = ""
    if related:
        tail = "\n\nRelated background:\n" + "\n".join(
            f"  oxidize show {r['id']}   # {r['title']}" for r in payload["related"])
    emit(payload, f"{text}\n\nSource: {doc['url']}{tail}", a.json)


def cmd_api(c: Corpus, a) -> None:
    query = a.path.strip().replace(".", "::").strip(":")
    parts = [p for p in query.split("::") if p]
    if not parts:
        die("empty API path")

    # Split the query into "the item" and "a member of it" at every plausible
    # point, longest item first. A candidate is only accepted if it actually
    # carries the requested member — that single check is what keeps
    # `Option::map` on the Option enum instead of on std::iter::Map, and
    # `Vec` on the struct instead of the vec! macro or the std::vec module.
    def candidates_for(prefix: list[str]) -> list[dict]:
        low = "::".join(prefix).lower()
        found: list[dict] = []
        for key in (low, f"std::{low}"):
            hit = c.by_path.get(key)
            if hit is not None and hit not in found:
                found.append(hit)
        for hit in c.by_name.get(prefix[-1].lower(), []):
            # Only accept a name match whose path actually ends with the
            # qualifiers the caller gave (so `vec::Vec` won't match `foo::Vec`).
            tail = "::".join(prefix).lower()
            if hit["path"].lower().endswith(tail) and hit not in found:
                found.append(hit)
        rank = {"struct": 0, "enum": 0, "trait": 0, "primitive": 1, "fn": 2,
                "macro": 3, "type": 3, "constant": 4, "static": 4, "union": 4,
                "keyword": 5, "module": 9}
        return sorted(found, key=lambda d: (rank.get(d.get("kind"), 6),
                                            len(d["path"])))

    doc = None
    member = None
    fallback = None
    for cut in range(len(parts), 0, -1):
        remainder = parts[cut:]
        for cand in candidates_for(parts[:cut]):
            if not remainder:
                doc, member = cand, None
                break
            names = {m.lower() for m in cand.get("members", [])}
            if remainder[0].lower() in names:
                doc, member = cand, "::".join(remainder)
                break
            if fallback is None:
                fallback = (cand, "::".join(remainder))
        if doc is not None:
            break

    if doc is None and fallback is not None:
        doc, member = fallback
    if doc is None:
        die(f"no std item matching {a.path!r}\n"
            f"  try: oxidize search '{a.path}' --source std")

    md = c.read(doc)
    if member:
        sections = split_sections(md)
        exact = [s for s in sections if s[1].lower() == member.lower()]
        loose = [s for s in sections if member.lower() in s[1].lower()]
        picked = exact or loose
        if not picked:
            names = doc.get("members", [])[:40]
            die(f"{doc['path']} has no member {member!r}\n"
                f"Members: {', '.join(names) if names else '(none indexed)'}")
        lvl, head, body = picked[0]
        md = f"# {doc['path']}::{head}\n\n{body}"

    text, truncated = budget_text(md, a.max_tokens)
    payload = {"path": doc["path"], "kind": doc["kind"], "member": member,
               "url": doc["url"] + (f"#method.{member}" if member else ""),
               "tokens_returned": tokens_of(text), "tokens_total": doc["tokens"],
               "truncated": truncated, "content": text}
    footer = ""
    if truncated and not member:
        footer = (f"\n\n[truncated — {doc['path']} is ~{doc['tokens']} tokens]\n"
                  f"Ask for one member instead: oxidize api {doc['path']}::<method>\n"
                  f"Members: {', '.join(doc.get('members', [])[:30])}")
    emit(payload, f"{text}\n\nSource: {payload['url']}{footer}", a.json)


def cmd_lint(c: Corpus, a) -> None:
    # Lints are written with underscores but printed by the compiler with
    # dashes, and may or may not carry the `clippy::` tool prefix.
    raw = a.name.strip().replace("-", "_")
    lints = [d for d in c.docs if d["source"] == "lints"]
    if not lints:
        die("no lint index in this corpus — rebuild with mirror.py")

    bare = raw.split("::")[-1]
    doc = next((d for d in lints if d["path"].lower() == raw.lower()), None)
    if doc is None:
        doc = next((d for d in lints
                    if d["path"].split("::")[-1].lower() == bare.lower()), None)
    if doc is None:
        near = [d["path"] for d in lints if bare.lower() in d["path"].lower()][:8]
        die(f"no lint named {a.name!r}"
            + (f"\nDid you mean: {', '.join(near)}" if near else
               f"\n  try: oxidize search '{bare}' --source lints"))

    md = c.read(doc)
    text, truncated = budget_text(md, a.max_tokens)
    emit({"lint": doc["path"], "level": doc.get("level"), "tool": doc.get("tool"),
          "url": doc["url"], "truncated": truncated, "content": text},
         f"{text}\nSource: {doc['url']}", a.json)


# --------------------------------------------------------------------------
# route


def cmd_route(c: Corpus, a) -> None:
    q = a.question.lower()
    scored: list[tuple[float, dict]] = []
    for rule in ROUTING:
        n = sum(1 for pat in rule["triggers"] if re.search(pat, q, re.I))
        if n:
            scored.append((n, rule))
    scored.sort(key=lambda x: -x[0])

    available = {s["id"] for s in c.manifest["sources"]}
    if scored:
        picked = [r for _, r in scored[:2]]
    else:
        picked = [next(r for r in ROUTING if r["domain"] == "02_learn")]

    payload = {"question": a.question, "domains": []}
    lines = [f"Question: {a.question}\n"]
    for rule in picked:
        srcs = [s for s in rule["sources"] if s in available]
        missing = [s for s in rule["sources"] if s not in available]
        payload["domains"].append({
            "domain": rule["domain"], "why": rule["why"],
            "sources": srcs, "unavailable": missing,
            "contract": f"domains/{rule['domain']}/CONTEXT.md",
        })
        lines.append(f"-> load  domains/{rule['domain']}/CONTEXT.md")
        lines.append(f"   why:  {rule['why']}")
        lines.append(f"   then: oxidize search '{a.question[:60]}' "
                     f"--source {' '.join(srcs) if srcs else '<none mirrored>'}")
        if missing:
            lines.append(f"   note: {', '.join(missing)} not in this corpus "
                         f"(rebuild with --online / --include)")
        lines.append("")

    codes = re.findall(r"\bE\d{4}\b", a.question, re.I)
    for code in codes:
        lines.append(f"   direct: oxidize explain {code.upper()}")
        payload.setdefault("direct", []).append(f"explain {code.upper()}")
    lines.append("Load exactly one domain contract. Loading all seven is the "
                 "failure mode this skill exists to prevent.")
    emit(payload, "\n".join(lines), a.json)


# --------------------------------------------------------------------------
# diagnose


# "aborting due to N previous errors" and "N warnings emitted" are the
# compiler's own summary lines. They carry no code and no span, and counting
# them as diagnostics inflates every error count by one.
_SUMMARY_RE = re.compile(r"^(?:aborting due to|\d+ (?:warning|error)s? emitted)")


def _rustc_diagnostics(target: Path, edition: str,
                       use_clippy: bool) -> tuple[list[dict], str]:
    """Compile `target` and return structured diagnostics."""
    driver = "clippy-driver" if use_clippy else "rustc"
    manifest = None
    for parent in [target if target.is_dir() else target.parent,
                   *target.resolve().parents]:
        if (parent / "Cargo.toml").exists():
            manifest = parent / "Cargo.toml"
            break

    diags: list[dict] = []
    if manifest is not None:
        sub = ["clippy"] if use_clippy else ["check"]
        cmd = ["cargo", *sub, "--message-format=json", "--quiet",
               "--manifest-path", str(manifest)]
        how = f"cargo {sub[0]} ({manifest})"
        proc = subprocess.run(cmd, capture_output=True, text=True)
        for line in proc.stdout.splitlines():
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("reason") == "compiler-message":
                diags.append(msg["message"])
    else:
        if target.is_dir():
            die(f"{target} is a directory with no Cargo.toml — pass a .rs file")
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [driver, "--edition", edition, "--error-format=json",
                   "--emit=metadata", "--crate-type", "lib",
                   "-o", str(Path(tmp) / "out.rmeta"), str(target)]
            if use_clippy:
                cmd += ["-W", "clippy::all"]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True)
            except FileNotFoundError:
                die(f"{driver} not found"
                    + (" — install it with `rustup component add clippy`"
                       if use_clippy else ""))
        how = f"{driver} --edition {edition}"
        for line in proc.stderr.splitlines():
            try:
                diags.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return [d for d in diags
            if d.get("message") and not _SUMMARY_RE.match(d["message"])], how


def cmd_diagnose(c: Corpus, a) -> None:
    target = Path(a.target)
    if not target.exists():
        die(f"no such path: {target}")

    diags, how = _rustc_diagnostics(target, a.edition, a.clippy)
    errors = [d for d in diags if d.get("level") == "error"]
    warnings = [d for d in diags if d.get("level") == "warning"]

    def code_of(d: dict) -> str | None:
        return (d.get("code") or {}).get("code")

    seen = list(dict.fromkeys(x for d in errors if (x := code_of(d))))
    lint_names = list(dict.fromkeys(x for d in warnings if (x := code_of(d))))

    payload = {
        "target": str(target), "compiler": how,
        "error_count": len(errors), "warning_count": len(warnings),
        "codes": seen, "lints": lint_names, "diagnostics": [], "docs": [],
    }
    lines = [f"# Diagnosis: {target}", f"compiler: {how}",
             f"{len(errors)} error(s), {len(warnings)} warning(s)"]
    if seen:
        lines.append(f"codes: {', '.join(seen)}")
    if lint_names:
        lines.append(f"lints: {', '.join(lint_names)}")
    lines.append("-" * 60)

    def location(d: dict) -> str:
        spans = [s for s in d.get("spans", []) if s.get("is_primary")]
        if not spans:
            return ""
        s = spans[0]
        return f"{Path(s['file_name']).name}:{s['line_start']}:{s['column_start']}"

    if not errors:
        lines.append("Compiles clean."
                     if not warnings else "No errors — warnings only.")
        for w in warnings[: a.limit]:
            name = code_of(w)
            loc = location(w)
            lines.append(f"\nwarning{f'[{name}]' if name else ''}: {w['message']}")
            if loc:
                lines.append(f"  at {loc}")
            for child in w.get("children", [])[:2]:
                if child.get("message"):
                    lines.append(f"  {child['level']}: {child['message']}")
            payload["diagnostics"].append(
                {"level": "warning", "code": name, "message": w["message"], "at": loc,
                 "help": [ch["message"] for ch in w.get("children", [])[:2]]})

        if lint_names:
            per = max(120, a.max_tokens // max(1, len(lint_names)))
            lines.append("\n" + "=" * 60 + "\nCANON\n" + "=" * 60)
            for name in lint_names:
                doc = next((d for d in c.docs if d["source"] == "lints"
                            and d["path"].lower() == name.lower()), None)
                if doc is None:
                    continue
                text, _ = budget_text(c.read(doc), per)
                lines.append(f"\n{text}\nSource: {doc['url']}")
                payload["docs"].append({"lint": name, "url": doc["url"],
                                        "content": text})
            lines.append("\nNext: load domains/06_idiom/CONTEXT.md")
            payload["domain"] = "06_idiom"
        elif not a.clippy:
            lines.append("\nFor idiom review too, re-run with --clippy.")
        emit(payload, "\n".join(lines), a.json)
        return

    for d in errors[: a.limit]:
        code = code_of(d)
        loc = location(d)
        lines.append(f"\nerror{f'[{code}]' if code else ''}: {d['message']}")
        if loc:
            lines.append(f"  at {loc}")
        for child in d.get("children", [])[:3]:
            if child.get("message"):
                lines.append(f"  {child['level']}: {child['message']}")
        payload["diagnostics"].append(
            {"level": "error", "code": code, "message": d["message"], "at": loc,
             "help": [ch["message"] for ch in d.get("children", [])[:3]]})

    # Attach the canon entry for each distinct code, within budget.
    per_code = max(200, a.max_tokens // max(1, len(seen)))
    lines.append("\n" + "=" * 60 + "\nCANON\n" + "=" * 60)
    for code in seen:
        doc = c.find(code, "error-index")
        if doc is None:
            continue
        text, truncated = budget_text(c.read(doc), per_code)
        lines.append(f"\n{text}")
        lines.append(f"Source: {doc['url']}")
        payload["docs"].append({"code": code, "url": doc["url"], "content": text,
                                "truncated": truncated})

    route_q = " ".join(seen) + " " + " ".join(d["message"] for d in errors[:2])
    rule = next((r for r in ROUTING
                 if any(re.search(p, route_q, re.I) for p in r["triggers"])), None)
    if rule:
        lines.append(f"\nNext: load domains/{rule['domain']}/CONTEXT.md")
        payload["domain"] = rule["domain"]
    emit(payload, "\n".join(lines), a.json)


def cmd_manifest(c: Corpus, a) -> None:
    m = c.manifest
    tc = m.get("toolchain", {})
    payload = {"corpus": str(c.root), "generated_at": m.get("generated_at"),
               "toolchain": tc, "sources": m["sources"], "totals": m["totals"]}
    lines = [f"corpus:    {c.root}",
             f"built:     {m.get('generated_at')}",
             f"toolchain: {tc.get('rustc_version')}",
             f"totals:    {m['totals']['docs']} docs, "
             f"~{m['totals']['tokens'] // 1000}k tokens", "",
             f"{'source':16s} {'docs':>6s} {'tokens':>9s}  role"]
    for s in m["sources"]:
        lines.append(f"{s['id']:16s} {s['doc_count']:6d} "
                     f"{s['total_tokens'] // 1000:8d}k  {s['role'][:70]}")
    try:
        cur = subprocess.run(["rustc", "--version"], capture_output=True,
                             text=True, check=True).stdout.strip()
        if cur != tc.get("rustc_version"):
            lines.append(f"\nSTALE: toolchain is now {cur}. Re-run mirror.py.")
            payload["stale"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    emit(payload, "\n".join(lines), a.json)


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="oxidize", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_BUDGET)
    ap.add_argument("--json", action="store_true")

    # The same flags are accepted after the subcommand, which is where anyone
    # would naturally reach for them. SUPPRESS keeps the subparser from
    # re-applying its defaults over a value given before the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--corpus", type=Path, default=argparse.SUPPRESS)
    common.add_argument("--max-tokens", type=int, default=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("route", parents=[common])
    p.add_argument("question"); p.set_defaults(fn=cmd_route)

    p = sub.add_parser("search", parents=[common])
    p.add_argument("query")
    p.add_argument("--source", nargs="*", default=[])
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("show", parents=[common])
    p.add_argument("doc_id")
    p.add_argument("--section", default=None)
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("explain", parents=[common])
    p.add_argument("code"); p.set_defaults(fn=cmd_explain)
    p = sub.add_parser("api", parents=[common])
    p.add_argument("path"); p.set_defaults(fn=cmd_api)
    p = sub.add_parser("lint", parents=[common])
    p.add_argument("name"); p.set_defaults(fn=cmd_lint)

    p = sub.add_parser("diagnose", parents=[common])
    p.add_argument("target")
    p.add_argument("--limit", type=int, default=6)
    p.add_argument("--edition", default="2021", choices=["2015", "2018", "2021", "2024"])
    p.add_argument("--clippy", action="store_true",
                   help="run clippy instead of rustc, for idiom review")
    p.set_defaults(fn=cmd_diagnose)

    p = sub.add_parser("manifest", parents=[common]); p.set_defaults(fn=cmd_manifest)

    args = ap.parse_args()
    corpus = Corpus(args.corpus or corpus_dir())
    args.fn(corpus, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
