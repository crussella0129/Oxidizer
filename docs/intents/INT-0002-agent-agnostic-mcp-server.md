# INT-0002 — Agent-Agnostic MCP Server

<!-- sprint-loop-intent-v2 -->
- **Intent ID:** INT-0002
- **State:** realized
- **Work evidence:** [Sprint 0 research](../sprints/s0/sprint-research/research-report.md)
- **Completion evidence:** [T-001 completion](../work/completed-tasks.md#t-001-sprint-0)
- **Code evidence:** [mcp/oxidizer-mcp/src/main.rs](../../mcp/oxidizer-mcp/src/main.rs), [mcp/oxidizer-mcp/src/corpus.rs](../../mcp/oxidizer-mcp/src/corpus.rs)
- **Test evidence:** [tests/run_tests.py](../../tests/run_tests.py) (MCP parity section)
- **Documentation evidence:** [README.md](../../README.md)

## Intent

Expose the Oxidizer retrieval surface as a native Rust MCP server over stdio,
so any MCP client can access the routed canon without knowing anything about
Claude skill formats or having Python installed. The server implements the same
seven tools as the Python CLI with verified result parity.

Non-goals: implementing a full agent or providing a web API.

## Acceptance criteria

1. The MCP server exposes all seven Oxidizer tools (`route`, `search`, `show`,
   `explain`, `api`, `lint`, `manifest`).
2. Tool schemas declare required parameters with JSON Schema.
3. The server produces identical results to the Python CLI for the same queries.
4. The server runs as a stdio process, suitable for any MCP client configuration.
5. No Python runtime dependency — all retrieval logic is native Rust.

## Rationale

The skill format (SKILL.md + domain contracts) is specific to Claude Code. The
MCP server makes the same retrieval surface available to any editor, agent, or
tool that speaks MCP, which is what makes Oxidizer genuinely agent-agnostic
rather than just documenting the intention.

## Alternatives

- **Python-based MCP server wrapping oxidize.py.** Rejected: defeats the goal
  of removing the Python dependency for MCP clients.
- **HTTP/REST API.** Rejected: MCP is the standard for tool integration; HTTP
  would require additional hosting infrastructure.

## Consequences

- Two implementations of the retrieval logic (Python CLI + Rust MCP) must stay
  in sync. The parity tests enforce this.
- The MCP server depends on `rmcp` 2.2 and Rust edition 2024.

## Transition history

- 2026-08-28: created as `realized` during Sprint 0 (Sprint-Loop conversion).
  All acceptance criteria satisfied by existing implementation.
