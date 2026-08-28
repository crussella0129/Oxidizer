# Sprint 0 Unit Tests

## T-001 unit tests
- `test_book_schema_valid`: `check-book.sh` exits 0, reports "valid v2 Book (3 intent chapters)" — **PASS**
- `test_intent_chapters_exist`: All three INT files exist with `sprint-loop-intent-v2` marker — **PASS**
- `test_intent_states_valid`: INT-0001=realized, INT-0002=realized, INT-0003=active — **PASS**
- `test_summary_links`: `docs/SUMMARY.md` contains 3 intent chapter links — **PASS**

## T-002 unit tests
- `test_completed_tasks_entry`: `docs/work/completed-tasks.md` contains T-001, T-002, T-003 entries for sprint 0 — **PASS**
- `test_evidence_links_resolve`: INT-0001 and INT-0002 Completion evidence links point to `completed-tasks.md#t-001-sprint-0` — **PASS**

## T-003 unit tests
- `test_sprint_meta_complete`: `sprint-meta.md` has non-empty Summary and Intents fields — **PASS**
