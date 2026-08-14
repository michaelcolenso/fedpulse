# FedPulse v0.2

FedPulse is an evidence-first regulatory monitoring and prioritization pipeline built from public metadata. It does **not** read or summarize regulatory full text and it is not a prediction engine.

## Inputs and clocks

- **Federal Register API:** same-day rules, proposed rules, notices, and presidential documents. The daily activity output uses `publication_date` and complete Monday–Friday weekly windows; per-agency activity, sustained level shifts, and proposal/final context are separate supporting metrics.
- **GPO MARC maintenance files:** monthly catalog deltas. The topic horizon uses `cataloged_date`, explicitly reports batch concentration, and never treats MARC rows as FR activity.
- **Source health:** attempts/success, visible degraded/stale state, FR `last_publication_date`, MARC `last_cataloged_date`, and `maintenance_applied_at`.

The nightly pipeline is additive and idempotent. Agency normalization carries a taxonomy mapping-version marker, so unchanged and explicitly unmapped records are not rewritten on every run. Mapping changes can deterministically reprocess records.

## Product outputs

`data/outputs/` contains seven schema-v2 JSON snapshots:

- `daily_activity.json` — daily FR totals and document-type/agency counts.
- `packages.json` — bounded, coherent FR packages with deterministic IDs, immutable membership versions, confidence, lifecycle, taxonomy versions, and official-record evidence.
- `standalone.json` — exact watchlist matches with record evidence and taxonomy provenance.
- `fr_metrics.json` — per-agency complete-week FR activity and level shifts plus supporting pipeline context.
- `marc_horizon.json` — MARC-only topic horizon with cataloged-date evidence and batch-risk confidence.
- `health.json` — source freshness contract.
- `brief.json` — evidence-first brief; low-confidence items remain dashboard-visible but are excluded from notification/brief prioritization.

Package coordination uses an exact child agency for single-child packages and a known parent plus participating children for coherent sibling packages. Unknown or unrelated siblings cannot earn confidence from count alone. Lifecycle state is persisted: new/material changes and stale/resolved transitions may notify; unchanged continuing signals do not notify merely because 48 hours elapsed.

## Commands

```bash
# Offline test suite
PYTHONPATH=src uv run python -m unittest discover -s tests -v

# Schema-v2 pipeline (use --skip-* for offline runs)
PYTHONPATH=src uv run python -m fedpulse.pipeline_v2 --db data/fedpulse.db --out data/outputs --skip-ingest --skip-marc

# FR/MARC ingestion and v2 output generation (network-dependent; not used by tests)
PYTHONPATH=src uv run python -m fedpulse.pipeline_v2 --db data/fedpulse.db --out data/outputs

# Honest pre-registered evaluation; separate predictive/horizon reporting
PYTHONPATH=src uv run python -m fedpulse.backtest --db data/fedpulse.db --out data/outputs/backtest.md

# Serve the dashboard over HTTP (fetch is not supported from file://)
uv run python -m http.server 8000 --directory .
# open http://localhost:8000/dashboard/
```

`run_pipeline(..., now=...)` is injectable for offline tests; when `as_of` is omitted it uses the `America/New_York` calendar date, not UTC. A custom `--db` is passed through to MARC sync; production data is never touched by temporary-DB tests.

## Honest evaluation

`src/fedpulse/config/evaluation_events.json` is the pre-registration ledger. Predictive checks scan only preceding windows and require the registered lead (at least 30 days for predictive events); TER evidence after an event is rejected. Precision, recall, false-positive rate, lead times, and median lead are reported for predictive events. MARC/TER horizon emergence is reported separately and is not counted as a predictive hit. No live or production evaluation is claimed by the offline test suite.

## Provenance and boundaries

FR API documentation: https://www.federalregister.gov/developers. MARC files are public-domain government catalog metadata from the GPO repositories. Taxonomy files are versioned in `src/fedpulse/config/`. Full-text interpretation, legal conclusions, outbound Telegram delivery, production ingestion, and deployment remain outside this offline-validated branch.
