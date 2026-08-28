# INT-0003 — Sprint-Loop Governance

<!-- sprint-loop-intent-v2 -->
- **Intent ID:** INT-0003
- **State:** realized
- **Work evidence:** [T-001 build plan](../sprints/s0/sprint-plans/build-plan.md#t-001-establish-book-and-intent-chapters)
- **Completion evidence:** [T-001 completion](../work/completed-tasks.md#t-001-sprint-0), [T-002 completion](../work/completed-tasks.md#t-002-sprint-0), [T-003 completion](../work/completed-tasks.md#t-003-sprint-0)
- **Code evidence:** [docs/.sprint-loop-book](../../docs/.sprint-loop-book)
- **Test evidence:** [Sprint 0 test report](../sprints/s0/sprint-tests/test-report.md)
- **Documentation evidence:** [docs/README.md](../README.md), [docs/SUMMARY.md](../SUMMARY.md)

## Intent

Establish the Sprint-Loop workflow as the project's development governance
structure. All future work proceeds through numbered sprints with research,
plan, build, test, and loop phases. The Project Book tracks intent chapters,
work state, and sprint provenance.

Non-goals: changing existing production code or skill functionality during this
conversion sprint.

## Acceptance criteria

1. The Project Book (docs/) exists with schema v2, containing README, SUMMARY,
   intents, work ledgers, and sprint provenance.
2. Intent chapters exist for all realized project capabilities (INT-0001,
   INT-0002) with proper evidence links.
3. The `dev` branch exists as the work branch; `main` remains the base branch.
4. The remote profile declares `github` provider with `human-approve` merge
   policy.
5. Sprint 0 completes with all phases passing.
6. Future development can be initiated with `/sprint-loop start <goal>`.

## Rationale

The project has reached functional maturity but lacks a structured development
workflow. Commits have been ad-hoc with no durable intent declarations, work
tracking, or sprint provenance. The Sprint-Loop workflow provides bounded
sprints with research-backed plans, evidence-gated phase transitions, and
auditable history — governance that matches the project's quality bar.

## Alternatives

- **Continue ad-hoc development.** Rejected: the project is mature enough that
  changes benefit from research and planning rather than direct commits.
- **Use GitHub Issues/Projects alone.** Rejected: does not provide the
  research-plan-build-test loop or intent-level tracking.

## Consequences

- Every future change goes through a sprint, adding overhead for trivial fixes.
  This is acceptable for a project where correctness (matching the compiler's
  actual behavior) is the primary value proposition.
- The `docs/` directory grows with each sprint's provenance artifacts.

## Transition history

- 2026-08-28: created as `proposed` during Sprint 0 research.
- 2026-08-28: `proposed` → `planned`. Sprint 0 plan accepted.
- 2026-08-28: `planned` → `active`. Sprint 0 build phase started.
- 2026-08-28: `active` → `realized`. All acceptance criteria satisfied. Sprint 0 complete.
