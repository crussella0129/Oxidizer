Finalized - DO NOT EDIT

# Sprint 0 Test Plan

## Intent Traceability
| Intent | Acceptance criterion | Build task / EARS clause | Verification |
|--------|----------------------|--------------------------|--------------|
| [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md) | AC-1: Book exists with schema v2 | T-001 / WHEN check-book.sh runs THEN SHALL report no errors | test_book_schema_valid |
| [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md) | AC-2: Intent chapters for realized capabilities | T-001 / WHEN intents listed THEN SHALL contain INT-0001, INT-0002, INT-0003 | test_intent_chapters_exist |
| [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md) | AC-2: Evidence links resolve | T-002 / WHEN Completion evidence followed THEN SHALL resolve | test_evidence_links_resolve |
| [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md) | AC-3: dev branch exists | substrate / WHEN branches listed THEN SHALL include dev | test_dev_branch_exists |
| [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md) | AC-4: Remote profile configured | substrate / WHEN remote-profile.sh runs THEN SHALL report github | test_remote_profile_valid |
| [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md) | AC-5: Sprint 0 completes | T-003 / WHEN sprint-meta read THEN SHALL have Summary and Intents | test_sprint_meta_complete |

## Unit Tests
### T-001 unit tests
- **Intent:** [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md)
- `test_book_schema_valid`: Run `check-book.sh` from project root → exits 0 with no error diagnostics
- `test_intent_chapters_exist`: Verify `docs/intents/INT-0001-*.md`, `INT-0002-*.md`, `INT-0003-*.md` all exist with `sprint-loop-intent-v2` marker
- `test_intent_states_valid`: INT-0001 state is `realized`, INT-0002 state is `realized`, INT-0003 state is `planned` or later
- `test_summary_links`: `docs/SUMMARY.md` contains links to all three intent chapters

### T-002 unit tests
- **Intent:** [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md)
- `test_evidence_links_resolve`: INT-0001 and INT-0002 Completion evidence links point to `completed-tasks.md` with an anchor that exists
- `test_completed_tasks_entry`: `docs/work/completed-tasks.md` contains a `T-001` entry referencing Sprint 0

### T-003 unit tests
- **Intent:** [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md)
- `test_sprint_meta_complete`: `sprint-meta.md` has non-empty Summary and Intents fields

## Integration Tests
### Governance structure integration
- **Intents:** [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md)
- `test_dev_branch_exists`: `git branch` lists `dev`
- `test_remote_profile_valid`: `remote-profile.sh` reports PROVIDER=github, BASE=main, WORK=dev
- `test_substrate_complete`: `check-substrate.sh` reports `substrate-complete`

## End-to-End Tests
- **Status:** possible
- `test_full_sprint_lifecycle`: After Sprint 0 loop phase completes, `current-phase.sh` reports `ready-for-next-sprint`, and a new sprint can be initialized with `init-sprint.sh`
