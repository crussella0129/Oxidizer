# Oxidizer

An agent-agnostic Rust skill. It mirrors the official Rust canon locally —
pinned to the toolchain you actually compile with — and serves it back in small,
routed, citable slices instead of dumping documentation into a context window.

The canon is about 8 million tokens. A single `std` page (`Vec`) is ~96k on its
own. You cannot read it; you have to route into it. That is the entire problem
Oxidizer solves.

```
$ oxidize diagnose src/parser.rs
# Diagnosis: src/parser.rs
compiler: rustc --edition 2021
1 error(s), 0 warning(s)
codes: E0502
------------------------------------------------------------

error[E0502]: cannot borrow `*words` as mutable because it is also borrowed as immutable
  at parser.rs:6:5

============================================================
CANON
============================================================

# Error code E0502

A variable already borrowed with a certain mutability ...

Source: https://doc.rust-lang.org/error_codes/E0502.html

Next: load domains/01_diagnose/CONTEXT.md
```

## Why mirror instead of fetching

`doc.rust-lang.org` always serves stable-latest. A project pinned to an older
toolchain will disagree with it — silently, and precisely in the cases where a
correct answer matters most: a method that is not stable yet, a lint that was
renamed, an edition default that changed.

Oxidizer builds from `$(rustc --print sysroot)/share/doc/rust/html`, which
`rustup component add rust-docs` installs. The corpus is therefore correct by
construction for the compiler that will actually build the user's code, needs no
network at query time, and `oxidize manifest` warns when the toolchain has moved
underneath it.

## Quick start

```bash
rustup component add rust-docs                       # ~750MB, one time
python3 skills/oxidizer/scripts/mirror.py --online    # build the corpus, ~30s

python3 skills/oxidizer/scripts/oxidize.py diagnose path/to/file.rs
python3 skills/oxidizer/scripts/oxidize.py api std::vec::Vec::retain
python3 skills/oxidizer/scripts/oxidize.py explain E0502
```

`--online` adds the two Brown University sources, which have no offline
equivalent. Everything else comes from the local toolchain. The scripts are
stdlib-only Python 3 — no pip install stands between you and a working corpus.

## What is mirrored

| Source | From | Docs |
|---|---|---|
| `std` API | toolchain | 2186 |
| rustc + clippy lints | `clippy-driver -W help` | 1056 |
| Rust By Example | toolchain | 783 |
| Compiler error index | toolchain | 520 |
| The Book | toolchain | 169 |
| The Book, Brown interactive fork | rust-book.cs.brown.edu | 121 |
| The Reference | toolchain | 115 |
| Cargo book | toolchain | 96 |
| The Rustonomicon | toolchain | 64 |
| Edition guide | toolchain | 56 |
| C++-to-Rust phrasebook | cel.cs.brown.edu/crp | 53 |
| Clippy development book | toolchain | 34 |
| Style guide | toolchain | 10 |

5,263 documents, ~8.1M tokens. `core`, `alloc`, the embedded book and the
unstable book are available via `--include`.

Counts are lower than the raw page counts on disk because redirect shims and
retired-edition copies are dropped at mirror time — the Book ships 124 root
chapter files, 22 of which are redirects left over from its chapter
renumbering.

Two things named in the original brief are **not** mirrored: `lib.rs` crate
categories (blocked by egress policy in the environment this was built in, HTTP
403) and any third-party crate documentation. `references/corpus.md` records the
gaps honestly rather than papering over them.

## Two ways to use it

**As a skill.** Point an agent harness at `skills/oxidizer/`. `SKILL.md`
describes when to reach for it and how to spend the retrieval budget.

**As an MCP server.** `mcp/oxidizer-mcp` is a stdio MCP server built on the
official `rmcp` SDK, exposing the same seven-tool surface natively in Rust — no
Python at runtime. This is what makes the skill agent-agnostic: any MCP client
gets the routed canon without knowing anything about skill formats.

```bash
cd mcp/oxidizer-mcp && cargo build --release
```

```json
{
  "mcpServers": {
    "oxidizer": {
      "command": "/path/to/Oxidizer/mcp/oxidizer-mcp/target/release/oxidizer-mcp",
      "env": { "OXIDIZER_CORPUS": "/path/to/Oxidizer/corpus" }
    }
  }
}
```

Tools: `oxidizer_route`, `oxidizer_search`, `oxidizer_show`, `oxidizer_explain`,
`oxidizer_api`, `oxidizer_lint`, `oxidizer_manifest`.

## Commands

| Command | Use it for |
|---|---|
| `route "<question>"` | Which domain contract to load |
| `diagnose <file.rs\|dir>` | Compile it, attach the error index for what broke |
| `diagnose <path> --clippy` | Idiom review: lints plus their docs |
| `explain E0502` | One error code |
| `api std::vec::Vec::retain` | One signature. Accepts `Vec`, `Vec::retain`, full paths |
| `lint needless_range_loop` | What a lint wants, and how to silence it |
| `search "<query>" [--source ...]` | Ranked candidates with token costs |
| `show <source>/<id> [--section H]` | One document, or one section |
| `manifest` | What is mirrored, and whether it is stale |

Every command takes `--max-tokens` (default 2000) and `--json`. Truncation
happens on a paragraph boundary and reports the headings it withheld, so the
caller can narrow rather than blindly raise the budget.

## Architecture

Oxidizer follows the Model Workspace Protocol from *Interpretable Context
Methodology: Folder Structure as Agent Architecture*
([arXiv:2603.16021](https://arxiv.org/html/2603.16021v1)) — folder structure as
the routing mechanism, with layers loaded on demand instead of all at once.

```
skills/oxidizer/
├── SKILL.md              Layer 0  identity + routing map        ~1,100 tok
├── CONTEXT.md            Layer 1  which source answers what       ~900 tok
├── domains/
│   ├── 01_diagnose/      Layer 2  it does not compile         ~700-1,000 tok
│   ├── 02_learn/                  explain a concept                    each
│   ├── 03_api/                    signatures
│   ├── 04_spec/                   is this legal / guaranteed
│   ├── 05_unsafe/                 unsafe, UB, FFI, variance
│   ├── 06_idiom/                  make this idiomatic
│   └── 07_migrate/                port from C/C++
├── scripts/
│   ├── mirror.py         build/refresh the corpus
│   ├── oxidize.py        the retrieval CLI
│   └── extract.py        HTML -> markdown
├── references/           how the corpus works; MWP deviations
└── evals/                test prompts and expectations

corpus/                   Layer 3  the mirrored canon (generated, gitignored)
mcp/oxidizer-mcp/         stdio MCP server (rmcp)
tests/                    fixtures + assertion harness
```

A typical answer loads Layer 0, one domain contract, and one or two retrievals —
roughly 3,000–5,000 tokens against a corpus of 8 million. That is the paper's
target range, and it is the reason the corpus can be this large without being
useless.

The retrieval budget is enforced in code rather than by instruction. Telling a
model to "be brief with context" is unreliable in a way that a hard cap in the
tool is not.

Where Oxidizer departs from the paper — numbered folders encode routing
precedence rather than pipeline order, and Layer 3 is generated rather than
authored — `skills/oxidizer/references/mwp-adaptation.md` says so and explains
why.

## Tests

```bash
python3 tests/run_tests.py --mcp
```

86 assertions over five real Rust fixtures. The fixtures are compiled by the
actual toolchain, so the tests check that Oxidizer retrieves the right canon for
what the compiler *actually* said, not for a hand-written guess at it. Coverage
includes error-code extraction and routing, clippy lint detection, std API
resolution (`Option::map` must land on the enum, not `std::iter::Map`), token
budget enforcement, search ranking, and CLI/MCP parity.

## Sources

- The Book — <https://doc.rust-lang.org/book/>
  ([Brown interactive fork](https://rust-book.cs.brown.edu/))
- Rust By Example — <https://doc.rust-lang.org/rust-by-example/>
- The Standard Library — <https://doc.rust-lang.org/std/>
- The Rust Reference — <https://doc.rust-lang.org/reference/>
- The Rustonomicon — <https://doc.rust-lang.org/nomicon/>
- Brown C++-to-Rust Phrasebook — <https://cel.cs.brown.edu/crp/>

## License

See `LICENSE`.
