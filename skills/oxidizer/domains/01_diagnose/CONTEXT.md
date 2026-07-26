# Layer 2 — 01_diagnose: it does not compile

The user has code the compiler rejects, or an error they do not understand.

## Inputs

| What | Where from | Load when |
|---|---|---|
| The failing code | The user, or a path in the repo | Always |
| Real compiler output | `oxidize diagnose <path>` | Always — do not skip this |
| Error index entry | Attached by `diagnose`, or `oxidize explain E####` | Always |
| Conceptual background | `oxidize show book/<chapter>` | The user is confused about *why*, not just *what* |
| Normative detail | `oxidize show reference/<page>` | The error hinges on an exact rule |

## Process

1. **Compile it.** `oxidize diagnose <file.rs or project dir>`. If the code only
   exists in the conversation, write it to a file first. Never reason about what
   the error "would be" — Rust's diagnostics are specific, and guessing at them
   is where wrong answers come from.
2. **Read the actual message, not just the code.** The `help:` and `note:`
   children of a rustc diagnostic frequently contain the fix outright. They are
   included in `diagnose` output.
3. **Read the canon entry** that `diagnose` attached for each error code.
4. **Explain the rule before the fix.** The user usually hits the same class of
   error again; the fix alone does not transfer, the rule does.
5. **Verify your fix compiles.** Apply it and re-run `diagnose`. A fix that
   trades E0502 for E0499 is not a fix, and this is common enough with borrow
   errors that checking is worth it every time.

## Reading borrow-checker errors specifically

Ownership errors are the ones most often answered wrongly, because the obvious
fix (`.clone()`, `Rc<RefCell<_>>`) usually works while being wrong. Work through
the actual conflict first:

- Which two borrows overlap, and where does each start and end?
- Does the borrow need to live that long, or is it just being held in a wider
  scope than necessary? Narrowing scope beats cloning.
- Is this really shared mutation, or a sequencing problem? Splitting into two
  statements resolves a large fraction of E0502s.
- Only when the data genuinely needs shared ownership should `Rc`/`Arc` appear,
  and only when it genuinely needs shared *mutation* should `RefCell`/`Mutex`.

Reach for `.clone()` when the cost is trivially small and the alternative is
contorted — and say so explicitly, so the user knows it was a choice.

## Common codes

`oxidize explain <code>` for any of these; the index has a minimal repro for each.

| Code | What it is |
|---|---|
| E0382 | Use after move |
| E0499 | Two mutable borrows at once |
| E0502 | Mutable borrow while an immutable one is live |
| E0505 | Move out of a value that is borrowed |
| E0506 | Assign to a borrowed value |
| E0106 | Missing lifetime specifier |
| E0597 | Value does not live long enough |
| E0308 | Mismatched types |
| E0277 | Trait bound not satisfied |
| E0596 | Mutable borrow of an immutable binding |

## Outputs

- What the compiler is objecting to, in plain language.
- Why the rule exists — one or two sentences, not a lecture.
- Corrected code the user can paste, verified by a second `diagnose` run.
- The `doc.rust-lang.org` URL for the error code.

## Hand off

- The fix is correct but ugly → `06_idiom`
- The error is in or around `unsafe` → `05_unsafe`
- The user's underlying model of ownership is missing → `02_learn`
