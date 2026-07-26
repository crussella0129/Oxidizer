# Layer 2 — 02_learn: explain a concept

The user wants to understand something, not fix a specific failure.

## Inputs

| What | Where from | Load when |
|---|---|---|
| The teaching narrative | `oxidize search "<concept>" --source book` then `show` | Always |
| Interactive treatment | `--source brown-book` | The user's mental model is *wrong*, not just absent |
| A runnable example | `--source rust-by-example` | The user learns better from code |
| Exact rules | `--source reference` | Only if the user asks for precision |

## Process

1. `oxidize search "<concept>" --source book brown-book rust-by-example`.
2. `show` the best hit. Read it before explaining. The Book's framing of
   ownership, lifetimes, and traits is carefully built and hard to improve on
   from memory.
3. Explain in your own words, at the user's level. Do not paste the chapter.
4. Give a small example the user can run. Prefer adapting the canon's example
   to the user's actual situation over inventing a new one.
5. Link the chapter so they can go deeper.

## Choosing between the Book and the Brown fork

Use `brown-book` when the user has stated a belief that is wrong ("I thought
`&mut` meant it copies", "doesn't the borrow end at the last line?"). Its
ownership-inspector diagrams show what actually happens to the stack and heap at
each step, which is the fastest correction for a broken model.

Use plain `book` when the user simply has not met the concept yet.

## Calibrate to the user

Someone who says "I'm new to Rust" and someone who says "I know Rust but not
async" need different answers. Match their vocabulary. If they came from another
language and say so, `07_migrate` may serve them better than a from-scratch
explanation — the phrasebook translates rather than teaches.

Do not front-load caveats. Get the mental model across first; edge cases can
follow if they ask.

## Outputs

- A direct explanation at the right level.
- One small, runnable example.
- The chapter URL.

## Hand off

- They actually have failing code → `01_diagnose`
- They want the exact rule, not the intuition → `04_spec`
- The concept is `unsafe`, variance, or UB → `05_unsafe`
