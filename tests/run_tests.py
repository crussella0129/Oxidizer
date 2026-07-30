#!/usr/bin/env python3
"""Oxidizer end-to-end tests.

Exercises the skill against real Rust files in `tests/fixtures/`. Every fixture
is compiled by the actual toolchain, so these assertions check that Oxidizer
retrieves the right canon for what the compiler *actually* said — not for what
a hand-written expectation assumed it would say.

    python3 tests/run_tests.py            # CLI paths
    python3 tests/run_tests.py --mcp      # also exercise the MCP server
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
OXIDIZE = ROOT / "skills" / "oxidizer" / "scripts" / "oxidize.py"
MCP_BIN = ROOT / "mcp" / "oxidizer-mcp" / "target" / "debug" / "oxidizer-mcp"

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"\n          {detail}" if detail and not ok else ""))
    return ok


def oxidize(*args: str, expect_ok: bool = True) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(OXIDIZE), *args],
                          capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    if expect_ok and proc.returncode != 0:
        print(f"        (command failed: oxidize {' '.join(args)})\n{out[:400]}")
    return proc.returncode, out


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# --------------------------------------------------------------------------


def test_corpus() -> None:
    section("1. Corpus integrity")
    rc, out = oxidize("manifest")
    check("manifest command succeeds", rc == 0)

    manifest_path = Path(os.environ.get("OXIDIZER_CORPUS", ROOT / "corpus")) / "MANIFEST.json"
    if not manifest_path.exists():
        check("MANIFEST.json exists", False, f"missing at {manifest_path}")
        return
    m = json.loads(manifest_path.read_text())
    ids = {s["id"] for s in m["sources"]}

    required = {"book", "reference", "nomicon", "error-index", "std", "lints"}
    check("core sources mirrored", required <= ids, f"missing: {required - ids}")
    check("corpus is non-trivial", m["totals"]["docs"] > 3000,
          f"only {m['totals']['docs']} docs")
    check("toolchain recorded", bool(m.get("toolchain", {}).get("rustc_version")))

    current = subprocess.run(["rustc", "--version"], capture_output=True,
                             text=True).stdout.strip()
    check("corpus matches active toolchain",
          m["toolchain"]["rustc_version"] == current,
          f"corpus={m['toolchain']['rustc_version']} current={current}")

    for src in ("book", "std", "error-index", "lints"):
        if src in ids:
            idx = manifest_path.parent / src / "INDEX.json"
            docs = json.loads(idx.read_text())["docs"]
            check(f"{src} index has entries with urls",
                  bool(docs) and all(d.get("url") for d in docs[:50]))


# Each fixture, the error code the compiler should produce, and the domain
# Oxidizer should route the resulting question to.
ERROR_FIXTURES = [
    ("borrow_conflict.rs", "E0502", "01_diagnose"),
    ("move_after_use.rs", "E0382", "01_diagnose"),
    ("missing_lifetime.rs", "E0106", "01_diagnose"),
]


def test_diagnose() -> None:
    section("2. diagnose on failing fixtures")
    for fixture, code, domain in ERROR_FIXTURES:
        path = FIXTURES / fixture
        rc, out = oxidize("diagnose", str(path), "--json", "--max-tokens", "400")
        if rc != 0:
            check(f"{fixture}: diagnose runs", False, out[:300])
            continue
        data = json.loads(out)

        check(f"{fixture}: compiler reports {code}",
              code in data["codes"], f"got {data['codes']}")
        check(f"{fixture}: exactly one error",
              data["error_count"] == 1, f"got {data['error_count']}")
        check(f"{fixture}: diagnostic carries a source location",
              bool(data["diagnostics"]) and bool(data["diagnostics"][0].get("at")))
        check(f"{fixture}: canon entry attached for {code}",
              any(d["code"] == code for d in data["docs"]))
        doc = next((d for d in data["docs"] if d["code"] == code), None)
        check(f"{fixture}: canon entry cites doc.rust-lang.org",
              doc is not None and doc["url"].startswith("https://doc.rust-lang.org/"))
        check(f"{fixture}: routed to {domain}",
              data.get("domain") == domain, f"got {data.get('domain')}")


def test_clippy_path() -> None:
    section("3. diagnose --clippy on the idiomatic-review fixture")
    path = FIXTURES / "unidiomatic.rs"
    rc, out = oxidize("diagnose", str(path), "--clippy", "--json", "--max-tokens", "800")
    if rc != 0:
        check("unidiomatic.rs: clippy diagnose runs", False, out[:300])
        return
    data = json.loads(out)

    check("unidiomatic.rs: compiles without errors", data["error_count"] == 0)
    expected = {"clippy::needless_range_loop", "clippy::ptr_arg",
                "clippy::needless_return", "clippy::len_zero"}
    got = set(data["lints"])
    check("unidiomatic.rs: expected lints fire", expected <= got,
          f"missing {expected - got}")
    check("unidiomatic.rs: lint docs attached",
          len(data["docs"]) >= 4, f"got {len(data['docs'])}")
    check("unidiomatic.rs: routed to 06_idiom", data.get("domain") == "06_idiom")

    # The clean fixture must not be reported as broken.
    rc, out = oxidize("diagnose", str(FIXTURES / "unsafe_ffi.rs"), "--json")
    data = json.loads(out)
    check("unsafe_ffi.rs: compiles clean", data["error_count"] == 0,
          f"errors: {data['diagnostics']}")


def test_routing() -> None:
    section("4. Routing")
    cases = [
        ("why does the borrow checker reject this, error E0502", "01_diagnose"),
        ("explain what ownership is, I'm new to Rust", "02_learn"),
        ("what's the signature of the std HashMap entry method", "03_api"),
        ("is it legal to rely on struct field drop order", "04_spec"),
        ("is this transmute undefined behaviour in unsafe code", "05_unsafe"),
        ("make this more idiomatic, what would clippy say", "06_idiom"),
        ("what's the Rust equivalent of a C++ shared_ptr", "07_migrate"),
    ]
    for question, domain in cases:
        rc, out = oxidize("route", question, "--json")
        data = json.loads(out)
        picked = [d["domain"] for d in data["domains"]]
        check(f"route -> {domain}: {question[:44]!r}",
              picked and picked[0] == domain, f"got {picked}")


def test_api() -> None:
    section("5. std API resolution")
    cases = [
        ("std::vec::Vec::retain", "std::vec::Vec", "retain", "pub fn retain"),
        ("Vec::push", "std::vec::Vec", "push", "pub fn push"),
        ("Option::map", "std::option::Option", "map", "pub fn map"),
        ("HashMap::entry", "std::collections::HashMap", "entry", "pub fn entry"),
        ("Iterator::fold", "std::iter::Iterator", "fold", "fn fold"),
        ("String::push_str", "std::string::String", "push_str", "pub fn push_str"),
    ]
    for query, path, member, sig in cases:
        rc, out = oxidize("api", query, "--json", "--max-tokens", "400")
        if rc != 0:
            check(f"api {query}", False, out[:200])
            continue
        data = json.loads(out)
        check(f"api {query} -> {path}::{member}",
              data["path"] == path and (data["member"] or "").endswith(member),
              f"got {data['path']}::{data['member']}")
        check(f"api {query} returns the signature",
              sig in data["content"], f"content began: {data['content'][:90]!r}")

    # A bare container type must stay inside budget rather than dumping ~96k.
    rc, out = oxidize("api", "Vec", "--json", "--max-tokens", "500")
    data = json.loads(out)
    check("api Vec resolves to the struct, not the module or the vec! macro",
          data["path"] == "std::vec::Vec" and data["kind"] == "struct",
          f"got {data['path']} ({data['kind']})")
    check("api Vec respects the token budget",
          data["tokens_returned"] <= 600,
          f"returned {data['tokens_returned']} tokens")
    check("api Vec reports that it truncated", data["truncated"] is True)


def test_lints() -> None:
    section("6. Lint lookup")
    for query, expected in [
        ("needless_range_loop", "clippy::needless_range_loop"),
        ("clippy::needless-range-loop", "clippy::needless_range_loop"),
        ("ptr_arg", "clippy::ptr_arg"),
        ("unused_mut", "unused_mut"),
    ]:
        rc, out = oxidize("lint", query, "--json")
        if rc != 0:
            check(f"lint {query}", False, out[:200])
            continue
        data = json.loads(out)
        check(f"lint {query} -> {expected}", data["lint"] == expected,
              f"got {data['lint']}")

    rc, out = oxidize("lint", "definitely_not_a_lint", expect_ok=False)
    check("unknown lint fails with a usable message",
          rc != 0 and "no lint named" in out)


def test_budgets() -> None:
    section("7. Token budgets are enforced, not merely advertised")
    rc, out = oxidize("show", "std/vec/struct.Vec", "--json", "--max-tokens", "300")
    data = json.loads(out)
    check("show respects --max-tokens on a ~96k-token page",
          data["tokens_returned"] <= 350, f"returned {data['tokens_returned']}")
    check("show reports the full size it withheld",
          data["tokens_total"] > 50_000, f"tokens_total={data['tokens_total']}")
    check("show flags truncation", data["truncated"] is True)

    rc, out = oxidize("show", "book/ch04-01-what-is-ownership",
                      "--section", "Ownership Rules", "--json")
    data = json.loads(out)
    check("show --section narrows to one heading",
          data["section"] == "Ownership Rules" and data["tokens_returned"] < 400,
          f"section={data['section']} tokens={data['tokens_returned']}")
    check("section content is the real rules text",
          "one owner at a time" in data["content"].lower())


def test_search() -> None:
    section("8. Search ranking")
    # The Brown fork mirrors the Book chapter for chapter, so either source
    # ranking first is correct; the test asserts the right *page*.
    cases = [
        ("trait objects vs generics", ("book", "brown-book"), None),
        ("shared_ptr equivalent in Rust", ("crp-phrasebook",), None),
        ("what is interior mutability RefCell", ("book", "brown-book"),
         "interior-mutability"),
    ]
    for query, sources, id_part in cases:
        rc, out = oxidize("search", query, "--json", "--limit", "3")
        data = json.loads(out)
        hits = data["hits"]
        check(f"search {query[:40]!r} returns hits", bool(hits))
        if not hits:
            continue
        check(f"search {query[:40]!r} ranks {'/'.join(sources)} first",
              hits[0]["source"] in sources,
              f"got {hits[0]['source']}: {hits[0]['title']}")
        if id_part:
            check(f"search {query[:40]!r} finds the right page",
                  id_part in hits[0]["id"], f"got {hits[0]['id']}")


# Naturally-phrased questions paired with every document that would be a
# reasonable answer. Several documents usually qualify, so a single "expected
# id" would understate quality — an earlier version of this benchmark scored
# search at 0/10 partly because its needles were too narrow.
RETRIEVAL_CASES = [
    ("why can't I use this vector after passing it to a function",
     ["ch04-01-what-is-ownership", "ch04-02-references"]),
    ("what does 'a mean in a struct definition",
     ["ch10-03-lifetime-syntax", "lifetime"]),
    ("how do I share a counter between threads",
     ["ch16-03-shared-state", "sync/struct.Mutex", "sync/struct.Arc"]),
    ("how do I sort a vector of structs by a field",
     ["sort_by_key", "sort_by", "primitive.slice", "trait.Ord"]),
    ("how do I call a C function from Rust safely",
     ["ffi", "extern", "nomicon"]),
    ("how do I get the index while iterating",
     ["struct.Enumerate", "enumerate", "ch13-02"]),
    ("why can't I index into a String",
     ["ch08-02-strings", "struct.String", "primitive.str"]),
    ("how do I write an integration test", ["ch11-03", "integration"]),
    ("how do modules and visibility work across files",
     ["ch07", "module", "visibility"]),
    ("why does my thread closure need move", ["ch16-01", "ch13-01", "closure"]),
    ("how do I make a custom error type",
     ["ch09", "define_error_type", "trait.Error"]),
    ("what is the difference between String and &str",
     ["ch08-02-strings", "struct.String", "primitive.str"]),
    ("how do I read a file line by line",
     ["struct.BufReader", "io/index", "lines"]),
]

# Retrieval quality measured before the BM25 rewrite was precision@1 0/10 and
# recall@5 1/10. These thresholds sit below current measured quality so normal
# corpus drift does not fail the build, but a real regression will.
MIN_PRECISION_AT_1 = 0.45
MIN_RECALL_AT_5 = 0.75


def test_retrieval_quality() -> None:
    section("12. Retrieval benchmark")
    hits_at_1 = hits_at_5 = 0
    misses = []
    for question, acceptable in RETRIEVAL_CASES:
        rc, out = oxidize("search", question, "--json", "--limit", "20")
        if rc != 0:
            misses.append((question, "search failed"))
            continue
        rank = None
        for i, h in enumerate(json.loads(out)["hits"], start=1):
            key = f"{h['source']}/{h['id']}".lower()
            if any(a.lower() in key for a in acceptable):
                rank = i
                break
        if rank == 1:
            hits_at_1 += 1
        if rank and rank <= 5:
            hits_at_5 += 1
        else:
            misses.append((question, f"rank {rank or '>20'}"))

    n = len(RETRIEVAL_CASES)
    p1, r5 = hits_at_1 / n, hits_at_5 / n
    check(f"precision@1 >= {MIN_PRECISION_AT_1:.0%} (got {p1:.0%}, {hits_at_1}/{n})",
          p1 >= MIN_PRECISION_AT_1,
          "; ".join(f"{q[:40]}: {why}" for q, why in misses[:4]))
    check(f"recall@5 >= {MIN_RECALL_AT_5:.0%} (got {r5:.0%}, {hits_at_5}/{n})",
          r5 >= MIN_RECALL_AT_5,
          "; ".join(f"{q[:40]}: {why}" for q, why in misses[:4]))


def test_confidence_signals() -> None:
    section("13. Confidence and not-in-canon signals")
    # A question the canon answers well should report high confidence.
    rc, out = oxidize("search", "how do I share a counter between threads",
                      "--json", "--limit", "3")
    data = json.loads(out)
    check("a well-covered question reports high confidence",
          data["confidence"] == "high", f"got {data['confidence']}")
    check("confidence reports term coverage",
          data["matched_terms"] > 0 and data["query_terms"] > 0)

    # Third-party crates are the case that previously produced confident junk:
    # "difference between anyhow and thiserror" returned btree_set::Difference.
    for query, crate in [
        ("how do I serialize a struct with serde", "serde"),
        ("difference between anyhow and thiserror", "anyhow"),
        ("how do I spawn a tokio task", "tokio"),
    ]:
        rc, out = oxidize("search", query, "--json", "--limit", "2")
        data = json.loads(out)
        check(f"{crate} question is flagged not-in-canon",
              crate in data.get("non_canon", []), f"got {data.get('non_canon')}")
        check(f"{crate} question reports low confidence",
              data["confidence"] == "low", f"got {data['confidence']}")

    # Question scaffolding must not be treated as content.
    rc, out = oxidize("search", "difference between anyhow and thiserror",
                      "--json", "--limit", "3")
    ids = [h["id"] for h in json.loads(out)["hits"]]
    check("the word 'difference' no longer retrieves btree_set::Difference",
          not any("btree_set::Difference".lower() in i.lower() for i in ids),
          f"got {ids}")

    rc, out = oxidize("search", "--auto", "how do I share a counter between threads",
                      "--json", "--limit", "3")
    data = json.loads(out)
    check("--auto reports the sources routing prefers",
          isinstance(data.get("preferred"), list))
    check("--auto boosts rather than filters (other sources still eligible)",
          not data.get("sources"), f"sources={data.get('sources')}")


def test_postings_index() -> None:
    section("14. Full-text postings index")
    corpus = Path(os.environ.get("OXIDIZER_CORPUS", ROOT / "corpus"))
    path = corpus / "POSTINGS.json"
    if not check("POSTINGS.json exists", path.exists()):
        return
    post = json.loads(path.read_text())
    check("postings cover every indexed document",
          len(post["docs"]) > 3000, f"{len(post['docs'])} docs")
    check("postings record per-document lengths for BM25",
          len(post["lengths"]) == len(post["docs"]))
    check("postings record an average document length",
          post.get("avg_length", 0) > 0)
    check("index is substantial", len(post["terms"]) > 10_000,
          f"{len(post['terms'])} terms")

    # Body-only vocabulary is the whole point: these appear in prose, not titles.
    for term in ("shared_ptr", "enumerate", "with_capacity", "utf"):
        check(f"body term {term!r} is indexed", term in post["terms"])


def test_algorithms() -> None:
    section("15. Worked-examples source (non-canonical)")
    manifest_path = Path(os.environ.get("OXIDIZER_CORPUS", ROOT / "corpus")) / "MANIFEST.json"
    m = json.loads(manifest_path.read_text())
    src = next((s for s in m["sources"] if s["id"] == "algorithms"), None)
    if src is None:
        print("  SKIP  algorithms source not mirrored "
              "(build with: mirror.py --algorithms)")
        return

    check("algorithms is flagged as non-canonical",
          src.get("canonical") is False)
    check("algorithms records the revision it was built from",
          bool(src.get("revision")), f"revision={src.get('revision')!r}")
    check("algorithms role warns it is not authoritative",
          "NOT CANON" in src["role"])
    check("algorithms records the lint posture of its own repo",
          isinstance(src.get("lint_allows"), list) and src["lint_allows"],
          f"lint_allows={src.get('lint_allows')}")

    docs = json.loads((manifest_path.parent / "algorithms" / "INDEX.json").read_text())["docs"]
    check("algorithms indexed a meaningful number of examples",
          len(docs) > 300, f"got {len(docs)}")

    # Citations must be public, commit-pinned, and free of proxy/credential junk.
    urls = [d["url"] for d in docs]
    bad = [u for u in urls
           if "127.0.0.1" in u or "local_proxy" in u or "@" in u.split("//")[-1].split("/")[0]]
    check("no citation leaks a proxy host or credentials", not bad, f"e.g. {bad[:2]}")
    pinned = [u for u in urls if "/blob/" in u]
    if pinned:
        rev = src["revision"]
        check("citations are pinned to the built revision",
              all(f"/blob/{rev}/" in u for u in pinned[:50]))

    # Rust-source extraction must produce the sections the domain contract promises.
    rc, out = oxidize("show", "algorithms/data_structures/trie", "--json",
                      "--max-tokens", "4000")
    data = json.loads(out)
    body = data["content"]
    for heading in ("Public items", "Implementation", "Tests (usage examples)"):
        check(f"trie example has a '{heading}' section", f"## {heading}" in body)
    check("trie example extracted the struct signature",
          "pub struct Trie" in body)
    check("trie example kept the module doc comment",
          "prefix tree" in body.lower())

    # Section slicing is the whole point on a 2k-token source file.
    rc, out = oxidize("show", "algorithms/data_structures/union_find",
                      "--section", "Public items", "--json")
    data = json.loads(out)
    check("a source file can be sliced to just its public API",
          data["tokens_returned"] < 200 and data["tokens_total"] > 1000,
          f"{data['tokens_returned']} of {data['tokens_total']}")

    rc, out = oxidize("search", "trie prefix tree", "--source", "algorithms",
                      "--json", "--limit", "3")
    hits = json.loads(out)["hits"]
    check("search finds an example by algorithm name",
          hits and "trie" in hits[0]["id"], f"got {hits[0]['id'] if hits else None}")


def test_implement_routing() -> None:
    section("16. 08_implement routing (must not cannibalise other domains)")
    for question, domain in [
        ("implement a trie in Rust", "08_implement"),
        ("how do I write a red-black tree from scratch", "08_implement"),
        ("show me a working dijkstra implementation", "08_implement"),
        # These must keep going where they went before the domain was added.
        ("explain what ownership is, I'm new to Rust", "02_learn"),
        ("make this more idiomatic, what would clippy say", "06_idiom"),
        ("why does the borrow checker reject this, error E0502", "01_diagnose"),
        ("is this transmute undefined behaviour in unsafe code", "05_unsafe"),
        ("what's the Rust equivalent of a C++ shared_ptr", "07_migrate"),
    ]:
        rc, out = oxidize("route", question, "--json")
        picked = [d["domain"] for d in json.loads(out)["domains"]]
        check(f"route -> {domain}: {question[:42]!r}",
              picked and picked[0] == domain, f"got {picked}")

    contract = ROOT / "skills" / "oxidizer" / "domains" / "08_implement" / "CONTEXT.md"
    check("08_implement contract exists", contract.exists())
    if contract.exists():
        body = contract.read_text()
        check("contract tells the agent to check std first",
              "Check `std` first" in body or "Check std first" in body)
        check("contract states the source is not canon", "not canon" in body.lower())
        check("contract says to re-lint adapted code",
              "--clippy" in body and "allow-list" in body)

    l1 = (ROOT / "skills" / "oxidizer" / "CONTEXT.md").read_text()
    check("corpus map ranks algorithms below the canon",
          "not authoritative for anything" in l1)


def test_disk() -> None:
    section("17. Disk hygiene reporting")
    rc, out = oxidize("disk", str(ROOT), "--json")
    if rc != 0:
        check("disk command runs", False, out[:300])
        return
    data = json.loads(out)

    check("disk reports the corpus size", data["corpus"]["bytes"] > 1_000_000)
    check("disk finds the MCP crate's target tree",
          any("oxidizer-mcp" in t["path"] for t in data["targets"]),
          f"found: {[t['path'] for t in data['targets']]}")

    target = next((t for t in data["targets"] if "oxidizer-mcp" in t["path"]), None)
    if target:
        # Cross-check against cargo's own accounting, which is the authority.
        manifest = Path(target["path"]).parent / "Cargo.toml"
        proc = subprocess.run(
            ["cargo", "clean", "--dry-run", "--manifest-path", str(manifest)],
            capture_output=True, text=True)
        reported = proc.stderr + proc.stdout
        mib = target["bytes"] / 1024 / 1024
        check("disk size agrees with `cargo clean --dry-run`",
              f"{mib:.1f}MiB" in reported.replace(" ", ""),
              f"we said {mib:.1f}MiB; cargo said: {reported.strip()[-90:]}")
        check("disk breaks out incremental state",
              target["incremental_bytes"] > 0)

    check("disk advertises that it deletes nothing",
          data.get("deletes_nothing") is True)

    # The whole point: it must never remove anything.
    before = sum(1 for _ in (ROOT / "mcp" / "oxidizer-mcp" / "target").rglob("*"))
    oxidize("disk", str(ROOT))
    after = sum(1 for _ in (ROOT / "mcp" / "oxidizer-mcp" / "target").rglob("*"))
    check("disk leaves the build tree untouched", before == after,
          f"{before} -> {after} entries")

    # Below the threshold it should advise against cleaning, not for it.
    rc, out = oxidize("disk", str(ROOT), "--threshold", "100000")
    check("disk declines to recommend cleaning under the threshold",
          "Nothing worth reclaiming" in out, out[-200:])

    rc, out = oxidize("disk", str(FIXTURES))
    check("disk handles a path with no target directory",
          rc == 0 and "No cargo target directories" in out)


def test_disk_guidance_documented() -> None:
    section("18. Disk-hygiene guidance is wired into the skill")
    ref = ROOT / "skills" / "oxidizer" / "references" / "disk-hygiene.md"
    check("references/disk-hygiene.md exists", ref.exists())
    if ref.exists():
        body = ref.read_text()
        check("guidance states the rebuild cost of cleaning",
              "incremental" in body and "cold rebuild" in body.lower()
              or "full one" in body.lower())
        check("guidance covers targeted cleans",
              all(f in body for f in ("--release", "--dry-run", "-p <crate>")))
        check("guidance says not to clean someone's tree unasked",
              "without being asked" in body.lower() or "ask before" in body.lower())

    skill = (ROOT / "skills" / "oxidizer" / "SKILL.md").read_text()
    check("SKILL.md tells the agent to offer rather than run the clean",
          "Offer it rather than running it" in skill)
    check("SKILL.md lists the disk command", "`disk [dir]`" in skill)

    for domain in ("01_diagnose", "06_idiom"):
        body = (ROOT / "skills" / "oxidizer" / "domains" / domain / "CONTEXT.md").read_text()
        check(f"{domain} contract points at disk hygiene",
              "oxidize disk" in body and "disk-hygiene.md" in body)


def test_explain() -> None:
    section("9. explain")
    rc, out = oxidize("explain", "E0502", "--json")
    data = json.loads(out)
    check("explain E0502 returns the index entry",
          "borrowed" in data["content"].lower())
    check("explain E0502 cites the canon URL",
          data["url"] == "https://doc.rust-lang.org/error_codes/E0502.html")

    # Codes should be recoverable from raw compiler output, not just clean input.
    rc, out = oxidize("explain", "error[E0382]: borrow of moved value", "--json")
    data = json.loads(out)
    check("explain extracts a code from raw rustc output", data["code"] == "E0382")

    rc, out = oxidize("explain", "not-a-code", expect_ok=False)
    check("explain rejects a non-code", rc != 0)


# --------------------------------------------------------------------------
# MCP parity


class McpClient:
    def __init__(self, binary: Path):
        self.proc = subprocess.Popen(
            [str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        self._id = 0
        self._request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "oxidizer-tests", "version": "0"}})
        self._notify("notifications/initialized", {})

    def _send(self, obj: dict) -> None:
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict) -> dict:
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method,
                    "params": params})
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout: "
                               + self.proc.stderr.read()[:500])
        return json.loads(line)

    def list_tools(self) -> list[dict]:
        return self._request("tools/list", {})["result"]["tools"]

    def call(self, name: str, args: dict) -> tuple[str | None, str | None]:
        r = self._request("tools/call", {"name": name, "arguments": args})
        if "error" in r:
            return None, r["error"].get("message", "")
        return r["result"]["content"][0]["text"], None

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def test_mcp() -> None:
    section("19. MCP server over stdio")
    if not MCP_BIN.exists():
        check("MCP binary built", False,
              f"not found at {MCP_BIN} — run `cargo build` in mcp/oxidizer-mcp")
        return

    client = McpClient(MCP_BIN)
    try:
        tools = {t["name"] for t in client.list_tools()}
        expected = {"oxidizer_route", "oxidizer_search", "oxidizer_show",
                    "oxidizer_explain", "oxidizer_api", "oxidizer_lint",
                    "oxidizer_manifest"}
        check("all seven tools advertised", expected <= tools,
              f"missing {expected - tools}")

        schemas = {t["name"]: t["inputSchema"] for t in client.list_tools()}
        check("tool schemas declare required params",
              schemas["oxidizer_api"].get("required") == ["path"])

        body, err = client.call("oxidizer_explain", {"code": "E0502"})
        check("MCP explain E0502", err is None and "borrowed" in (body or "").lower(),
              err or "")

        body, err = client.call("oxidizer_api", {"path": "Option::map",
                                                 "max_tokens": 200})
        check("MCP api resolves Option::map to the enum, not std::iter::Map",
              err is None and "std::option::Option::map" in (body or ""),
              err or (body or "")[:120])

        # The same budget guarantee must hold over MCP as over the CLI.
        body, err = client.call("oxidizer_api", {"path": "Vec", "max_tokens": 300})
        check("MCP api enforces the token budget",
              err is None and len(body or "") <= 300 * 4 + 800,
              f"got {len(body or '')} chars")

        body, err = client.call("oxidizer_lint",
                                {"name": "clippy::needless-range-loop"})
        check("MCP lint normalises dashes and the tool prefix",
              err is None and "needless_range_loop" in (body or ""), err or "")

        body, err = client.call("oxidizer_route",
                                {"question": "is this transmute undefined behaviour"})
        check("MCP route picks 05_unsafe",
              err is None and "05_unsafe" in (body or ""), err or "")

        body, err = client.call("oxidizer_show",
                                {"doc_id": "book/ch04-01-what-is-ownership",
                                 "section": "Ownership Rules", "max_tokens": 200})
        check("MCP show slices to a section",
              err is None and "one owner at a time" in (body or "").lower(), err or "")

        body, err = client.call("oxidizer_manifest", {})
        check("MCP manifest reports the toolchain",
              err is None and "rustc 1." in (body or ""), err or "")

        _, err = client.call("oxidizer_lint", {"name": "range_loop"})
        check("MCP returns a helpful error for an unknown lint",
              err is not None and "did you mean" in err.lower(), err or "(no error)")

        # Parity: MCP and CLI must not disagree about the same lookup.
        body, _ = client.call("oxidizer_api", {"path": "std::vec::Vec::retain",
                                               "max_tokens": 300})
        _, cli = oxidize("api", "std::vec::Vec::retain", "--max-tokens", "300")
        sig = "pub fn retain<F>(&mut self, f: F)"
        check("MCP and CLI agree on Vec::retain",
              sig in (body or "") and sig in cli)
    finally:
        client.close()


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp", action="store_true", help="also test the MCP server")
    args = ap.parse_args()

    started = time.time()
    print(f"Oxidizer tests\nrepo:   {ROOT}\nfixtures: {len(list(FIXTURES.glob('*.rs')))}")

    test_corpus()
    test_diagnose()
    test_clippy_path()
    test_routing()
    test_api()
    test_lints()
    test_budgets()
    test_search()
    test_explain()
    test_retrieval_quality()
    test_confidence_signals()
    test_postings_index()
    test_algorithms()
    test_implement_routing()
    test_disk()
    test_disk_guidance_documented()
    if args.mcp:
        test_mcp()

    total = len(PASS) + len(FAIL)
    print(f"\n{'=' * 70}")
    print(f"{len(PASS)}/{total} passed in {time.time() - started:.1f}s")
    if FAIL:
        print(f"\n{len(FAIL)} failure(s):")
        for name in FAIL:
            print(f"  - {name}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
