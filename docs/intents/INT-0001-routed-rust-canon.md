# INT-0001 — Routed Rust Canon

<!-- sprint-loop-intent-v2 -->
- **Intent ID:** INT-0001
- **State:** realized
- **Work evidence:** [Sprint 0 research](../sprints/s0/sprint-research/research-report.md)
- **Completion evidence:** [T-001 completion](../work/completed-tasks.md#t-001-sprint-0)
- **Code evidence:** [skills/oxidizer/SKILL.md](../../skills/oxidizer/SKILL.md), [skills/oxidizer/scripts/oxidize.py](../../skills/oxidizer/scripts/oxidize.py), [skills/oxidizer/scripts/mirror.py](../../skills/oxidizer/scripts/mirror.py)
- **Test evidence:** [tests/run_tests.py](../../tests/run_tests.py)
- **Documentation evidence:** [README.md](../../README.md), [skills/oxidizer/CONTEXT.md](../../skills/oxidizer/CONTEXT.md)

## Intent

Provide situational access to the official Rust documentation canon (~8M
tokens, ~5,200 documents) through a locally-mirrored, version-pinned corpus
with budgeted retrieval. The skill routes questions into eight domain contracts,
retrieves from the correct authoritative source, and enforces token budgets so
that the full canon can be queried without saturating a context window.

Non-goals: mirroring third-party crate documentation, replacing the official
docs, or providing opinionated guidance beyond what the canon states.

## Acceptance criteria

1. The corpus mirrors The Book, Rust By Example, the Reference, the
   Rustonomicon, std API docs, the compiler error index, Cargo book, clippy
   lints, edition guide, style guide, and the Brown University sources.
2. The corpus is built from `rustc --print sysroot`, agreeing with the user's
   actual toolchain by construction.
3. Domain routing directs questions to the correct contract (8 domains).
4. Token budgets are enforced in code, not by instruction.
5. Every retrieval result carries a citable upstream URL.
6. The test suite verifies retrieval correctness against real compiler output.

## Rationale

Rust's documentation canon is too large to load into a context window (~8M
tokens), yet too precise to answer from memory — edition defaults, lint names,
method stability, and borrow-checker rules change across versions. The skill
solves this by routing into the canon rather than summarizing it, and by pinning
to the installed toolchain rather than fetching from the web.

## Alternatives

- **Fetching from doc.rust-lang.org at query time.** Rejected: always serves
  stable-latest, which disagrees with projects pinned to older toolchains in
  precisely the cases where correctness matters most.
- **Embedding the full canon in every prompt.** Rejected: 8M tokens exceeds any
  current context window. The retrieval budget (~2,000 tokens per query) is the
  design constraint.
- **Using a vector database.** Rejected: the corpus structure (source hierarchy,
  member lists, section headings) provides better routing signal than embedding
  similarity for this domain.

## Consequences

- The corpus requires ~250MB on disk and `rustup component add rust-docs`.
- Mirror rebuild takes ~30 seconds and must be re-run when the toolchain
  updates.
- Third-party crate docs are explicitly out of scope.

## Transition history

- 2026-08-28: created as `realized` during Sprint 0 (Sprint-Loop conversion).
  All acceptance criteria satisfied by existing implementation.
