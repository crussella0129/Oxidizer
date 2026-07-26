# Layer 2 — 06_idiom: make this idiomatic

The code works. The user wants it to look like Rust.

## Inputs

| What | Where from | Load when |
|---|---|---|
| Real lints on the real code | `oxidize diagnose <path> --clippy` | Always — do not eyeball it |
| What a lint wants | `oxidize lint <name>` | For each lint fired |
| Formatting and naming | `--source style-guide` | Naming or layout questions |
| Manifest and features | `--source cargo` | `Cargo.toml`, features, workspaces |

## Process

1. **Run clippy.** `oxidize diagnose <path> --clippy` compiles the code and
   returns each lint with its documentation attached. Reviewing Rust for idiom
   without running clippy is guessing at what a tool already knows exactly.
2. For each lint, read what it wants (`oxidize lint <name>` if you need more
   than the one-line summary) and apply it.
3. Re-run to confirm the fixes landed and introduced nothing new.
4. Then look for the things clippy cannot see — see below.
5. Run `cargo fmt` rather than hand-formatting. Never argue with rustfmt.

## What clippy will not tell you

- **Types that permit invalid states.** Two `Option` fields where only certain
  combinations are legal usually wants an enum. This is the highest-value change
  and no lint finds it.
- **`String`/`Vec` in signatures where `&str`/`&[T]` would do.** Clippy catches
  the common shapes (`ptr_arg`) but not all of them.
- **Error handling.** `unwrap()` in library code, stringly-typed errors, missing
  `?`. Libraries should return concrete error types; applications can use
  `anyhow`-style boxing.
- **Iterator chains that would be clearer as a loop**, and loops that would be
  clearer as iterator chains. Clippy pushes toward iterators; past three or four
  adapters that is often the wrong direction.
- **Missing trait impls** the type obviously wants: `Debug`, `Clone`, `Default`,
  `From` rather than an ad-hoc constructor.
- **Naming.** `snake_case` items, `CamelCase` types, `SCREAMING_CASE` consts;
  `as_` for cheap borrows, `to_` for expensive conversions, `into_` for
  consuming ones. Getters are named `field()`, not `get_field()`.

## Judgement

Not every lint must be obeyed. `#[allow]` with a comment explaining why is a
legitimate outcome, and some lints (`too_many_arguments`, `type_complexity`) are
noisy in real code. Say when you are choosing to ignore one, and why.

Do not rewrite beyond what was asked. A user asking to clean up one function has
not asked for their error handling to be redesigned — mention it, do not do it.

## Outputs

- The revised code.
- What changed and why, briefly — lint name where one applies.
- Anything you deliberately left alone, and the reason.

## Hand off

- A change broke the build → `01_diagnose`
- The user disputes the rule → `04_spec`
- The refactor touches `unsafe` → `05_unsafe`
