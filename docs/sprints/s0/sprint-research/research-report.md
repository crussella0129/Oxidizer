# Sprint 0 Research Report

## Sprint Goal

Convert the Oxidizer project to Sprint-Loop governance. The project is a
functionally complete Rust skill and MCP server for situational access to the
official Rust canon (~8M tokens, version-pinned). This sprint establishes the
Book, intent chapters, and work ledgers so that ongoing development follows
the sprint-loop workflow rather than ad-hoc commits.

## Existing Code Survey

**15 project files reviewed.**

### Skill layer (`skills/oxidizer/`)
- `SKILL.md` (Layer 0): routing map + retrieval budget discipline. ~1,100 tok.
- `CONTEXT.md` (Layer 1): corpus map — which source is authoritative for which
  claim, with explicit precedence ordering.
- `domains/01-08` (Layer 2): eight domain contracts covering diagnose, learn,
  api, spec, unsafe, idiom, migrate, and implement.
- `scripts/mirror.py`: stdlib-only Python that mirrors the Rust toolchain docs
  plus two Brown University sources into `corpus/`.
- `scripts/oxidize.py`: retrieval CLI — route, diagnose, explain, api, lint,
  search, show, disk, manifest.
- `scripts/extract.py`: HTML/Rust-source-to-markdown extraction.
- `references/corpus.md`, `disk-hygiene.md`, `mwp-adaptation.md`: operational
  references.
- `evals/evals.json`: seven eval prompts with expectations.

### MCP server (`mcp/oxidizer-mcp/`)
- Rust crate using `rmcp` 2.2, edition 2024.
- Seven tools: `oxidizer_route`, `oxidizer_search`, `oxidizer_show`,
  `oxidizer_explain`, `oxidizer_api`, `oxidizer_lint`, `oxidizer_manifest`.
- `corpus.rs`: IDF-weighted search, API path resolution, lint lookup,
  section splitting, token budgeting — all native Rust, no Python dependency.
- Produces identical results to the Python CLI (verified by parity tests).

### Tests (`tests/`)
- `run_tests.py`: 86 assertions over 5 Rust fixtures.
- Fixtures: `borrow_conflict.rs`, `move_after_use.rs`, `missing_lifetime.rs`,
  `unidiomatic.rs`, `unsafe_ffi.rs`.
- Covers: error-code extraction, clippy detection, API resolution, lint lookup,
  search ranking, token budget enforcement, disk hygiene reporting, MCP/CLI
  parity.

### Infrastructure
- `.gitignore` properly excludes `corpus/` (generated, ~250MB) and `target/`.
- `LICENSE` present.
- `README.md`: comprehensive project documentation.

### Assessment

The project is functionally complete for its stated purpose. All major
capabilities — corpus mirroring, domain routing, budgeted retrieval, MCP server,
test harness — are implemented, tested, and documented. The code quality is high
with clear separation of concerns across the MWP layers.

What is missing is a governance structure for ongoing development. Commits have
been ad-hoc, there are no durable intent declarations, and there is no work
tracking or sprint provenance. This is exactly what the Sprint-Loop conversion
provides.

## External Sources

None required. This sprint is about project governance, not new technical
capabilities. The Sprint-Loop skill itself provides the schema and tooling.

## Risks / Unknowns / Dependencies

1. **Book structure vs. existing documentation.** The project already has a
   well-structured README.md. The Book's `docs/README.md` should complement,
   not duplicate, the root README. Risk: low.

2. **Existing branch topology.** The project has only `main`. Sprint-Loop
   substrate has created a `dev` branch. No existing workflow to disrupt.
   Risk: none.

3. **No CLAUDE.md in the project.** There is a global CLAUDE.md but no
   project-specific one. The Sprint-Loop workflow does not require one, but
   future sprints may benefit from project-specific instructions.
   Risk: none.

## Recommended Approach

1. Create intent chapters capturing the project's two realized capabilities
   (routed Rust canon skill + agent-agnostic MCP server) and one proposed intent
   for the governance conversion itself.
2. Write the Book README with project identity.
3. Proceed through plan, build (minimal — governance artifacts only, no code
   changes), and test phases to complete Sprint 0.
4. The build phase writes no production code — it formalizes the existing state
   into Book artifacts with proper evidence links.

## Intents Reviewed

- [INT-0001 — Routed Rust Canon](../../intents/INT-0001-routed-rust-canon.md):
  created as `realized`. The foundational project capability — mirroring the
  ~8M-token Rust documentation canon locally and routing into it with budgeted
  retrieval. Already fully implemented with CLI, domain contracts, test suite,
  and documentation.

- [INT-0002 — Agent-Agnostic MCP Server](../../intents/INT-0002-agent-agnostic-mcp-server.md):
  created as `realized`. The rmcp-based MCP server that exposes the retrieval
  surface to any MCP client, with verified CLI/MCP parity.

- [INT-0003 — Sprint-Loop Governance](../../intents/INT-0003-sprint-loop-governance.md):
  created as `proposed`. Establishes the Sprint-Loop workflow for ongoing
  development. This is what Sprint 0 advances.

## Referenced Artifacts

- `skills/oxidizer/SKILL.md` — Layer 0 identity
- `skills/oxidizer/CONTEXT.md` — Layer 1 corpus map
- `mcp/oxidizer-mcp/src/main.rs` — MCP server (7 tools)
- `mcp/oxidizer-mcp/src/corpus.rs` — search/retrieval engine
- `tests/run_tests.py` — 86-assertion test suite
- `skills/oxidizer/evals/evals.json` — eval expectations
- `README.md` — project documentation
