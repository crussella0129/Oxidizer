# Sprint 1 Research Report

## Sprint Goal

Add a project-specific CLAUDE.md with build, test, and development instructions
so that future Claude Code sessions can work on the Oxidizer project effectively
without rediscovering toolchain requirements, test commands, or project
conventions.

## Existing Code Survey

**6 project files reviewed.**

### Build and test infrastructure
- `mcp/oxidizer-mcp/Cargo.toml`: Rust crate, edition 2024, depends on rmcp
  2.2, tokio, serde, schemars, tracing.
- `tests/run_tests.py`: Python test harness, 86 assertions, supports `--mcp`
  flag for MCP parity tests. Requires a built corpus.
- `skills/oxidizer/scripts/mirror.py`: stdlib-only Python 3, builds the corpus
  from the local toolchain. `--online` adds Brown University sources.

### Current developer experience
- No `CLAUDE.md` exists. The global CLAUDE.md covers language preferences
  (Rust-first, Python fallback) and formatting rules, but nothing project-
  specific.
- No `.claude/settings.json` exists.
- The README.md has a quick-start section but is user-facing documentation,
  not agent instructions.

### Key commands a developer (or agent) needs to know
1. `rustup component add rust-docs` — prerequisite for corpus build
2. `python3 skills/oxidizer/scripts/mirror.py --online` — build the corpus
3. `cd mcp/oxidizer-mcp && cargo build --release` — build the MCP server
4. `python3 tests/run_tests.py --mcp` — run the full test suite
5. `cargo fmt` / `cargo clippy` — in `mcp/oxidizer-mcp/`
6. `ruff format` / `ruff check` — on Python files (per global CLAUDE.md)

## External Sources

None required.

## Risks / Unknowns / Dependencies

1. **CLAUDE.md scope.** Should focus on what an agent needs to work on this
   project, not duplicate the README. Risk: low — the boundary is clear.

## Recommended Approach

Create a single `CLAUDE.md` at the project root with sections for:
- Project overview (one paragraph)
- Build commands (corpus, MCP server)
- Test commands
- Code formatting/linting
- Project structure orientation
- Sprint-Loop workflow notes

Create a new intent (INT-0004) for developer experience, since this is a
distinct concern from the existing intents.

## Intents Reviewed

- [INT-0004 — Developer Experience](../../intents/INT-0004-developer-experience.md):
  created as `proposed`. Project-specific CLAUDE.md and development tooling
  instructions for agent and human contributors.

## Referenced Artifacts

- `mcp/oxidizer-mcp/Cargo.toml` — Rust build config
- `tests/run_tests.py` — test harness
- `skills/oxidizer/scripts/mirror.py` — corpus builder
- `README.md` — existing user-facing docs
