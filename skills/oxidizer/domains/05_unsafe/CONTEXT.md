# Layer 2 — 05_unsafe: unsafe, UB, FFI, variance

The user is writing or reviewing code where the compiler has stopped checking
and the obligations have moved to them.

## Inputs

| What | Where from | Load when |
|---|---|---|
| The invariants | `oxidize search "<topic>" --source nomicon` then `show` | Always |
| Safety contract of a std API | `oxidize api <path>` — read its `# Safety` section | Calling any `unsafe` std fn |
| Normative rules | `--source reference`, especially `behavior-considered-undefined` | Deciding whether something is UB |

## Process

1. Read the Nomicon page for the specific mechanism. Do not generalise from
   "unsafe means be careful" — each construct has a precise contract.
2. For any `unsafe` std function, read its `# Safety` section verbatim. That
   section *is* the contract; it enumerates exactly what the caller must
   guarantee.
3. Identify which invariants the user's code must uphold, and check each one
   against what their code actually does.
4. Say plainly whether the code is sound, unsound, or you cannot tell without
   information you do not have. Hedging on soundness is not kindness.
5. Recommend `cargo +nightly miri test` where it applies. Miri catches a large
   class of UB that neither rustc nor review reliably will.

## The obligations that actually get violated

- **Aliasing.** A `&mut T` must be unique for its whole lifetime. Producing two
  from one raw pointer is UB even if you never use them simultaneously.
- **Validity.** Every value must always be valid for its type — no uninitialised
  `bool`, no null `&T`, no invalid `char`. Use `MaybeUninit`, and note that
  `mem::uninitialized` is deprecated precisely because it is unsound.
- **Lifetimes.** `transmute`ing a lifetime, or returning a reference derived from
  a raw pointer, silently invents a lifetime the compiler will then trust.
- **`Send`/`Sync`.** A manual `unsafe impl` is a claim you must actually justify.
- **FFI.** The C side's contract is not checked. Ownership of allocations,
  nullability, and string encoding all have to be established by hand — and
  memory allocated by C must be freed by C, not by Rust.
- **Panics across FFI.** Unwinding into C is UB unless the ABI is `extern
  "C-unwind"`. Wrap in `catch_unwind` at the boundary.

## Encapsulation

The point of `unsafe` is not to make a function unsafe but to build a safe
abstraction over it. Push the user toward the smallest possible `unsafe` block
with a documented invariant around it, rather than an `unsafe fn` that spreads
the obligation to every caller.

Every `unsafe fn` needs a `/// # Safety` doc comment stating its contract. The
`missing_safety_doc` lint enforces this; if it is absent, flag it.

## Outputs

- Sound / unsound / cannot determine — stated directly.
- The specific invariant at issue, and whether the code upholds it.
- A safe alternative if one exists. Very often there is one, and it is faster
  than the user assumes.
- Nomicon and Reference URLs.

## Hand off

- A safe API does the job → `03_api`
- The question is really about what is guaranteed → `04_spec`
- The unsafe code does not compile → `01_diagnose`
