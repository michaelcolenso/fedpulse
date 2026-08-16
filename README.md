# FedPulse

FedPulse is an evidence-ranked federal regulatory monitoring system built from Federal Register and GPO metadata. It is deterministic, stdlib-only at runtime, and designed around auditable evidence rather than generated summaries.

## v0.3 production-trust release

This release hardens the production boundary around the existing v0.2 evidence engine:

- R2 state restore fails closed instead of treating every error as an empty bootstrap.
- SQLite state is validated before it can replace persisted production state.
- State backups are retained before replacement.
- Dashboard data is published into immutable generation-scoped KV objects.
- A single `current.json` pointer is written last, so readers get one coherent generation.
- The Worker and Wrangler configuration live in the repo.
- CI validates tests, Python compilation, JSON config, dashboard JavaScript, Worker JavaScript, and shell syntax.
- The dashboard is organized around decision-ready evidence signals instead of raw classifier diagnostics.

## Dashboard

The dashboard is dependency-free vanilla JavaScript. It fetches schema-v2 output through the Cloudflare Worker, verifies generation consistency across all payloads, and shows:

1. signals worth watching;
2. today's Federal Register pulse;
3. agencies outside baseline;
4. coordinated evidence packages;
5. standalone watchlist hits;
6. emerging GPO topics;
7. methodology and diagnostic metrics.

## Local validation

```bash
PYTHONPATH=src uv run python -m unittest discover -s tests -v
uv run python -m compileall -q src tests
python -m json.tool src/fedpulse/config/agency_aliases.json >/dev/null
node --check dashboard/app.js
node --check worker/src/index.js
bash -n scripts/nightly.sh
```

## Nightly operation

`.github/workflows/nightly.yml` runs the pipeline, restores state from Cloudflare R2, validates state before replacement, persists a rollback copy, publishes immutable dashboard generations to KV, and then advances `current.json`.

## Cloudflare Worker

The Worker is configured by `wrangler.jsonc` and serves static dashboard assets plus generation-scoped JSON outputs from the `DASHBOARD_DATA` KV binding.

Deploy with:

```bash
npx wrangler deploy
```

## v0.4 direction

The next product stage is Regulations.gov docket lifecycle enrichment. See:

```text
docs/superpowers/specs/2026-08-16-fedpulse-v0.4-regulationsgov-lifecycle.md
```

The v0.4 goal is to turn Federal Register records and packages into docket-centered lifecycle signals: proposal open, comment window closed, agency review activity, final rule published, implementation follow-up, or withdrawal/termination.
