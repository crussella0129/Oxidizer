# Layer 2 — 08_implement: write a working implementation

The user wants code that does a specific thing — a data structure, an algorithm
— not an explanation of a language feature.

This domain exists because the canon has a real gap. The Book teaches concepts,
the Reference states rules, `std` documents APIs, and Rust By Example shows
five-line snippets. None of them contains a complete, compiling red-black tree.

## Inputs

| What | Where from | Load when |
|---|---|---|
| A worked implementation | `oxidize search "<thing>" --source algorithms` then `show` | The corpus has it |
| Whether `std` already does it | `oxidize api <Type>` | **First, always** |
| Language mechanics you need | `--source book`, `--source rust-by-example` | The implementation uses something unfamiliar |
| Unsafe internals | `--source nomicon` | The structure needs raw pointers |

## Process

1. **Check `std` first.** A large share of "implement X" requests are already
   solved: `BinaryHeap`, `BTreeMap`, `HashMap`, `VecDeque`, `sort_unstable`,
   `binary_search`. Reaching for a hand-rolled version when `std` has a better
   one is the most common failure in this domain. Only proceed if the user wants
   it for learning, or genuinely needs behaviour `std` does not provide.
2. `oxidize search "<thing>" --source algorithms` and `show` the best hit.
3. **Read it critically, then write your own.** See the warning below — this
   source is not canon and must not be pasted through unexamined.
4. Compile what you produce: `oxidize diagnose <file.rs>`, then
   `--clippy` for idiom.
5. Cite the example as a reference you consulted, not as an authority.

## This source is not canon

Everything else Oxidizer mirrors is normative or compiler-generated. The
`algorithms` source is a community repository — illustrative, lowest precedence,
and explicitly **not** an idiom authority.

Its own `Cargo.toml` allows lints that `06_idiom` will tell the user to fix.
`oxidize manifest` prints the current list; at the time of writing it includes
`needless_range_loop`, `needless_return`, `unwrap_used`, `expect_used`,
`indexing_slicing`, and `panic`. That is a defensible choice for teaching
material — an index loop is often clearer in an algorithms textbook — but it is
not the posture this skill recommends for production code.

Measured against the four default-warn style lints the repo opts out of, 9 of
its 423 files trip at least one. So the code is mostly fine; the point is that
you cannot *assume* it is, and you must not present it as exemplary Rust.

**When adapting an example:**

- Run `oxidize diagnose <your version> --clippy` and fix what fires. Do not
  inherit the example's allow-list.
- Replace `unwrap()`/`panic!` with `Result` if the code is going into a library.
- Check the generic bounds are the ones the user actually needs, not the ones
  the example happened to pick.
- Prefer slices (`&[T]`) over `&Vec<T>` in signatures.
- Keep the tests. They are usually the clearest statement of intended usage, and
  they are extracted into their own section of each document.

## If the corpus is not present

`algorithms` is opt-in and off by default. If `route` says it is not mirrored,
either build it —

```bash
python3 scripts/mirror.py --algorithms
```

— or answer from `std` plus your own knowledge and say that is what you did. Do
not pretend to have consulted a source that is not there.

## Outputs

- Working code, compiled and clippy-checked, in the user's own naming style.
- A note on whether `std` already solves this, if it does.
- Complexity, when it is the reason for choosing one approach over another.
- Attribution to the example consulted, flagged as community code rather than
  canon.

## Hand off

- It does not compile → `01_diagnose`
- It compiles but reads badly → `06_idiom`
- The user needs the concept, not the code → `02_learn`
- The structure needs raw pointers or `unsafe` → `05_unsafe`
