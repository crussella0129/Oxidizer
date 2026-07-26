---
name: oxidizer
description: Answer Rust questions from the official Rust canon (The Book, Rust By Example, the Reference, the Rustonomicon, std API docs, the compiler error index, Cargo book, clippy lints, the Brown interactive Book fork, and the Brown C++-to-Rust phrasebook) instead of from memory, using a version-pinned local mirror. Use this skill whenever Rust is involved at all — writing or reviewing Rust, explaining a borrow-checker or lifetime error, looking up a std signature, settling what the language actually guarantees, auditing unsafe code or FFI, making code more idiomatic, or porting C/C++ to Rust. Use it even when the question seems easy enough to answer from memory, because Rust's rules are version-specific and the mirror is pinned to the user's actual toolchain. Trigger on error codes like E0502, on phrases like "borrow checker", "lifetime", "does not live long enough", "cannot move out of", "unsafe", "trait bound", "idiomatic Rust", "clippy", and on any .rs file or Cargo.toml in the task.
---

# Oxidizer

Rust's canon is about 8 million tokens. A single std page (`Vec`) is ~96k on its
own. You cannot read it; you have to *route* into it. That is the whole job of
this skill.

Oxidizer mirrors the canon locally, pinned to the toolchain the user actually
compiles with, and gives you one CLI that returns small, budgeted slices with
citable upstream URLs.

## Why not answer from memory

Rust's rules are version-specific and change in ways that are easy to
misremember: edition defaults, lint names, what `async` closures do, which
methods are stable, what the borrow checker accepts. The mirror is built from
`rustc --print sysroot`, so it agrees with the user's compiler by construction.
When you answer from the mirror you can cite; when you answer from memory you
are guessing about a moving target.

## The one command

```bash
python3 <skill>/scripts/oxidize.py <command> [args] [--max-tokens N] [--json]
```

Set `OXIDIZER_CORPUS` if the corpus is not at the repository's `corpus/`.

| Command | Use it for |
|---|---|
| `route "<question>"` | You are not sure where to look. Returns the domain contract to load. |
| `diagnose <file.rs\|dir>` | Any question about code that fails to compile. Compiles it and attaches the error index. |
| `diagnose <path> --clippy` | Idiom review. Returns lints plus their docs. |
| `explain E0502` | A known error code. |
| `api std::vec::Vec::retain` | A signature or a method's docs. Accepts `Vec`, `Vec::retain`, or a full path. |
| `lint needless_range_loop` | What a lint wants and how to silence it. |
| `search "<query>" [--source ...]` | Locating the right document. Returns summaries, not sources. |
| `show <source>/<id> [--section H]` | Reading one document, or one section of it. |
| `manifest` | What is mirrored and whether it is stale. |

## How to work

**Start from the code, not the question.** If there is a `.rs` file or a Cargo
project in play and anything is failing, run `diagnose` on it first. The real
compiler output beats any guess about what the error might be, and `diagnose`
attaches the canon entry for each code it finds.

**Otherwise, route.** Run `route "<the user's question>"`. It names one domain
contract under `domains/`. Read that one file and follow it. It tells you which
sources are authoritative for that kind of question and in what order to consult
them.

**Load exactly one domain contract.** Loading several is the context saturation
this skill exists to prevent. If `route` returns two, pick the first unless the
question is obviously about the second.

**Retrieve before answering.** `search` returns titles and summaries so you can
choose; it is not a source. Follow it with `show` or `api` and read the actual
text before you commit to an answer.

**Spend the budget deliberately.** Every command defaults to ~2000 tokens and
tells you when it truncated, along with the section headings it withheld. Prefer
narrowing (`--section`, or `api Type::method` instead of `api Type`) over raising
`--max-tokens`. Raise the budget only when you have a reason to believe the
answer is in the part that got cut.

**Cite what you used.** Every command prints the upstream `doc.rust-lang.org`
URL for what it returned. Include it. The user should be able to check you.

## Answering

Lead with the answer, then the evidence. For a compile error, say what the
compiler is actually objecting to and why the rule exists before showing the
fix — the fix is rarely the useful part. Show corrected code the user can paste.
If the canon does not settle the question, say so rather than filling the gap
from memory; "the Reference doesn't specify this" is a real and useful answer.

When the mirror and your recollection disagree, the mirror wins. It is pinned to
the compiler that will actually run the code.

## Layout

This skill follows the Model Workspace Protocol (folder structure as agent
architecture). Layers load on demand rather than all at once:

```
SKILL.md              Layer 0  identity + routing map        (you are here)
CONTEXT.md            Layer 1  corpus map: what each source is good for
domains/NN_*/         Layer 2  one contract per question type
corpus/               Layer 3  the mirrored canon (generated; see references/)
```

Read `CONTEXT.md` when you need to choose a source by hand rather than via
`route`. Read `references/corpus.md` when the corpus is missing, stale, or you
need to change what is mirrored. Read `references/mwp-adaptation.md` for how
this layout deviates from the paper and why.

## If the corpus is missing

`oxidize.py` will say so and exit. Build it:

```bash
rustup component add rust-docs          # ~750MB, one time
python3 <skill>/scripts/mirror.py --online
```

`--online` adds the two Brown University sources, which have no offline
equivalent. Everything else comes from the local toolchain. Tell the user what
you are doing before a first build — it takes a couple of minutes.
