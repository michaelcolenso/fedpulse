# FedPulse v0.2 — Project Instructions

## Product thesis

FedPulse is an evidence-ranked federal regulatory watchlist for compliance and government-affairs teams. It answers:

> What changed, why is it noteworthy, who may be affected, and which official records support that conclusion?

The product is **monitoring and prioritization, not prediction**. Coherent Federal Register packages and consequential standalone actions are the primary objects. Anomaly scores are supporting evidence only.

## Separate source clocks

Never mix the feeds into one time series:

- **Federal Register:** daily monitoring on `publication_date` for packages, standalone actions, complete-week agency activity, and rulemaking-pipeline context.
- **GPO MARC:** monthly/periodic topic horizon on `cataloged_date`, with explicit catalog-batch concentration and sample warnings.

Every user-facing item must identify its source, cadence, date basis, freshness, confidence, selection rationale, comparison basis, and official-record evidence.

## Deterministic constraints

- Structured metadata and deterministic rules only.
- No generative NLP, embeddings, semantic clustering, full-document reading, or analyst-in-the-loop requirement.
- Agency mapping uses exact/versioned aliases and canonical IDs; preserve raw names.
- Package formation requires exact shared topic or direction-plus-sector coherence. Same-day/same-family count alone is insufficient.
- Package date span is at most three inclusive publication dates.
- Two-record packages require both coherence predicates.
- Package logical IDs are stable; immutable membership/classification versions link through supersession.
- Direction rules use versioned phrases, word boundaries, Unicode normalization, and a three-token negation window.
- Low-confidence packages remain dashboard-visible but never enter the daily brief.
- Federal Register complete weeks are Monday–Friday in `America/New_York`; partial current weeks are not scored.
- Zero-variance baselines never produce synthetic numeric z-score alerts.
- MARC high confidence requires at least 10 records, three cataloging dates, three canonical agencies, and no date contributing more than 50%.

## Lifecycle and notifications

Signals are stateful: `new`, `continuing`, `resolved`, `stale`.

Telegram/digest output includes only new, materially changed, resolved, stale, or critical-health conditions. Unchanged continuing conditions remain visible on the dashboard and are not repeatedly announced. A quiet successful day still reports the daily Federal Register activity ledger.

## Runtime and commands

- Python `>=3.11`; stdlib-only runtime dependencies.
- Use uv for all Python execution.
- SQLite datastore.
- Offline tests; no production DB or network access from tests.
- Dependency-free vanilla JavaScript dashboard served over HTTP.
- All dynamic dashboard interpolation must pass through the single `esc()` helper or safe text-node APIs.

```bash
PYTHONPATH=src uv run python -m unittest discover -s tests -v
PYTHONPATH=src uv run python -m fedpulse.pipeline_v2 --db data/fedpulse.db --out data/outputs --skip-ingest --skip-marc
PYTHONPATH=src uv run python -m fedpulse.backtest --db data/fedpulse.db --out data/outputs/backtest.md
bash -n scripts/nightly.sh
uv run python -m compileall -q src tests
```

## Operational safety

- Development and tests must not mutate `data/fedpulse.db` or production output snapshots.
- Nightly runs use a nonblocking overlap lock and fail loudly on Federal Register/output failures.
- `.github/workflows/nightly.yml` runs the pipeline on GitHub-hosted runners, which are ephemeral. State survives across runs by round-tripping `data/fedpulse.db` through a Cloudflare R2 bucket (`fedpulse-state`) before/after each run — no pipeline code depends on this; it's pure CI plumbing (see README "Running the nightly pipeline on GitHub Actions"). `scripts/nightly.sh` remains the entry point for a self-hosted cron host with a persistent local disk.
- The dashboard is hosted by the `fedpulse-dashboard` Cloudflare Worker (see README "Live dashboard hosting"); `dashboard/` is bundled into the Worker script and the seven JSON outputs are served from a bound KV namespace, which the nightly workflow refreshes after each run. `dashboard/app.js` is unmodified — the Worker mirrors the exact paths it already fetches.
- MARC failures may produce a degraded run only when visible in health output.
- Output JSON uses schema version 2 and atomic file replacement.
- Historical evaluation events, dates, lead requirements, and negative controls are committed before threshold tuning.
- A predictive hit requires at least the pre-registered lead, normally 30 days; post-event topic evidence is not predictive.

## Engineering workflow

- Read current code and design before editing.
- Add focused failing tests before implementation changes.
- Keep changes atomic and avoid unrelated refactors.
- Run narrow tests first, then full offline validation.
- Use feature commits and preserve `Michael Colenso <michael@fedpulse.local>` as Git identity.
- Do not claim live/production success without a fresh real pipeline run and browser verification.
