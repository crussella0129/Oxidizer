Finalized - DO NOT EDIT

# Sprint 1 Test Plan

## Intent Traceability
| Intent | Acceptance criterion | Build task / EARS clause | Verification |
|--------|----------------------|--------------------------|--------------|
| [INT-0004](../../../intents/INT-0004-developer-experience.md) | AC-1: CLAUDE.md exists | T-004 / WHEN session opens THEN SHALL find CLAUDE.md | test_claude_md_exists |
| [INT-0004](../../../intents/INT-0004-developer-experience.md) | AC-2: Corpus build documented | T-004 / WHEN read THEN SHALL contain mirror.py | test_corpus_build_documented |
| [INT-0004](../../../intents/INT-0004-developer-experience.md) | AC-3: MCP build documented | T-004 / WHEN read THEN SHALL contain cargo build | test_mcp_build_documented |
| [INT-0004](../../../intents/INT-0004-developer-experience.md) | AC-4: Tests documented | T-004 / WHEN read THEN SHALL contain run_tests.py | test_tests_documented |
| [INT-0004](../../../intents/INT-0004-developer-experience.md) | AC-5: Lint commands documented | T-004 / WHEN read THEN SHALL contain fmt/clippy/ruff | test_lint_documented |
| [INT-0004](../../../intents/INT-0004-developer-experience.md) | AC-6: Structure documented | T-004 / WHEN read THEN SHALL describe structure | test_structure_documented |
| [INT-0004](../../../intents/INT-0004-developer-experience.md) | AC-7: Sprint-Loop referenced | T-004 / WHEN read THEN SHALL reference workflow | test_workflow_referenced |

## Unit Tests
### T-004 unit tests
- **Intent:** [INT-0004](../../../intents/INT-0004-developer-experience.md)
- `test_claude_md_exists`: `CLAUDE.md` exists at the project root
- `test_corpus_build_documented`: contains `mirror.py` and `rustup component add rust-docs`
- `test_mcp_build_documented`: contains `cargo build` and `mcp/oxidizer-mcp`
- `test_tests_documented`: contains `run_tests.py` and `--mcp`
- `test_lint_documented`: contains `cargo fmt`, `cargo clippy`, `ruff format`, `ruff check`
- `test_structure_documented`: contains references to `skills/oxidizer/`, `mcp/oxidizer-mcp/`, `tests/`, `corpus/`
- `test_workflow_referenced`: contains `sprint-loop` or `Sprint-Loop` and `docs/`

## Integration Tests
### Book integrity
- **Intents:** [INT-0004](../../../intents/INT-0004-developer-experience.md)
- `test_book_still_valid`: `check-book.sh` passes after CLAUDE.md is added

## End-to-End Tests
- **Status:** not-yet-possible
- Unlocked by: a session that opens the project for the first time and uses CLAUDE.md to successfully build the corpus and run tests. This requires a fresh session, which cannot be simulated within this sprint.
