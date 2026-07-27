# Layer 1 — Corpus map

Which source is authoritative for which kind of claim. Read this when you are
choosing a source by hand instead of via `oxidize route`.

The ordering principle: **the most specific authority wins.** For a compile
error that is the error index; for "what does the language guarantee" it is the
Reference; for "how do I think about this" it is the Book. Reaching for the Book
to settle a normative question, or the Reference to teach a beginner, is the
most common way to answer confidently and wrongly.

## Sources

| Source | Authoritative for | Not authoritative for |
|---|---|---|
| `error-index` | What a specific `E####` means, with a minimal repro and fix | Why the rule exists |
| `book` | Teaching a concept; the mental model | Edge cases, exact semantics |
| `brown-book` | Same as `book`, plus ownership diagrams and quizzes. Better when the user's mental model is wrong, not just missing | Anything not in the Book |
| `rust-by-example` | Short runnable examples | Explanations of why |
| `std` | Signatures, trait bounds, stability, method docs | Language rules |
| `reference` | Normative language semantics: what is legal, drop order, coercions, precedence | Teaching; API |
| `nomicon` | Unsafe invariants, UB, variance, FFI, `Send`/`Sync` | Safe-Rust questions |
| `lints` | Every lint the installed toolchain knows, with default level | Rationale beyond one line |
| `style-guide` | Formatting and naming conventions | Semantics |
| `cargo` | Manifests, features, workspaces, profiles, publishing | Language questions |
| `edition-guide` | What changed between editions, migration | Current-edition semantics |
| `crp-phrasebook` | C++ idiom → Rust idiom, side by side | Rust-native design |

## Precedence when sources disagree

1. `std` and `error-index` — generated from the compiler itself, so they cannot
   drift from it.
2. `reference` — normative, but occasionally lags the implementation.
3. `nomicon` — normative for unsafe, explicitly incomplete by its own admission.
4. `book`, `brown-book`, `rust-by-example` — pedagogical. They simplify. A Book
   statement that contradicts the Reference is a simplification, not a rule.
5. `edition-guide`, `cargo`, `style-guide` — scoped to their own topic.

`lints` is generated from the installed `clippy-driver`, so it is exact about
*which* lints exist and their default levels, and thin on rationale. For the
reasoning behind a lint, follow up in the Book.

## Things the corpus does not cover

Be explicit with the user rather than improvising:

- **Third-party crates.** Nothing from crates.io is mirrored. `lib.rs`
  categories, named in the project brief, are not reachable from this
  environment's egress policy. For a crate question, say the canon does not
  cover it and reason from the crate's own docs if the user supplies them.
- **Nightly-only features**, unless the corpus was built with
  `--include unstable-book`.
- **`core` and `alloc`**, unless built with `--include core,alloc`. std
  re-exports most of what matters; reach for these only for `no_std` work.
- **Anything newer than the pinned toolchain.** `oxidize manifest` reports the
  version the mirror was built for and warns when the toolchain has moved.

## Operational references

Not sources — how the skill itself behaves.

| File | Read it when |
|---|---|
| `references/corpus.md` | The corpus is missing, stale, or needs different sources |
| `references/disk-hygiene.md` | Before cleaning any build tree; after a `diagnose` run |
| `references/mwp-adaptation.md` | You need to know how this layout maps to the paper |

## Domain contracts

`oxidize route` picks one of these. Each states its inputs, process, and outputs.

| Domain | Question shape |
|---|---|
| `domains/01_diagnose/CONTEXT.md` | It does not compile |
| `domains/02_learn/CONTEXT.md` | Explain a concept |
| `domains/03_api/CONTEXT.md` | What is the signature / which method |
| `domains/04_spec/CONTEXT.md` | Is this legal, what is guaranteed |
| `domains/05_unsafe/CONTEXT.md` | Unsafe, UB, FFI, variance |
| `domains/06_idiom/CONTEXT.md` | Make this idiomatic |
| `domains/07_migrate/CONTEXT.md` | Port from C/C++/another language |
