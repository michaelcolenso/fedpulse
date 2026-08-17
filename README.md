# FedPulse

> **Federal activity is public. Understanding what matters, what changed, and what to do about it is not.**

FedPulse turns the federal government's scattered public records into an evidence-backed intelligence feed for people who need to know **what is forming, what just opened, where money is moving, and which policy changes may matter next**.

Instead of making you search the Federal Register, SAM.gov, Grants.gov, USAspending, RegInfo, GovInfo, and congressional data separately, FedPulse watches those systems together, preserves the official evidence, connects records when the identifiers support it, and ranks the developments most likely to deserve attention.

It is built around one simple workflow:

```text
see what changed → understand why it matters → inspect the evidence → decide whether to act
```

FedPulse is not a generic government search engine, an AI news summarizer, or a black-box prediction system. It is a **government-action intelligence layer**: source-backed, explainable, and designed to surface signal before it disappears into the volume of federal publishing.

---

## What FedPulse helps you see

The federal government leaves traces before, during, and after consequential action.

A rule may appear in the Unified Agenda before it reaches OIRA. An OIRA review can attract stakeholder meetings before a Federal Register publication. A grant can move from forecast to open opportunity. A procurement can appear as Sources Sought or presolicitation before a formal solicitation. USAspending then shows where federal dollars actually landed.

FedPulse puts those traces into one system.

It is designed to answer questions such as:

- **What can I act on right now?** Which contracts and grants are open, relevant, realistically actionable, and approaching a meaningful deadline?
- **What is appearing early?** Which forecasts, Sources Sought notices, presolicitations, OIRA reviews, or stakeholder meetings deserve attention before the obvious public milestone?
- **Where is government demand moving?** Which agencies, categories, geographies, and markets are seeing new opportunities or award activity?
- **What changed in policy?** Which legislative and regulatory actions are advancing, and what official records support that conclusion?
- **What looks unusually interesting?** Which opportunities combine strong fit, early timing, specificity, limited competition, or unusual buying patterns?
- **What happened after the opportunity?** Where possible, can a solicitation, grant program, rulemaking, or bill be followed into later stages such as awards or implementation?
- **Why is this item on my screen?** What facts, identifiers, timing, and scoring components caused FedPulse to surface it?

The goal is not more federal data. The goal is **decision compression**.

---

## The product surfaces

### Today

A compact executive brief of federal developments worth attention.

This is the front door: the smallest useful set of signals from a much larger evidence corpus.

### Act Now

Open contracts and funding opportunities where a near-term action can still change the outcome.

Examples include:

- SAM.gov solicitations
- Sources Sought notices
- presolicitations
- Grants.gov forecasts and open opportunities
- set-aside opportunities
- geographically relevant procurements
- opportunities with useful response runway

### Market Intelligence

Evidence that federal demand, spending, or buying behavior is moving.

This includes award activity, agency/category movement, and other signals that matter even when there is nothing to bid on today.

### Policy Signals

Upstream government activity that may reshape a market, compliance obligation, funding environment, or procurement landscape.

Examples include:

- congressional activity
- Unified Agenda actions
- OIRA review activity
- EO 12866 stakeholder meetings
- Federal Register actions

### Hidden Gems

A deliberately selective view for opportunities that are not merely relevant, but **unusually easy to overlook**.

FedPulse looks for combinations such as:

- early procurement stage + strong profile fit
- rare agency × NAICS combinations
- first-seen agency × geography × category combinations
- restricted or limited competition
- unusually specific local fit
- recent acceleration in agency buying activity
- obscure titles whose underlying description reveals a much better opportunity than the headline suggests

A Hidden Gem must still survive hard evidence checks. “Interesting” is not allowed to substitute for “true.”

### Evidence Explorer

The audit trail behind the intelligence.

FedPulse preserves source records, identifiers, lifecycle stages, scoring reasons, timestamps, and official links so a recommendation can be inspected rather than trusted blindly.

---

## One government, many source systems

FedPulse treats each source as a different sensor. It does **not** pretend they all mean the same thing or run on the same clock.

| Source | What it contributes | Why it matters |
|---|---|---|
| **Federal Register** | Proposed/final rules, notices, agency actions | The formal public record of regulatory action |
| **RegInfo / OIRA** | Unified Agenda, OIRA reviews, EO 12866 meetings | Earlier visibility into regulatory formation and stakeholder activity |
| **Grants.gov** | Forecast and posted funding opportunities | What agencies are preparing to fund and what is open now |
| **SAM.gov** | Contract opportunities, Sources Sought, presolicitations, solicitations | What the government is preparing to buy |
| **USAspending** | Award and transaction activity | Where federal money actually went |
| **GovInfo / GPO** | Congressional and government publication data | Official legislative and documentary context |
| **Congressional Bill Status** | Bill lifecycle and latest actions | Policy formation before agency implementation |
| **GPO catalog / MARC** | Broader publication horizon signals | Topic and publication activity outside the daily action feeds |

The baseline source architecture is intentionally built around public, machine-readable federal data and does not require source API keys for core operation.

---

## From documents to government actions

FedPulse does not flatten every source into one giant ambiguous table.

The core model is an evidence graph built from three primitives.

### Events

An event is one observed action from one official source:

```text
OIRA review
Federal Register publication
SAM solicitation
Grants.gov opportunity
USAspending award
congressional bill update
...
```

Each event keeps its original source-specific payload and provenance.

### Identifiers

FedPulse extracts typed identifiers such as:

```text
RIN
Federal Register document number
bill / public law
Grants opportunity number
SAM notice ID
solicitation number
award ID
NAICS
Assistance Listing
```

Those identifiers are not treated as interchangeable.

A shared **RIN** can support a strong regulatory lifecycle link. A shared **NAICS code** only means two records occupy the same classification; it does not prove they describe the same action.

### Edges

FedPulse creates relationships only when the evidence supports them.

That enables timelines such as:

```text
Congress
   ↓
Unified Agenda
   ↓
OIRA review
   ↓
OIRA stakeholder meetings
   ↓
Federal Register
   ↓
Grants / procurement
   ↓
Awards / spending
```

Not every action will contain every stage. FedPulse shows observed evidence; it does not invent missing steps to make a prettier story.

---

## Ranking without a mystery score

Federal data has a volume problem. A useful system has to rank aggressively without becoming opaque.

FedPulse therefore decomposes opportunity ranking into auditable components rather than producing one unexplained relevance number.

Signals can include:

- **freshness** — how recent is the official action?
- **novelty** — how recently did FedPulse first observe it?
- **topic relevance** — does the work match the watch profile?
- **geographic relevance** — is the authoritative place of performance relevant?
- **NAICS relevance** — does the procurement classification fit?
- **agency relevance** — is the buying/funding agency important to the profile?
- **specificity** — do several independent dimensions agree?
- **magnitude** — is the opportunity economically meaningful?
- **urgency** — is the response window closing?
- **response runway** — is there still useful time to investigate?
- **early-stage advantage** — forecast, Sources Sought, presolicitation, special notice, stakeholder meeting, etc.
- **competitive shape** — small-business, HUBZone, 8(a), SDVOSB, WOSB, sole-source, or other competition signals
- **actionability** — can someone do something with this information now?

A high-dollar opportunity does not automatically win. An upstream notice does not automatically win. A keyword hit does not automatically win.

The strongest items are usually the ones where **multiple independent facts agree**.

---

## Semantic retrieval and AI: useful, constrained, optional

Rules are excellent at facts. They are weaker at language.

“Roof replacement,” “building envelope remediation,” and “facilities sustainment” can describe overlapping commercial work without sharing obvious keywords. FedPulse therefore supports a semantic retrieval layer using canonical, source-aware text representations.

In the Cloudflare deployment:

```text
canonical event text
      ↓
Workers AI embeddings
      ↓
Vectorize semantic retrieval
      ↓
deterministic evidence filters + scoring
```

Embeddings help **find** candidates. They do not establish facts.

Structured evidence still decides things such as:

- place of performance
- agency
- NAICS
- amount
- deadline
- RIN
- solicitation number
- lifecycle state

FedPulse also supports an optional generative analyst/reranker behind a feature flag. When enabled, the model receives a sealed evidence packet and can help judge semantic fit, commercial relevance, actionability, and Hidden Gem potential. A separate skeptic pass can challenge those judgments.

The important boundary is absolute:

> **AI may interpret evidence. It may not manufacture government facts.**

Unsupported evidence references are rejected, model influence is bounded, and deterministic rankings remain the fallback.

---

## Watch profiles

A watch profile describes what “relevant” means for a particular user or market.

Current profiles include:

- **Construction / AEC / Washington**
- **AI / Technology**
- **Business Opportunities**
- **Seattle / Pacific Northwest Intelligence**

Profiles can express:

```text
topics / capabilities
geographies
agencies
NAICS families
minimum useful value
high-value thresholds
freshness windows
deadline windows
```

The result is intentionally different from a saved keyword search. A profile is a compact statement of **what kind of government action would actually matter**.

---

## Evidence first

FedPulse is opinionated about trust.

### Facts and analysis are different things

A source field such as:

```text
Place of performance: Tacoma, WA
```

is evidence.

A conclusion such as:

```text
Strong fit for a regional roofing contractor
```

is analysis.

FedPulse keeps that distinction visible.

### Identity and similarity are different things

Two records that look similar are not automatically the same government action.

Exact identifiers can create strong links. Shared classifications, text similarity, embeddings, or model judgments can suggest related context, but they do not silently create identity.

### Source semantics are preserved

“Washington” in a contracting-office address is not the same as a Washington place of performance. An award date is not a solicitation deadline. A recipient location is not necessarily a work location.

The system is designed around those distinctions because small semantic errors become large ranking errors at federal-data scale.

### Quiet is allowed

FedPulse does not need to invent an alert every day.

If the evidence is weak or nothing changed materially, a quiet result is valid output.

---

## Architecture

The core system is intentionally small and inspectable.

```text
Official federal sources
        │
        ▼
Source-specific ingestion
        │
        ▼
Normalization + provenance
        │
        ▼
SQLite government-event graph
        │
        ├── exact identifier linking
        ├── lifecycle state
        ├── historical context
        └── embedding fingerprints
        │
        ▼
Eligibility + deterministic ranking
        │
        ├── semantic retrieval (optional enhancement)
        ├── LLM analyst / skeptic (optional enhancement)
        └── evidence validation
        │
        ▼
Generation-scoped JSON snapshot
        │
        ▼
Cloudflare KV + Worker dashboard
```

### Core runtime

- Python 3.11+
- Python standard library only for the core runtime
- SQLite
- dependency-free HTML/CSS/JavaScript dashboard

### Cloudflare deployment

- Workers Static Assets for the dashboard
- KV for published generations
- R2 for durable SQLite pipeline state
- Workers AI for semantic embeddings
- Vectorize for semantic retrieval

### Automation

GitHub Actions runs the production pipeline, restores state from R2, ingests current sources, validates the resulting database, incrementally maintains embeddings, persists validated state, and atomically publishes the dashboard snapshot.

---

## Atomic publishing

A monitoring system should never show half of one run mixed with half of another.

FedPulse publishes immutable generation-scoped output and swaps a single current-generation pointer only after a complete snapshot exists.

That means readers see one coherent view of the system rather than a collection of JSON files updated at different moments.

---

## Incremental semantic maintenance

The semantic index is maintained by content, not by blindly re-embedding the same corpus every night.

For every eligible opportunity, FedPulse computes a SHA-256 fingerprint of:

```text
embedding model identity + canonical source-aware text
```

If the fingerprint has not changed, the record is skipped.

If the record is new or materially changed, it is embedded and upserted into Vectorize. The new fingerprint is committed to SQLite **only after the Vectorize write succeeds**, so failed uploads remain eligible for retry.

The nightly job scans the full eligible opportunity corpus while using a configurable update budget to control throughput during large backfills.

Coverage and throughput are therefore separate concepts:

```text
full corpus coverage
      ≠
embed everything on every run
```

---

## Quick start

### Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) recommended

Clone the repository and run the test suite:

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

For an offline/local output pass against an existing database:

```bash
PYTHONPATH=src uv run python -m fedpulse.pipeline_v2 \
  --db data/fedpulse.db \
  --out data/outputs \
  --skip-ingest \
  --skip-marc
```

Compile-check the Python source:

```bash
uv run python -m compileall -q src tests scripts
```

The production Cloudflare/GitHub Actions path requires the relevant R2, KV, Workers AI, Vectorize, and Cloudflare credentials. Those services are deployment infrastructure; they are not required to understand or test the core evidence/ranking logic locally.

---

## Repository map

```text
src/fedpulse/            core ingestion, graph, ranking, evidence, semantic logic
dashboard/               dependency-free product UI
worker/                  Cloudflare Worker entrypoint
scripts/                 validation, publishing, semantic maintenance utilities
tests/                   offline deterministic test suite
docs/                    deeper technical/product documentation
.github/workflows/       CI, nightly production pipeline, Cloudflare automation
wrangler.jsonc           Cloudflare Worker/KV/AI/Vectorize bindings
```

Useful deeper reads:

- [`docs/government-action-graph.md`](docs/government-action-graph.md) — event, identifier, edge, and lifecycle semantics
- [`docs/commercial-product-strategy.md`](docs/commercial-product-strategy.md) — product use cases and market framing
- [`docs/semantic-maintenance.md`](docs/semantic-maintenance.md) — full-corpus incremental embedding behavior

---

## What FedPulse is for

FedPulse is most useful to people whose decisions are affected by federal action but who do not want to spend their day operating federal search portals.

That includes:

- federal contractors and subcontractors
- AEC and construction firms
- manufacturers and suppliers
- grant-seeking organizations
- business-development teams
- consultants
- government-affairs and compliance teams
- market researchers
- journalists and public-data researchers
- investors and strategists studying government-driven demand

Different users care about different signals. The underlying principle remains the same:

> **Find the consequential government action early, show exactly why it matters, and make the evidence easy to inspect.**

---

## What FedPulse is not

FedPulse is deliberately **not**:

- a replacement for the official record
- a legal or compliance opinion
- a generic full-text government search engine
- a feed of every federal document
- an “AI summary” wrapper around public data
- a system that assumes similarity means identity
- a black-box prediction engine
- a guarantee that an opportunity is commercially suitable

The official source remains authoritative. FedPulse exists to help you find the right official source faster and understand its context.

---

## The standard

A FedPulse recommendation should be able to answer four questions:

1. **What happened?**
2. **Why is it relevant?**
3. **Why is it showing up now?**
4. **Which official evidence proves it?**

If the system cannot answer those questions, the item should not be presented with confidence.

That is the product.
