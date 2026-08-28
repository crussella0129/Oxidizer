# Test Critique — Sprint 0

## Concerns

### C-001: Evidence drift — tested commit not recorded
- **Where:** `unit-tests.md`, `integration-tests.md`, `e2e-tests.md`
- **Quote:** (no commit SHA cited in test results)
- **Failure mode:** evidence-drift
- **Why it matters:** Test results should identify the exact commit they were run against for reproducibility.
- **Suggested response:** defer-with-rationale — this is a governance-only sprint with no production code changes. The tested state is the HEAD of main after the three T-00N commits, which are recorded in `completed-tasks.md`. Adding explicit SHAs to test artifacts would be good practice for future sprints with code changes.

## Confidence
proceed-with-caveats
