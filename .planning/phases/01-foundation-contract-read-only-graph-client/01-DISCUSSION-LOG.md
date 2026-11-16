# Phase 1: Foundation, Contract & Read-Only Graph Client - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md. This log preserves the alternatives considered.

**Date:** 2026-11-15
**Phase:** 01-foundation-contract-read-only-graph-client
**Areas discussed:** Sign-off 1 (HTTP stack). CI & task runner, Fact-sheet v1.0 shape, Allow-list ownership and Client-data guard were offered, and the user accepted Claude's recommendations for all of them.

---

## Sign-off 1: HTTP stack

| Option | Description | Selected |
|--------|-------------|----------|
| Approve httpx2 (Recommended) | One HTTP stack shared with openai 3.x, OS trust store by default, no extra test dependency | ✓ |
| Keep httpx + respx | Pin httpx 0.28.1 + respx 0.23.1 for Graph only; second HTTP stack later | |

**User's choice:** Approve httpx2

## Gray-area selection

Offered: CI & task runner, Fact-sheet v1.0 shape, Allow-list ownership, Client-data guard.
**User's response:** "I accept your recommendations". No individual discussion; Claude's recommendations are recorded as D-02..D-13 in CONTEXT.md.

## Claude's Discretion

- CI: GitHub Actions Windows + Ubuntu; stdlib `scripts/check.py` instead of a Makefile
- Fact sheet: full provisional v1.0 shape now, provisional until the Phase 6 freeze
- Allow-list: packaged and locked in code, pinned by a test, not operator-editable
- Client-data guard: scan only the shippable tree with generic rules plus an optional external term list; `.planning/`, `.claude/` and the root drafts are excluded from the scan and the distribution
- Graph client internals, retry implementation, logging, config sources, atomic writer

## Deferred Ideas

- GitHub remote and branch protection
- Private CI job with the external client term list
