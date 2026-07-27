# How Oxidizer adapts the Model Workspace Protocol

Oxidizer's layout follows *Interpretable Context Methodology: Folder Structure
as Agent Architecture* (arXiv:2603.16021), which defines the Model Workspace
Protocol. The fit is close but not exact, and the differences are deliberate.

## What MWP prescribes

A five-layer context hierarchy, loaded selectively rather than all at once:

| Layer | MWP | Purpose |
|---|---|---|
| 0 | `CLAUDE.md` | Workspace identity and routing map |
| 1 | `CONTEXT.md` | Workspace-level routing and shared resources |
| 2 | `stages/NN_name/CONTEXT.md` | Stage contract: Inputs, Process, Outputs |
| 3 | `references/` | Stable material, internalised as constraints |
| 4 | `output/` | Per-run working artifacts |

The paper's central claim is that "one agent, reading the right files at the
right moment, does the work that would otherwise require a multi-agent
framework," and its central metric is tokens loaded per stage: 2,000–8,000
against 40,000+ for a monolithic prompt.

## What Oxidizer changes, and why

**Numbered folders encode routing precedence, not execution order.** MWP's
stages are a pipeline: research → script → production, run in sequence, with
review gates between them. Oxidizer is not a pipeline. A Rust question arrives
and needs *one* domain, chosen situationally — a borrow-checker error does not
"then" become an idiom question. The numbers order the domains from most to
least specific so that `route` has a deterministic tie-break, and the contracts
end with an explicit "Hand off" section instead of an implicit next stage.

**Layer 0 is `SKILL.md`, not `CLAUDE.md`.** The brief calls for an
agent-agnostic skill. `CLAUDE.md` is one vendor's convention; `SKILL.md` with
YAML frontmatter is portable across agent harnesses, and the MCP server exposes
the same tree to clients that read neither.

**Layer 3 is generated, not authored.** In MWP, `references/` holds hand-written
stable material — voice guides, design systems. Oxidizer's Layer 3 is
`corpus/`: ~5,200 documents mirrored from the Rust toolchain, rebuilt whenever
the toolchain moves. It keeps MWP's defining property (stable across runs,
internalised as constraint rather than processed as input) but it is derived
rather than written, and it is far too large to load. Hence the retrieval CLI —
Layer 3 is *queried*, not read. `skills/oxidizer/references/` holds the small
authored material MWP's Layer 3 describes.

**Layer 4 has no folder.** MWP's `output/` exists so a later stage can read what
an earlier one wrote, with a human editing in between. Oxidizer answers a
question in one pass; its Layer 4 is the retrieved slice living in the agent's
context for the duration of the turn, and nothing needs to persist. Adding an
`output/` directory would create files nothing reads.

## Where the paper's metric lands

MWP targets 2,000–8,000 tokens per stage. Oxidizer's budgets:

| Load | Tokens |
|---|---|
| Layer 0 (`SKILL.md`) | ~1,100 |
| Layer 1 (`CONTEXT.md`), when needed | ~900 |
| Layer 2 (one domain contract) | ~700–1,000 |
| Layer 3 (retrieved slice, default budget) | ~2,000 |

A typical answer loads Layer 0, one Layer 2 contract, and one or two retrievals:
roughly 3,000–5,000 tokens against a corpus of ~8 million. That is the paper's
range, and it is the reason the corpus can be this large without being useless.

The retrieval budget is enforced in code rather than by instruction —
`oxidize.py` truncates on a paragraph boundary and reports what it withheld.
Instructing a model to "be brief with context" is unreliable in a way that a
hard cap in the tool is not.
