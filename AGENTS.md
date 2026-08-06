# FedPulse — Regulatory Intelligence from Federal Metadata

## What this is
FedPulse derives proprietary regulatory signal from two free, public-domain feeds:

1. **GPO MARC records** — the Catalog of U.S. Government Publications (~1.1M records).
   - Full catalog: `usgpo/cataloging-records-all-cgp-marcxml` (28 zips × ~40k records, 357MB)
   - Monthly delta: `usgpo/cataloging-records-CGP-maintenance-files/CGP_Records_Monthly_Files/`
     (`New_MARC_Records`, `Changed_MARC_Records`, `Deleted_Records_Lists`, plus Online/Tangible splits)
   - Formats: MARCXML, UTF-8 (.mrc), MARC-8
2. **Federal Register API** (`https://www.federalregister.gov/api/v1`) — same-day rules,
   proposed rules, notices, presidential documents. Full history 1994→now. Free, no key.

## The three indices
- **API — Agency Pulse Index**: 4-week rolling z-score of publication volume per agency.
  Spike = agency shifted into output mode.
- **RCR — Regulatory Churn Ratio**: (Proposed Rules + Notices) / (Final Rules) over rolling
  12-month windows per agency / SuDoc class. High ratio = drafting mode, future compliance
  costs being baked in.
- **TER — Topic Emergence Radar**: new or accelerating Library of Congress subject headings
  (650 field). New heading string = new policy territory.

## Commands (all via `uv run`)
- `PYTHONPATH=src uv run python -m fedpulse.ingest` — pull FR daily + MARC delta, upsert into SQLite
- `PYTHONPATH=src uv run python -m fedpulse.indices` — recompute API / RCR / TER snapshots → data/outputs/
- `PYTHONPATH=src uv run python -m fedpulse.backtest` — validate indices against known past events
- `uv run pytest` — tests

## Stack
Python 3.11 (uv, stdlib-only — sqlite3, xml.etree, urllib), SQLite at `data/fedpulse.db`,
index snapshots as JSON in `data/outputs/`. No paid deps, no NLP.

## Data provenance
- MARC: public domain (U.S. government works). GPO repos linked from
  https://github.com/usgpo/cataloging-records README.
- FR API: public data, terms at https://www.federalregister.gov/developers — attribution
  required in redistribution.
