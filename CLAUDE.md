# Oxidizer

An agent-agnostic Rust skill and MCP server for situational access to the
official Rust documentation canon (~8M tokens), version-pinned to the local
toolchain. See the root `README.md` for user-facing documentation.

## Building the Corpus

The corpus is generated from the local Rust toolchain and is not committed
(gitignored at `/corpus/`). Build it before running tests or the MCP server:

```bash
rustup component add rust-docs
python3 skills/oxidizer/scripts/mirror.py --online
```

`--online` adds two Brown University sources (the interactive Book fork and the
C++-to-Rust phrasebook). Everything else comes from the installed toolchain.
Takes ~30 seconds. Rebuild when the toolchain updates (`oxidize manifest` warns
when stale).

## Building the MCP Server

```bash
cd mcp/oxidizer-mcp && cargo build --release
```

Edition 2024, depends on `rmcp` 2.2. The binary is at
`mcp/oxidizer-mcp/target/release/oxidizer-mcp`.

## Running Tests

```bash
python3 tests/run_tests.py --mcp
```

86 assertions over 5 Rust fixtures. Requires:
- A built corpus (see above)
- The MCP server binary (for `--mcp` parity tests; omit `--mcp` to skip those)

The fixtures are compiled by the actual toolchain, so tests verify that
Oxidizer retrieves the right canon for what the compiler actually says.

## Formatting and Linting

**Rust** (in `mcp/oxidizer-mcp/`):
```bash
cargo fmt
cargo clippy
```

**Python** (project-wide):
```bash
ruff format skills/ tests/
ruff check skills/ tests/
```

## Project Structure

```
skills/oxidizer/          The skill: SKILL.md, CONTEXT.md, domain contracts,
                          scripts (mirror.py, oxidize.py, extract.py),
                          references, evals
mcp/oxidizer-mcp/         Rust MCP server (rmcp): same 7 tools as the CLI,
                          no Python dependency
tests/                    Fixtures (.rs) and assertion harness (run_tests.py)
corpus/                   Generated mirror of the Rust canon (gitignored)
docs/                     Sprint-Loop Project Book: intents, work ledgers,
                          sprint provenance
```

## Sprint-Loop Workflow

This project uses Sprint Loops for development governance. The Project Book
lives in `docs/` with intent chapters (`docs/intents/`), work state
(`docs/work/`), and sprint provenance (`docs/sprints/`). Start new work with
`/sprint-loop start <goal>`. Sprints commit to `dev` and open a PR to `main`.
