Finalized - DO NOT EDIT

# Sprint 1 Build Plan

## Intents
- [INT-0004](../../../intents/INT-0004-developer-experience.md) — state: planned; acceptance criteria covered: 1, 2, 3, 4, 5, 6, 7

## Schema Tree
- Sprint Goal: Add project-specific CLAUDE.md
  - Developer Experience
    - T-004: Create project-specific CLAUDE.md

## Execution Sequence

### T-004: Create project-specific CLAUDE.md
- **Intent:** [INT-0004](../../../intents/INT-0004-developer-experience.md)
- **Touches:** `CLAUDE.md`
- **Depends on:** (none)
- **Acceptance criterion:** A CLAUDE.md exists at the project root with build, test, lint, structure, and workflow documentation (AC-1 through AC-7).
- **Success criterion (EARS):**
  - **WHEN** a new Claude Code session opens the Oxidizer project, **THEN** it **SHALL** find a `CLAUDE.md` at the project root with corpus build, MCP server build, test, and lint commands.
  - **WHEN** the CLAUDE.md is read, **THEN** it **SHALL** contain the `mirror.py --online` command and its `rustup component add rust-docs` prerequisite.
  - **WHEN** the CLAUDE.md is read, **THEN** it **SHALL** contain `cargo build` in `mcp/oxidizer-mcp/` for the MCP server.
  - **WHEN** the CLAUDE.md is read, **THEN** it **SHALL** contain `tests/run_tests.py --mcp` for the test suite.
  - **WHEN** the CLAUDE.md is read, **THEN** it **SHALL** contain formatting/linting commands for both Rust and Python.
  - **WHEN** the CLAUDE.md is read, **THEN** it **SHALL** describe the project structure (skill, MCP server, tests, corpus, docs).
  - **WHEN** the CLAUDE.md is read, **THEN** it **SHALL** reference the Sprint-Loop workflow and the `docs/` Book.
- **Notes:** This is a new file, not a modification of an existing one.
