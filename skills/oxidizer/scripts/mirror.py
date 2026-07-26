#!/usr/bin/env python3
"""Build the Oxidizer corpus (MWP Layer 3) from the Rust canon.

The canon is not scraped by default. ``rustup component add rust-docs`` ships
the Book, Rust By Example, the Reference, the Nomicon, the std API, the Cargo
book, the clippy lint index, the error index, and the edition/style guides as
local HTML, pinned to the exact toolchain the user compiles with. Reading those
is both faster and *more correct* than fetching doc.rust-lang.org, which always
describes stable-latest and will quietly disagree with an older pinned project.

Two canon sources have no offline equivalent and are fetched over HTTP when
``--online`` is passed: the Brown University interactive fork of the Book and
the Brown C++-to-Rust phrasebook.

Usage:
    python3 mirror.py                     # offline canon, default source set
    python3 mirror.py --include core,alloc
    python3 mirror.py --online            # add the two Brown sources
    python3 mirror.py --check             # report staleness, write nothing
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import (  # noqa: E402
    estimate_tokens,
    html_to_markdown,
    rustdoc_kind_and_path,
    rustdoc_members,
)

SCHEMA_VERSION = 2

# id -> (local dir under the rust-docs html root, kind, title, upstream base, default?)
SOURCES: dict[str, dict] = {
    "book": {
        "dir": "book", "kind": "mdbook", "default": True,
        "title": "The Rust Programming Language (\"The Book\")",
        "url": "https://doc.rust-lang.org/book/",
        "role": "Teaching narrative. Best first stop for a concept a human is learning.",
    },
    "rust-by-example": {
        "dir": "rust-by-example", "kind": "mdbook", "default": True,
        "title": "Rust By Example",
        "url": "https://doc.rust-lang.org/rust-by-example/",
        "role": "Runnable examples. Best when the answer is 'show me the code'.",
    },
    "reference": {
        "dir": "reference", "kind": "mdbook", "default": True,
        "title": "The Rust Reference",
        "url": "https://doc.rust-lang.org/reference/",
        "role": "Normative language semantics. Use to settle 'is this legal / what "
                "exactly does this mean' questions.",
    },
    "nomicon": {
        "dir": "nomicon", "kind": "mdbook", "default": True,
        "title": "The Rustonomicon",
        "url": "https://doc.rust-lang.org/nomicon/",
        "role": "Unsafe Rust, UB, variance, FFI, and the invariants unsafe code must uphold.",
    },
    "error-index": {
        "dir": "error_codes", "kind": "mdbook", "default": True,
        "title": "Rust Compiler Error Index",
        "url": "https://doc.rust-lang.org/error_codes/",
        "role": "One page per E-code. The single highest-value source when a "
                "compile actually failed.",
    },
    "std": {
        "dir": "std", "kind": "rustdoc", "default": True,
        "title": "Rust Standard Library (crate std)",
        "url": "https://doc.rust-lang.org/std/",
        "role": "API surface: types, traits, methods, signatures.",
    },
    "cargo": {
        "dir": "cargo", "kind": "mdbook", "default": True,
        "title": "The Cargo Book",
        "url": "https://doc.rust-lang.org/cargo/",
        "role": "Manifests, features, workspaces, profiles, publishing.",
    },
    "clippy": {
        "dir": "clippy", "kind": "mdbook", "default": True,
        "title": "Clippy Lint Documentation",
        "url": "https://doc.rust-lang.org/clippy/",
        "role": "Idiom enforcement: what each lint wants and why.",
    },
    "edition-guide": {
        "dir": "edition-guide", "kind": "mdbook", "default": True,
        "title": "The Rust Edition Guide",
        "url": "https://doc.rust-lang.org/edition-guide/",
        "role": "What changed between editions and how to migrate.",
    },
    "style-guide": {
        "dir": "style-guide", "kind": "mdbook", "default": True,
        "title": "The Rust Style Guide",
        "url": "https://doc.rust-lang.org/style-guide/",
        "role": "Formatting and naming conventions.",
    },
    # Opt-in: large, and std re-exports most of what matters from core/alloc.
    "core": {
        "dir": "core", "kind": "rustdoc", "default": False,
        "title": "Rust Core Library (crate core)",
        "url": "https://doc.rust-lang.org/core/",
        "role": "no_std API surface.",
    },
    "alloc": {
        "dir": "alloc", "kind": "rustdoc", "default": False,
        "title": "Rust Alloc Library (crate alloc)",
        "url": "https://doc.rust-lang.org/alloc/",
        "role": "Allocation-aware collections without std.",
    },
    "embedded-book": {
        "dir": "embedded-book", "kind": "mdbook", "default": False,
        "title": "The Embedded Rust Book",
        "url": "https://doc.rust-lang.org/embedded-book/",
        "role": "Bare-metal and embedded targets.",
    },
    "unstable-book": {
        "dir": "unstable-book", "kind": "mdbook", "default": False,
        "title": "The Unstable Book",
        "url": "https://doc.rust-lang.org/unstable-book/",
        "role": "Nightly-only features and their tracking issues.",
    },
}

ONLINE_SOURCES: dict[str, dict] = {
    "brown-book": {
        "kind": "online", "title": "The Rust Book — Brown University Interactive Fork",
        "url": "https://rust-book.cs.brown.edu/",
        "role": "The Book plus ownership-inspector diagrams and quizzes. Prefer over "
                "'book' when the user is stuck on *why* the borrow checker rejected "
                "something conceptually.",
        "max_pages": 300,
    },
    "crp-phrasebook": {
        "kind": "online", "title": "Brown C++-to-Rust Phrasebook",
        "url": "https://cel.cs.brown.edu/crp/",
        "role": "Side-by-side C++ idiom -> Rust idiom translation. The entry point for "
                "porting work.",
        "max_pages": 200,
    },
}

SKIP_FILE_RE = re.compile(
    r"(?:^|/)(?:print|SUMMARY|404|not_found|help|settings|all|search-index"
    r"|toc|index-page)\.html$"
)

# The shipped docs carry a lot of redirect shims and retired-edition notices.
# They rank well (short, on-topic titles) while containing no answer at all, so
# they are dropped at mirror time rather than filtered at query time.
STUB_RE = re.compile(
    r"redirecting to"
    r"|is no longer distributed with rust"
    r"|has moved to"
    r"|this (?:chapter|section|page) (?:has )?moved"
    r"|you may want to check out the current version",
    re.I,
)
STUB_MAX_TOKENS = 200

# Titles and headings alone miss body-only vocabulary — "shared_ptr" appears
# nowhere in the phrasebook's headings, only in its prose. Storing the most
# distinctive body terms per document keeps search useful without carrying a
# full inverted index (which would be an order of magnitude larger on disk).
KEYWORD_LIMIT = 80
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_COMMON = {
    "the", "and", "for", "that", "this", "with", "you", "are", "not", "can",
    "will", "have", "has", "but", "all", "any", "its", "from", "when", "which",
    "what", "how", "why", "into", "than", "then", "them", "they", "your", "our",
    "use", "used", "using", "one", "two", "also", "more", "most", "some", "such",
    "only", "other", "same", "each", "here", "there", "these", "those", "would",
    "could", "should", "must", "may", "might", "does", "did", "was", "were",
    "been", "being", "let", "value", "values", "type", "types", "example",
    "examples", "code", "rust", "see", "note", "like", "want", "need", "make",
    "get", "set", "new", "first", "last", "case", "way", "time", "run",
}


def body_keywords(md: str, limit: int = KEYWORD_LIMIT) -> list[str]:
    """Most distinctive words in a document body, by frequency.

    Identifier-shaped tokens (snake_case, CamelCase) are always kept: they are
    exactly the terms someone searches for and are rare enough that frequency
    ranking alone would sometimes drop them.
    """
    counts: dict[str, int] = {}
    for w in _WORD_RE.findall(md):
        lw = w.lower()
        if len(lw) < 3 or lw in _COMMON:
            continue
        counts[lw] = counts.get(lw, 0) + 1
    identifiers = {w.lower() for w in _WORD_RE.findall(md)
                   if ("_" in w and len(w) > 3)
                   or (len(w) > 3 and not w.islower() and not w.isupper())}
    ranked = sorted(counts, key=lambda w: -counts[w])
    keep = [w for w in ranked if w in identifiers][: limit // 2]
    for w in ranked:
        if len(keep) >= limit:
            break
        if w not in keep:
            keep.append(w)
    return sorted(keep)


# --------------------------------------------------------------------------
# toolchain discovery


def rust_doc_root() -> Path | None:
    if os.environ.get("OXIDIZER_RUST_DOCS"):
        p = Path(os.environ["OXIDIZER_RUST_DOCS"])
        return p if p.is_dir() else None
    try:
        sysroot = subprocess.run(
            ["rustc", "--print", "sysroot"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    root = Path(sysroot) / "share" / "doc" / "rust" / "html"
    return root if root.is_dir() else None


def toolchain_info() -> dict:
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  check=True).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
    version = run(["rustc", "--version"]) or "unknown"
    m = re.search(r"rustc (\d+\.\d+\.\d+)", version)
    return {
        "rustc_version": version,
        "semver": m.group(1) if m else None,
        "host": run(["rustc", "-vV"]) and next(
            (l.split(": ", 1)[1] for l in run(["rustc", "-vV"]).splitlines()
             if l.startswith("host: ")), None),
        "sysroot": run(["rustc", "--print", "sysroot"]),
    }


# --------------------------------------------------------------------------
# conversion workers


def _convert_page(args: tuple) -> dict | None:
    """Worker: one HTML file -> one markdown doc + index entry."""
    src_id, kind, html_root_s, rel, out_dir_s, url_base = args
    html_path = Path(html_root_s) / rel
    out_dir = Path(out_dir_s)
    try:
        raw = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    md, headings = html_to_markdown(raw)
    if len(md.strip()) < 40:
        return None
    if estimate_tokens(md) < STUB_MAX_TOKENS and STUB_RE.search(md):
        return None

    doc_id = rel[: -len(".html")].replace("\\", "/")
    entry: dict = {
        "id": doc_id,
        "source": src_id,
        "title": headings[0][1] if headings else doc_id.rsplit("/", 1)[-1],
        "headings": [h for _, h in headings[:40]],
        "url": urllib.parse.urljoin(url_base, rel.replace("\\", "/")),
        "tokens": estimate_tokens(md),
    }

    if kind == "rustdoc":
        kp = rustdoc_kind_and_path(rel)
        if kp is None:
            return None
        # rel is relative to the crate dir, so the crate name has to go back on:
        # "vec/struct.Vec.html" describes std::vec::Vec, not vec::Vec.
        entry["kind"] = kp[0]
        entry["path"] = f"{src_id}::{kp[1]}" if kp[1] else src_id
        members = rustdoc_members(raw)
        if members:
            entry["members"] = [m["name"] for m in members]
            md += "\n\n## Members\n\n"
            for mem in members:
                md += f"\n### {mem['name']}\n\n```rust\n{mem['signature']}\n```\n"
                if mem["doc"]:
                    md += "\n" + mem["doc"] + "\n"
            entry["tokens"] = estimate_tokens(md)
        entry["title"] = f"{entry['kind']} {entry['path']}"
    else:
        entry["kind"] = "page"

    # First real paragraph, used as the search-result summary.
    body = re.sub(r"^#.*$", "", md, flags=re.M)
    body = re.sub(r"```.*?```", "", body, flags=re.S)
    para = next((p.strip() for p in body.split("\n\n") if len(p.strip()) > 60), "")
    entry["summary"] = re.sub(r"\s+", " ", para)[:400]
    entry["keywords"] = body_keywords(md)

    out_file = out_dir / (doc_id + ".md")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    header = f"<!-- oxidizer: source={src_id} url={entry['url']} -->\n\n"
    out_file.write_text(header + md, encoding="utf-8")
    entry["file"] = doc_id + ".md"
    return entry


def build_source(src_id: str, meta: dict, html_root: Path, corpus: Path,
                 jobs: int, quiet: bool) -> dict | None:
    src_dir = html_root / meta["dir"]
    if not src_dir.is_dir():
        return None

    files = [
        str(p.relative_to(src_dir))
        for p in sorted(src_dir.rglob("*.html"))
        if not SKIP_FILE_RE.search(str(p.relative_to(src_dir)).replace("\\", "/"))
    ]
    if not files:
        return None

    out_dir = corpus / src_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    work = [(src_id, meta["kind"], str(src_dir), rel, str(out_dir), meta["url"])
            for rel in files]
    entries: list[dict] = []
    started = time.time()
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
        for i, entry in enumerate(pool.map(_convert_page, work, chunksize=16), 1):
            if entry:
                entries.append(entry)
            if not quiet and i % 250 == 0:
                print(f"    {src_id}: {i}/{len(files)}", file=sys.stderr)

    entries.sort(key=lambda e: e["id"])
    (out_dir / "INDEX.json").write_text(
        json.dumps({"source": src_id, "docs": entries}, indent=1), encoding="utf-8")

    total_tokens = sum(e["tokens"] for e in entries)
    if not quiet:
        print(f"  {src_id:16s} {len(entries):5d} docs  "
              f"{total_tokens // 1000:6d}k tok  {time.time() - started:5.1f}s",
              file=sys.stderr)
    return {
        "id": src_id, "kind": meta["kind"], "title": meta["title"],
        "role": meta["role"], "url": meta["url"], "origin": "offline",
        "doc_count": len(entries), "total_tokens": total_tokens,
    }


# --------------------------------------------------------------------------
# lints
#
# rustup does *not* ship the clippy lint index offline — the clippy book's lint
# list is fetched by JavaScript at page load, so `share/doc/rust/html/clippy`
# contains only clippy's own development docs. The installed clippy-driver can
# however enumerate every lint it knows about, which is both offline and exactly
# version-matched to the toolchain. That is the better source anyway.

_LINT_CHECK_RE = re.compile(r"^\s+(\S+)\s+(allow|warn|deny|forbid)\s+(.*\S)\s*$")
_LINT_GROUP_RE = re.compile(r"^\s+(\S+)\s{2,}(\S.*\S)\s*$")


def build_lints_source(corpus: Path, quiet: bool) -> dict | None:
    tools = [(["clippy-driver", "-W", "help"], "clippy+rustc"),
             (["rustc", "-W", "help"], "rustc")]
    text = None
    provider = None
    for cmd, label in tools:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if proc.stdout and "Lint checks" in proc.stdout:
            text, provider = proc.stdout, label
            break
    if text is None:
        if not quiet:
            print("  lints            SKIPPED (no clippy-driver or rustc -W help)",
                  file=sys.stderr)
        return None

    out_dir = corpus / "lints"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    section = None
    entries: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("lint checks"):
            section = "check"
            continue
        if low.startswith("lint groups"):
            section = "group"
            continue
        if not line.strip() or line.strip().startswith(("name", "----", "-W ", "-A ",
                                                        "-D ", "-F ", "Available")):
            continue

        # Lint names are printed with dashes but written with underscores in
        # `#[allow(...)]` and on the command line, so the underscore form is
        # canonical everywhere Oxidizer reports one.
        if section == "check":
            m = _LINT_CHECK_RE.match(line)
            if not m:
                continue
            canonical = m.group(1).replace("-", "_")
            level, meaning = m.group(2), m.group(3)
            body = (f"# {canonical}\n\n**default level:** `{level}`\n\n{meaning}\n\n"
                    f"Silence with `#[allow({canonical})]`.\n")
        elif section == "group":
            m = _LINT_GROUP_RE.match(line)
            if not m:
                continue
            canonical = m.group(1).replace("-", "_")
            members = m.group(2)
            level = "group"
            meaning = f"Lint group containing {members.count(',') + 1} lints."
            body = (f"# {canonical}\n\n**lint group**\n\n{meaning}\n\n## Members\n\n"
                    + "\n".join(f"- `{x.strip().replace('-', '_')}`"
                                for x in members.split(",")) + "\n")
        else:
            continue

        if canonical in seen:
            continue
        seen.add(canonical)

        tool, _, bare = canonical.partition("::")
        if not bare:
            tool, bare = "rustc", canonical
        url = (f"https://rust-lang.github.io/rust-clippy/master/index.html#{bare}"
               if tool == "clippy"
               else f"https://doc.rust-lang.org/rustc/lints/listing/index.html")

        doc_id = canonical.replace("::", "-")
        (out_dir / f"{doc_id}.md").write_text(
            f"<!-- oxidizer: source=lints url={url} -->\n\n" + body, encoding="utf-8")
        entries.append({
            "id": doc_id, "source": "lints", "kind": "lint",
            "title": canonical, "path": canonical,
            "headings": [canonical], "summary": meaning[:400],
            "keywords": body_keywords(body + " " + canonical.replace("_", " ")),
            "url": url, "tokens": estimate_tokens(body), "file": f"{doc_id}.md",
            "level": level, "tool": tool,
        })

    if not entries:
        shutil.rmtree(out_dir, ignore_errors=True)
        return None

    entries.sort(key=lambda e: e["id"])
    (out_dir / "INDEX.json").write_text(
        json.dumps({"source": "lints", "docs": entries}, indent=1), encoding="utf-8")
    if not quiet:
        print(f"  {'lints':16s} {len(entries):5d} docs  (from {provider})",
              file=sys.stderr)
    return {
        "id": "lints", "kind": "lints", "title": "Rustc and Clippy Lint Index",
        "role": "Every lint the installed toolchain knows, with default level. "
                "The idiom authority.",
        "url": "https://rust-lang.github.io/rust-clippy/master/index.html",
        "origin": "toolchain", "doc_count": len(entries),
        "total_tokens": sum(e["tokens"] for e in entries),
    }


# --------------------------------------------------------------------------
# online sources


def _fetch(url: str, timeout: int = 30) -> str | None:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Oxidizer-mirror/1.0 (+rust canon mirror)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return None


def crawl_online(src_id: str, meta: dict, corpus: Path, quiet: bool) -> dict | None:
    base = meta["url"]
    root = _fetch(base)
    if root is None:
        if not quiet:
            print(f"  {src_id:16s} SKIPPED (unreachable — egress policy or network)",
                  file=sys.stderr)
        return None

    out_dir = corpus / src_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    origin = urllib.parse.urlparse(base)
    seen: set[str] = set()
    queue: list[str] = [base]
    entries: list[dict] = []

    while queue and len(entries) < meta["max_pages"]:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        raw = root if url == base else _fetch(url)
        if raw is None:
            continue

        md, headings = html_to_markdown(raw)
        if len(md.strip()) >= 200:
            rel = urllib.parse.urlparse(url).path[len(origin.path):] or "index.html"
            doc_id = re.sub(r"\.html?$", "", rel.strip("/")) or "index"
            out_file = out_dir / (doc_id + ".md")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(
                f"<!-- oxidizer: source={src_id} url={url} -->\n\n" + md,
                encoding="utf-8")
            body = re.sub(r"```.*?```", "", re.sub(r"^#.*$", "", md, flags=re.M), flags=re.S)
            para = next((p.strip() for p in body.split("\n\n") if len(p.strip()) > 60), "")
            entries.append({
                "id": doc_id, "source": src_id, "kind": "page",
                "title": headings[0][1] if headings else doc_id,
                "headings": [h for _, h in headings[:40]],
                "summary": re.sub(r"\s+", " ", para)[:400],
                "keywords": body_keywords(md),
                "url": url, "tokens": estimate_tokens(md), "file": doc_id + ".md",
            })

        for href in re.findall(r'href="([^"#?]+)"', raw):
            nxt = urllib.parse.urljoin(url, href)
            p = urllib.parse.urlparse(nxt)
            if (p.netloc == origin.netloc and p.path.startswith(origin.path)
                    and (p.path.endswith(".html") or p.path.endswith("/"))
                    and nxt not in seen):
                queue.append(nxt)
        time.sleep(0.2)  # be a polite guest on someone else's server

    if not entries:
        shutil.rmtree(out_dir, ignore_errors=True)
        return None

    entries.sort(key=lambda e: e["id"])
    (out_dir / "INDEX.json").write_text(
        json.dumps({"source": src_id, "docs": entries}, indent=1), encoding="utf-8")
    if not quiet:
        print(f"  {src_id:16s} {len(entries):5d} docs  (online)", file=sys.stderr)
    return {
        "id": src_id, "kind": "online", "title": meta["title"], "role": meta["role"],
        "url": base, "origin": "online", "doc_count": len(entries),
        "total_tokens": sum(e["tokens"] for e in entries),
    }


# --------------------------------------------------------------------------


def corpus_dir() -> Path:
    if os.environ.get("OXIDIZER_CORPUS"):
        return Path(os.environ["OXIDIZER_CORPUS"])
    return Path(__file__).resolve().parents[3] / "corpus"


def cmd_check(corpus: Path) -> int:
    manifest_path = corpus / "MANIFEST.json"
    if not manifest_path.exists():
        print("corpus: ABSENT — run `python3 scripts/mirror.py` to build it")
        return 1
    manifest = json.loads(manifest_path.read_text())
    current = toolchain_info()
    built_for = manifest.get("toolchain", {}).get("rustc_version")
    print(f"corpus:    {corpus}")
    print(f"built:     {manifest.get('generated_at')}")
    print(f"built for: {built_for}")
    print(f"current:   {current['rustc_version']}")
    print(f"sources:   {len(manifest.get('sources', []))}, "
          f"{sum(s['doc_count'] for s in manifest.get('sources', []))} docs")
    if built_for != current["rustc_version"]:
        print("\nSTALE: the toolchain moved since this corpus was built. "
              "Re-run mirror.py so the docs match the compiler.")
        return 2
    print("\nFRESH: corpus matches the active toolchain.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--include", default="",
                    help="comma-separated extra sources (core,alloc,embedded-book,unstable-book)")
    ap.add_argument("--only", default="", help="comma-separated: build only these")
    ap.add_argument("--online", action="store_true",
                    help="also mirror the Brown book fork and C++/Rust phrasebook")
    ap.add_argument("--check", action="store_true", help="report freshness and exit")
    ap.add_argument("--jobs", type=int, default=min(8, (os.cpu_count() or 4)))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    corpus = args.corpus or corpus_dir()
    if args.check:
        return cmd_check(corpus)

    html_root = rust_doc_root()
    if html_root is None:
        print("error: local Rust documentation not found.\n"
              "  Install it with:  rustup component add rust-docs\n"
              "  Or point OXIDIZER_RUST_DOCS at an existing doc html root.",
              file=sys.stderr)
        return 1

    if args.only:
        wanted = [s.strip() for s in args.only.split(",") if s.strip()]
    else:
        wanted = [k for k, v in SOURCES.items() if v["default"]]
        wanted += [s.strip() for s in args.include.split(",") if s.strip()]

    # "lints" is generated from the toolchain rather than from an HTML tree, so
    # it is a valid selector without being an entry in SOURCES.
    unknown = [s for s in wanted if s not in SOURCES and s != "lints"]
    if unknown:
        print(f"error: unknown source(s): {', '.join(unknown)}\n"
              f"  available: {', '.join(SOURCES)}, lints", file=sys.stderr)
        return 1
    wanted = [s for s in wanted if s != "lints"]

    corpus.mkdir(parents=True, exist_ok=True)
    if not args.quiet:
        print(f"Rust docs: {html_root}\nCorpus:    {corpus}\n", file=sys.stderr)

    built: list[dict] = []
    for src_id in wanted:
        info = build_source(src_id, SOURCES[src_id], html_root, corpus,
                            args.jobs, args.quiet)
        if info:
            built.append(info)

    if not args.only or "lints" in args.only:
        info = build_lints_source(corpus, args.quiet)
        if info:
            built.append(info)

    if args.online:
        if not args.quiet:
            print("\nOnline sources:", file=sys.stderr)
        for src_id, meta in ONLINE_SOURCES.items():
            info = crawl_online(src_id, meta, corpus, args.quiet)
            if info:
                built.append(info)

    # Rebuilding a subset must not erase the record of sources built earlier;
    # keep any previously-mirrored source whose corpus files are still present.
    merged: dict[str, dict] = {}
    old_path = corpus / "MANIFEST.json"
    if old_path.exists():
        try:
            for s in json.loads(old_path.read_text()).get("sources", []):
                if (corpus / s["id"] / "INDEX.json").exists():
                    merged[s["id"]] = s
        except (json.JSONDecodeError, OSError, KeyError):
            pass
    for s in built:
        merged[s["id"]] = s
    built = sorted(merged.values(), key=lambda s: s["id"])

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolchain": toolchain_info(),
        "doc_root": str(html_root),
        "sources": built,
        "totals": {
            "docs": sum(s["doc_count"] for s in built),
            "tokens": sum(s["total_tokens"] for s in built),
        },
    }
    (corpus / "MANIFEST.json").write_text(json.dumps(manifest, indent=2),
                                          encoding="utf-8")
    if not args.quiet:
        print(f"\n{manifest['totals']['docs']} docs, "
              f"~{manifest['totals']['tokens'] // 1000}k tokens across "
              f"{len(built)} sources -> {corpus}/MANIFEST.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
