# INT-0004 — Developer Experience

<!-- sprint-loop-intent-v2 -->
- **Intent ID:** INT-0004
- **State:** active
- **Work evidence:** [T-004 build plan](../sprints/s1/sprint-plans/build-plan.md#t-004-create-project-specific-claudemd)
- **Completion evidence:** none
- **Code evidence:** none
- **Test evidence:** none
- **Documentation evidence:** none

## Intent

Provide project-specific development instructions via a root CLAUDE.md so that
agent and human contributors can build, test, lint, and navigate the Oxidizer
project without rediscovering toolchain requirements or command incantations.

Non-goals: duplicating the user-facing README, adding CI/CD, or creating
`.claude/settings.json` permissions (those belong to the user's own
configuration).

## Acceptance criteria

1. A `CLAUDE.md` exists at the project root.
2. It documents the corpus build command (`mirror.py --online`) and its
   prerequisite (`rustup component add rust-docs`).
3. It documents how to build the MCP server (`cargo build` in
   `mcp/oxidizer-mcp/`).
4. It documents how to run the test suite (`tests/run_tests.py --mcp`).
5. It documents the project's formatting/linting commands for both Rust and
   Python code.
6. It orients the reader to the project structure (skill layer, MCP server,
   tests, corpus).
7. It references the Sprint-Loop workflow and `docs/` Book.

## Rationale

The project has two languages (Rust, Python), a generated corpus that needs
rebuilding, an MCP server that needs compiling, and a test suite that depends
on both. Without project-specific instructions, every new session burns context
rediscovering these relationships. The global CLAUDE.md covers language
preferences but not project-specific commands.

## Alternatives

- **Rely on README.md alone.** Rejected: the README is user-facing
  documentation; CLAUDE.md is agent-oriented development instructions. They
  serve different audiences and have different lifespans.
- **Add instructions to docs/README.md.** Rejected: the Book README is about
  project governance, not development workflow.

## Consequences

- One more file to keep in sync with the project's actual build/test
  commands. Mitigated: CLAUDE.md should reference commands rather than
  re-documenting behavior, so drift surface is small.

## Transition history

- 2026-08-28: created as `proposed` during Sprint 1 research.
- 2026-08-28: `proposed` → `planned`. Sprint 1 plan accepted.
- 2026-08-28: `planned` → `active`. Sprint 1 build phase started.
