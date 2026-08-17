# FedPulse

> **Federal activity is public. Knowing what matters is not.**

FedPulse turns scattered federal records into an evidence-backed intelligence feed.

It watches official sources across regulation, legislation, grants, procurement, and spending, then helps answer:

- What changed?
- What can I act on now?
- What is forming early?
- Where is federal money moving?
- Why is this relevant?
- What official evidence supports it?

```text
see what changed → understand why it matters → inspect the evidence → act
```

FedPulse is not a generic search engine, an AI summary feed, or a black-box prediction system. It is a government-action intelligence layer built to reduce noise and preserve evidence.

## What you get

### Today
A short brief of the federal developments most worth attention.

### Act Now
Open contracts and grants where action can still affect the outcome.

Examples:
- SAM solicitations
- Sources Sought
- presolicitations
- Grants.gov forecasts and open opportunities
- set-asides
- opportunities with useful response runway

### Market Intelligence
Signals showing where government demand and spending are moving.

### Policy Signals
Legislative, regulatory, OIRA, and Federal Register activity that may change a market, funding environment, or compliance landscape.

### Hidden Gems
Unusually relevant opportunities that are easy to miss because of obscure titles, early-stage notices, narrow fit, limited competition, or unusual buying patterns.

### Evidence Explorer
The source records, identifiers, timestamps, scoring reasons, and official links behind every surfaced item.

## Sources

FedPulse treats each federal source as a separate sensor with its own meaning and timing.

| Source | What it tells you |
|---|---|
| Federal Register | Formal regulatory actions and notices |
| RegInfo / OIRA | Unified Agenda, review activity, stakeholder meetings |
| Grants.gov | Forecast and open funding opportunities |
| SAM.gov | Contract opportunities and procurement stages |
| USAspending | Where federal money actually went |
| GovInfo / Congressional Bill Status | Legislative activity and official publications |
| GPO catalog / MARC | Broader federal publication trends |

Core operation uses public machine-readable data and does not require source API keys.

## How FedPulse models government action

FedPulse keeps source records intact and connects them only when the evidence supports it.

### Events
One observed action from one official source, such as:

```text
OIRA review
Federal Register rule
SAM solicitation
Grants.gov opportunity
USAspending award
bill update
```

### Identifiers
Typed identifiers such as:

```text
RIN
Federal Register document number
bill / public law
grant opportunity number
SAM notice ID
solicitation number
award ID
NAICS
```

A shared RIN can support a strong lifecycle link. A shared NAICS code cannot.

### Edges
Relationships are created only when the evidence is strong enough.

That supports timelines such as:

```text
Congress
  ↓
Unified Agenda
  ↓
OIRA
  ↓
Federal Register
  ↓
Grants / procurement
  ↓
Awards / spending
```

Missing stages are not invented.

## Ranking

FedPulse does not rank by keyword match or dollar size alone.

Signals can include:

- freshness
- first-seen novelty
- topic fit
- geography
- NAICS
- agency
- specificity
- value
- deadline urgency
- response runway
- early-stage advantage
- competition / set-aside signals
- actionability

The strongest results usually have several independent facts pointing in the same direction.

## Semantic retrieval and AI

Rules are good at facts. They are weaker at language.

FedPulse can use semantic retrieval to find related opportunities even when wording differs:

```text
canonical event text
      ↓
Workers AI embeddings
      ↓
Vectorize
      ↓
deterministic evidence filters
```

Embeddings help find candidates. They do not establish facts.

Structured source data still decides things like:

- place of performance
- agency
- NAICS
- amount
- deadline
- RIN
- solicitation number
- lifecycle state

An optional LLM analyst can help judge relevance, commercial fit, actionability, and Hidden Gem potential. A second skeptic pass can challenge those judgments.

> **AI may interpret evidence. It may not invent government facts.**

Unsupported claims are rejected, model influence is bounded, and deterministic ranking remains the fallback.

## Watch profiles

Watch profiles define what matters for a market or user.

Current profiles include:

- Construction / AEC / Washington
- AI / Technology
- Business Opportunities
- Seattle / Pacific Northwest Intelligence

Profiles can include topics, geographies, agencies, NAICS families, value thresholds, freshness windows, and deadline windows.

They are meant to describe useful government activity, not just saved keywords.

## Trust model

FedPulse separates fact from analysis.

```text
Fact: Place of performance: Tacoma, WA
Analysis: Strong fit for a regional roofing contractor
```

It also separates identity from similarity. Similar records are not automatically treated as the same action.

Source semantics are preserved. A Washington contracting-office address is not the same as work being performed in Washington.

Quiet output is valid. FedPulse does not invent alerts when the evidence is weak.

## Architecture

```text
Official federal sources
        ↓
Source-specific ingestion
        ↓
Normalization + provenance
        ↓
SQLite government-event graph
        ↓
Eligibility + deterministic ranking
        ↓
Semantic retrieval / optional AI
        ↓
Evidence validation
        ↓
Generation-scoped JSON
        ↓
Cloudflare KV + Worker dashboard
```

Core stack:

- Python 3.11+
- standard-library Python runtime
- SQLite
- vanilla HTML/CSS/JavaScript
- Cloudflare Workers, KV, R2, Workers AI, Vectorize
- GitHub Actions for production automation

Published output is generation-scoped and switched atomically so the dashboard never mixes files from different runs.

## Incremental embeddings

FedPulse does not re-embed the same corpus every night.

Each eligible opportunity gets a SHA-256 fingerprint of:

```text
embedding model + canonical event text
```

Unchanged records are skipped. New or changed records are embedded and upserted into Vectorize.

The fingerprint is committed only after the Vectorize write succeeds, so failed updates retry automatically.

Nightly maintenance scans the full eligible corpus while limiting how many changed vectors are processed in one run.

## Quick start

Requirements:

- Python 3.11+
- `uv` recommended

```bash
git clone https://github.com/michaelcolenso/fedpulse.git
cd fedpulse

PYTHONPATH=src uv run python -m unittest discover -s tests -v
```

Run the pipeline:

```bash
PYTHONPATH=src uv run python -m fedpulse.pipeline_v2 \
  --db data/fedpulse.db \
  --out data/outputs
```

Run against an existing database without ingesting new source data:

```bash
PYTHONPATH=src uv run python -m fedpulse.pipeline_v2 \
  --db data/fedpulse.db \
  --out data/outputs \
  --skip-ingest \
  --skip-marc
```

## Repository map

```text
src/fedpulse/       ingestion, graph, ranking, semantic logic
dashboard/          product UI
worker/             Cloudflare Worker
scripts/            validation and publishing utilities
tests/              offline test suite
docs/               deeper technical documentation
.github/workflows/  CI and production automation
```

Useful docs:

- `docs/government-action-graph.md`
- `docs/semantic-maintenance.md`

## Who it is for

FedPulse is useful to people whose decisions depend on federal action:

- contractors and subcontractors
- AEC firms
- manufacturers and suppliers
- grant-seeking organizations
- business-development teams
- consultants
- government-affairs and compliance teams
- researchers, journalists, and strategists

The core promise is simple:

> **Find consequential federal activity early, explain why it matters, and show the evidence.**

## What it is not

FedPulse is not:

- the official record
- legal or compliance advice
- a feed of every federal document
- an AI wrapper around government data
- a system that assumes similarity means identity
- a black-box prediction engine
- a guarantee that an opportunity is commercially suitable

Official sources remain authoritative. FedPulse helps you find the right ones faster and understand their context.
