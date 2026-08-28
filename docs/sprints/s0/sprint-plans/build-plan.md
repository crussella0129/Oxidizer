Finalized - DO NOT EDIT

# Sprint 0 Build Plan

## Intents
- [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md) — state: planned; acceptance criteria covered: 1, 2, 3, 4, 5

## Schema Tree
- Sprint Goal: Establish Sprint-Loop governance over the Oxidizer project
  - Governance Artifacts
    - T-001: Establish Book and intent chapters
    - T-002: Record realized capabilities in the completed-tasks ledger
    - T-003: Update sprint metadata with goal and intents

## Execution Sequence

### T-001: Establish Book and intent chapters
- **Intent:** [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md)
- **Touches:** `docs/intents/INT-0001-routed-rust-canon.md`, `docs/intents/INT-0002-agent-agnostic-mcp-server.md`, `docs/intents/INT-0003-sprint-loop-governance.md`, `docs/SUMMARY.md`, `docs/README.md`
- **Depends on:** (none)
- **Acceptance criterion:** The Project Book exists with schema v2, containing README, SUMMARY, intents, work ledgers, and sprint provenance (AC-1). Intent chapters exist for all realized project capabilities (AC-2).
- **Success criterion (EARS):**
  - **WHEN** `check-book.sh` is run from the project root, **THEN** the validator **SHALL** report no schema errors for the Book structure.
  - **WHEN** `docs/intents/` is listed, **THEN** it **SHALL** contain INT-0001, INT-0002, and INT-0003, each with the `sprint-loop-intent-v2` marker and valid state.
  - **WHEN** `docs/SUMMARY.md` is read, **THEN** it **SHALL** contain navigation links to all three intent chapters.
- **Notes:** INT-0001 and INT-0002 are created as `realized` (retroactively documenting existing capabilities). INT-0003 transitions `proposed` → `planned`. The Book scaffold was created by `deploy-substrate.sh`.

### T-002: Record realized capabilities in the completed-tasks ledger
- **Intent:** [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md)
- **Touches:** `docs/work/completed-tasks.md`
- **Depends on:** T-001
- **Acceptance criterion:** Intent chapters exist for all realized project capabilities with proper evidence links (AC-2).
- **Success criterion (EARS):**
  - **WHEN** `docs/work/completed-tasks.md` is read, **THEN** it **SHALL** contain a `T-001` entry referencing Sprint 0 with links to INT-0001 and INT-0002.
  - **WHEN** INT-0001 and INT-0002 Completion evidence is followed, **THEN** each link **SHALL** resolve to the completed-tasks entry.
- **Notes:** This is a retroactive record — the capabilities already exist. The ledger entry documents the mapping between intents and existing work.

### T-003: Update sprint metadata with goal and intents
- **Intent:** [INT-0003](../../../intents/INT-0003-sprint-loop-governance.md)
- **Touches:** `docs/sprints/s0/sprint-meta.md`
- **Depends on:** T-001
- **Acceptance criterion:** Sprint 0 completes with all phases passing (AC-5).
- **Success criterion (EARS):**
  - **WHEN** `docs/sprints/s0/sprint-meta.md` is read, **THEN** it **SHALL** contain a non-empty Summary field and an Intents field listing INT-0001, INT-0002, and INT-0003.
  - **WHEN** `current-phase.sh` is run after all phases complete, **THEN** it **SHALL** report phase progression through research → plan → build → test → loop.
- **Notes:** The metadata is updated during the plan phase (Summary, Intents) and completed during the loop phase (End timestamp, Exit status).
