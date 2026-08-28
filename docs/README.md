# Oxidizer — Project Book

Oxidizer is an agent-agnostic Rust skill that mirrors the official Rust
documentation canon locally (~8M tokens, ~5,200 documents) and serves it back
in small, routed, citable slices with enforced token budgets.

The project provides two interfaces: a Python CLI (`oxidize.py`) for use as a
Claude Code skill, and a native Rust MCP server (`oxidizer-mcp`) for any MCP
client. Both produce identical results — the MCP server has no Python
dependency.

This directory is the canonical Sprint Loops Book: project intent, executable
work, realization evidence, and sprint provenance live here together.

See the root [README.md](../README.md) for usage, architecture, and quick
start.
