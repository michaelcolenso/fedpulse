# ADR 001: Pursuit briefs scope decision and instruction reconciliation

**Status:** Proposed for pilot — 2026-09-22
**Context:** Fedpulse pivot agent build plan (2026-09-21), Phase 0

## Decision

FedPulse adds a second product lane alongside the existing regulatory
watchlist: **company-specific federal construction pursuit briefs**. The
pilot answers, for one small general contractor at a time:

> Is this notice worth our estimating time, what could rule us out, and what
> must we do next?

The regulatory watchlist, dashboard, and nightly pipeline remain in place and
are not on the new lane's critical path.

## Instruction reconciliation

`AGENTS.md` was written for the regulatory watchlist and forbids full-document
reading, generative NLP, and non-stdlib runtime dependencies. For the pursuit
lane only, those constraints are revised as follows:

1. **Public procurement document parsing is permitted.** Bounded, schema-
   constrained extraction from readable public solicitation documents
   (HTML, plain text, digitally readable PDF) is allowed. OCR, drawings, and
   estimating remain out of scope.
2. **An optional, pinned dependency group is permitted** (e.g. `pypdf`).
   The legacy core — ingestion, ranking, dashboard, nightly pipeline — must
   remain usable with stdlib-only dependencies. Tests that require the
   optional group skip cleanly without it.
3. **Embeddings and vector stores are not introduced** into the pursuit lane.
   The existing semantic/Vectorize infrastructure is untouched.

These watchlist constraints are retained unchanged and apply to the pursuit
lane as well:

- deterministic eligibility decisions by code, not model output
- official evidence and citations for every consequential claim
- separate source clocks; no mixing of feeds into one time series
- offline tests with no production DB or network access
- escaped output via `esc()` / text-node APIs
- operational safety: no production mutation without authorization
- no claims of live/production success without a fresh verified run

Access and permission rules are unchanged: no deploying, merging, sending
email, enabling schedules, or purchasing without separate authorization.

## New truth rules introduced by the pursuit lane

- Public source facts, extracted requirements, customer assertions, and
  derived fit decisions are separate record types and never blended.
- Missing values are `null` or a named status, never zero/false by default.
- Customer capability attestations are not government verification and never
  enter public snapshots or shared extraction prompts.
- Analyst review is a one-time pilot launch gate on held-out critical facts,
  not a per-item ongoing service requirement.

## Consequences

- A separate `pursuit.db` SQLite database, private R2 prefix, and isolated
  workflow keep pilot state away from the legacy pipeline.
- `AGENTS.md` requires a corresponding text update when the build is
  assigned for execution (Phase 1), so the instructions and this ADR agree.
