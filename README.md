# FedPulse

Real-time regulatory intelligence derived from **federal metadata, not full text**.
No NLP. No human analysts. Pure counts on two free, public-domain feeds:

1. **GPO MARC records** — the Catalog of U.S. Government Publications (~1.1M records).
   Monthly `New / Changed / Deleted` deltas on
   [`usgpo/cataloging-records-CGP-maintenance-files`](https://github.com/usgpo/cataloging-records-CGP-maintenance-files),
   full catalog in
   [`usgpo/cataloging-records-all-cgp-marcxml`](https://github.com/usgpo/cataloging-records-all-cgp-marcxml).
2. **Federal Register API** — same-day rules / proposed rules / notices,
   full history 1994→now, free, no key.

## Indices (the product)

| Index | What it measures | Signal |
|---|---|---|
| **API** — Agency Pulse Index | 4-week rolling z-score of publication volume per agency | agency in "output mode" → enforcement/rulemaking wave |
| **RCR** — Regulatory Churn Ratio | (Proposed + Notices) / Final over rolling 12 months | drafting mode → future compliance costs |
| **TER** — Topic Emergence Radar | new / accelerating LC subject headings | new policy territory before funding/rule announcements |

## Pipeline

```
nightly cron
  ├─ FR API daily pull      → data/fedpulse.db (records table)
  ├─ MARC monthly delta     → data/fedpulse.db (New/Changed/Deleted)
  └─ index recompute        → data/outputs/{api,rcr,ter,summary}.json
```

Backtest (`python -m fedpulse.backtest`) replays the indices against known
regulatory events — that output is the sales deck.

## Commands

```bash
uv venv && uv run python -m unittest discover -s tests -v   # tests (stdlib only)
PYTHONPATH=src uv run python -m fedpulse.ingest fr --days 3                # daily FR pull
PYTHONPATH=src uv run python -m fedpulse.ingest fr --backfill 2021-01-01   # history
PYTHONPATH=src uv run python -m fedpulse.ingest marc --dir data/raw/monthly  # MARC delta
PYTHONPATH=src uv run python -m fedpulse.indices                           # recompute indices
PYTHONPATH=src uv run python -m fedpulse.backtest                          # validation report
```

## Status
- [x] MARCXML + binary MARC21 parsers (stdlib, XXE-guarded) — tested
- [x] FR API client (date-sliced pagination) — shape verified live
- [x] API / RCR / TER index math — tested on synthetic data
- [x] Backtest framework — 8 known events seeded
- [ ] Real-data ingest (needs outbound network on the host)
- [ ] Nightly cron
- [ ] Dashboard (Cloudflare Pages)
