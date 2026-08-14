# FedPulse Evidence-Ranked Regulatory Watchlist — Design

**Status:** Draft for review  
**Date:** 2026-08-14  
**Product version:** FedPulse v0.2  
**Primary user:** Compliance and government-affairs teams  
**Runtime constraints:** Python 3.11+, standard library only, SQLite, vanilla JavaScript, no paid services, no runtime LLM/NLP, no full-document analysis

## 1. Executive summary

FedPulse v0.2 will stop presenting anomaly scores as the product. It will become an evidence-ranked regulatory watchlist that answers four questions every day:

1. **What changed?**
2. **Which changes form a coordinated package rather than isolated paperwork?**
3. **Why is each item unusual or operationally relevant?**
4. **Which official records prove it?**

The central product object becomes a **regulatory package**: a deterministic grouping of related Federal Register records associated with the same canonical agency, publication period, document family, and structured metadata themes. A package may represent coordinated deregulation, new requirements, a funding round, a consultation wave, a permitting program, or another concentrated government action.

Examples already present in the data illustrate the intended output:

- NCUA published 11 coordinated final actions on 2026-08-06 affecting credit-union operations and removing or simplifying several requirements.
- PHMSA published a broad package of hazardous-material transportation actions covering paperwork, training, packaging, special permits, rail reporting, batteries, aerosols, and fireworks.
- CDC published a coordinated international surveillance-funding round rather than a disease-outbreak signal.
- NIST published a strategically important standalone request for information about modernizing the National Vulnerability Database for artificial intelligence.

Statistical metrics remain useful, but only as supporting evidence. A z-score may help rank a package; it may not substitute for explaining the package.

## 2. Product promise

### 2.1 Honest promise

> FedPulse turns the daily Federal Register and the broader GPO catalog into a prioritized, evidence-backed account of coordinated federal action: what changed, the direction of change, who is plausibly affected, and the official records behind it.

### 2.2 Claims FedPulse will not make

FedPulse v0.2 will not claim:

- access to pre-public or non-public information;
- that every anomaly predicts enforcement, policy, markets, or news;
- that MARC cataloging dates represent publication dates;
- that a post-event catalog heading is an early warning;
- that a high churn ratio is actionable without adequate sample size;
- that public-domain source data or simple count math cannot be copied.

### 2.3 Definition of consistent usefulness

FedPulse is useful on a quiet day as well as a busy day. Each daily brief must provide:

- a complete count of new Federal Register records by canonical agency and document type;
- the highest-ranked coordinated packages, if any;
- consequential standalone records matching configured watchlists;
- newly elevated, continuing, and resolved statistical conditions;
- evidence links and calculation details;
- feed freshness and pipeline-health status.

“No anomalies” must never mean “no information.”

## 3. Design principles

1. **Evidence before score.** Every conclusion links to the exact official records that support it.
2. **Separate clocks.** Federal Register publication activity and MARC cataloging activity are never combined in one time-series metric.
3. **Deterministic core.** Runtime classification uses structured metadata, exact aliases, fixed dictionaries, and count math. No LLM, embeddings, semantic search, or full-text NLP.
4. **Explain every flag.** A user can reconstruct every score from the output.
5. **Scarce notifications.** Telegram reports new, materially changed, and resolved conditions; continuing conditions remain visible on the dashboard.
6. **Unknown stays unknown.** Unmapped agencies, sectors, or directions are labeled as such rather than guessed.
7. **Operational failure is signal.** A stale or failed feed must produce a visible warning.
8. **Validation precedes marketing.** Evaluation definitions are frozen before thresholds are tuned.

## 4. Source separation

### 4.1 Federal Register Regulatory Activity Monitor

**Cadence:** Daily.  
**Date used:** `publication_date`.  
**Purpose:** Current rules, proposed rules, notices, presidential documents, funding notices, consultations, and coordinated packages.

Federal Register records power:

- daily activity counts;
- regulatory package detection;
- standalone watchlist matches;
- weekly activity spikes;
- sustained activity shifts;
- rulemaking-pipeline transitions;
- source-document evidence lists.

### 4.2 GPO MARC Government Topic Horizon

**Cadence:** Monthly/periodic.  
**Date used:** `cataloged_date`, explicitly labeled as cataloging time.  
**Purpose:** Broad government-document coverage and controlled-subject-heading emergence.

MARC records power:

- first-seen controlled headings;
- subject-heading acceleration;
- cross-agency breadth;
- catalog-batch concentration;
- long-horizon topic histories.

MARC does not contribute to Federal Register volume, package, churn, or level-shift calculations.

## 5. Canonical agency model

### 5.1 Goal

Prevent duplicate series such as `Centers for Disease Control and Prevention` and `Centers for Disease Control and Prevention (U.S.)`, while preserving source provenance.

### 5.2 Tables

Add an `agency_aliases` table:

```sql
CREATE TABLE agency_aliases (
    source TEXT NOT NULL,
    raw_name TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    parent_id TEXT,
    mapping_method TEXT NOT NULL,
    PRIMARY KEY (source, raw_name)
);
```

Add nullable canonical fields to `records`:

```sql
ALTER TABLE records ADD COLUMN canonical_agency_id TEXT;
ALTER TABLE records ADD COLUMN canonical_agency_name TEXT;
```

### 5.3 Mapping rules

- Federal Register agency IDs are canonical for FR records.
- The most specific FR child agency remains the display agency; parent ID is retained.
- MARC aliases are exact, reviewed mappings only.
- Harmless punctuation and terminal jurisdiction markers may be normalized before exact lookup, using a documented function.
- No fuzzy matching.
- Unmapped values retain their raw agency and receive `canonical_agency_id = NULL`.
- Every mapping records its method: `fr_id`, `exact_alias`, `normalized_exact`, or `unmapped`.

### 5.4 Initial alias scope

The first release must cover all agencies appearing in current FR outputs and known duplicates discovered during the build, including CDC variants. It need not solve all 13,000+ MARC organization strings before release.

## 6. Regulatory package detection

### 6.1 Package definition

A regulatory package is a group of at least two Federal Register records that share a canonical agency and show deterministic evidence of coordinated action within a short publication period.

### 6.2 Candidate generation

Generate candidate groups from FR records published in the last 14 days using:

- canonical agency;
- publication date;
- normalized document family (`rule`, `proposed_rule`, `notice`, `presidential_document`);
- Federal Register topics;
- fixed action-direction tags;
- fixed sector tags.

### 6.3 Deterministic grouping rules

Records join the same package when all required rules hold:

1. Same canonical agency.
2. Publication dates are no more than three days apart.
3. At least one coordination condition holds:
   - three or more records share the same publication date and document family;
   - two or more records share at least one exact Federal Register topic;
   - two or more records share the same deterministic direction tag and at least one sector tag.

Connected records are grouped with union-find. Packages with only two records require a shared topic or shared direction-plus-sector evidence; a same-day pair alone is insufficient.

### 6.4 Direction classification

Direction is derived only from Federal Register `action`, `title`, and `abstract` metadata using a versioned fixed phrase dictionary. It does not read full document text.

Initial direction tags:

- `reduce_or_rescind`: rescind, remove, eliminate, streamline, reduce burden, reduce cost, withdraw;
- `increase_or_require`: require, mandate, establish requirement, prohibit, restrict;
- `fund_or_award`: award, grant, cooperative agreement, funding;
- `consult_or_collect`: request for information, request for comment, information collection, public hearing;
- `authorize_or_permit`: authorize, permit, approval, exemption, waiver;
- `technical_or_conforming`: technical amendment, conforming amendment, correction;
- `mixed_or_unknown`.

A package receives a direction when at least 60% of its records share one tag. Otherwise it is `mixed_or_unknown`. The output includes matched phrases so the classification is auditable.

### 6.5 Sector and affected-party tags

Affected sectors come from a versioned deterministic map:

- canonical agency → default sectors;
- exact Federal Register topic → sectors;
- exact title keyword → sectors, for narrow high-confidence terms only.

Examples include credit unions, banking, hazardous-material carriers, agriculture, food manufacturing, healthcare, cybersecurity, aviation, energy, and government contractors.

The output calls these **coverage tags**, not inferred economic impacts. If no mapping exists, the package says `sector_tags: []`.

### 6.6 Package confidence

Confidence expresses evidence quality, not predicted impact.

- **High:** at least five records, or at least three records with shared topic and shared direction; canonical agency known; all official URLs present.
- **Medium:** at least three same-day/same-family records with canonical agency known, or two records sharing topic plus direction.
- **Low:** package passes minimum grouping but has weak topic cohesion, missing agency mapping, or incomplete URLs.

No statistical z-score can raise a low-evidence package to high confidence.

### 6.7 Package priority

Priority orders the watchlist; it does not imply business impact. The score is an additive, published rubric:

- record count: 0–3 points;
- document-family weight: 0–3 points (`final rule` highest);
- topic cohesion: 0–2 points;
- direction consistency: 0–2 points;
- current activity anomaly: 0–2 points;
- configured watchlist match: 0–3 points;
- missing evidence penalty: 0 to −3 points.

Every package output includes the component scores.

## 7. Consequential standalone records

Package detection must not hide important single records such as the NIST NVD modernization RFI.

A standalone record enters the brief when it matches a configured watchlist by:

- canonical agency ID;
- exact Federal Register topic;
- document type;
- exact metadata keyword or phrase.

Initial watchlists are configuration files, not code, and include broad domains such as cybersecurity, finance, public health, trade/export controls, energy, environment, food/drug regulation, transportation, and procurement.

Each match reports the exact rule that selected it. No runtime semantic inference is permitted.

## 8. Supporting metrics

### 8.1 FR weekly activity spike

- Federal Register records only.
- Complete calendar weeks, including zero-count weeks.
- Latest complete week compared with the preceding 16 complete weeks.
- Require at least eight weeks of history and at least three current records.
- Report current count, baseline mean, baseline standard deviation, z-score, and source count.
- Partial weeks appear in daily counts but never in spike scoring.

### 8.2 Sustained level shift

Detect sustained output mode separately from a one-week spike:

- Compare the most recent four complete weeks with the preceding 12 complete weeks.
- Require at least 50% increase, a minimum absolute increase of four records, and activity in at least three of the four recent weeks.
- Report both window totals and per-week rates.

### 8.3 Rulemaking-pipeline transition

RCR remains `(proposed rules + notices) / final rules` over rolling 12-month windows, FR only.

Changes:

- Minimum denominator: at least 10 final rules, or at least 50 total counted documents and at least five final rules.
- Compute cross-agency percentile among eligible agencies.
- A new alert requires either:
  - z-score ≥ 2.5 against the agency's own history and current percentile ≥ 80; or
  - current percentile ≥ 95 and a material increase from the prior month.
- Persistent conditions do not repeatedly notify.
- Report `newly_elevated`, `continuing`, or `resolved`.

### 8.4 MARC horizon confidence

TER remains MARC only and reports:

- first-seen cataloging date;
- last-four-week catalog count;
- prior baseline;
- distinct canonical agencies;
- same-day concentration;
- top source records.

A heading is high confidence only when activity spans at least three canonical agencies and no single cataloging day contributes more than 50% of recent records. Batch-heavy headings remain visible but are labeled `catalog_batch_risk`.

## 9. Signal lifecycle and persistence

Add tables:

```sql
CREATE TABLE signal_state (
    signal_key TEXT PRIMARY KEY,
    signal_type TEXT NOT NULL,
    status TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_notified TEXT,
    fingerprint TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE pipeline_state (
    component TEXT PRIMARY KEY,
    last_attempt TEXT,
    last_success TEXT,
    status TEXT NOT NULL,
    detail TEXT
);
```

Lifecycle rules:

- `new`: first appearance or materially changed fingerprint;
- `continuing`: still qualifies, fingerprint unchanged;
- `resolved`: previously qualified but no longer qualifies;
- `stale`: source data or computation is outside freshness limits.

Telegram includes new, materially changed, resolved, and stale signals. The dashboard includes all states.

## 10. Output contracts

Write versioned JSON snapshots:

- `data/outputs/daily_activity.json`
- `data/outputs/packages.json`
- `data/outputs/standalone.json`
- `data/outputs/fr_metrics.json`
- `data/outputs/marc_horizon.json`
- `data/outputs/health.json`
- `data/outputs/brief.json`

Every file includes:

```json
{
  "schema_version": 2,
  "generated_at": "ISO-8601 timestamp",
  "as_of": "YYYY-MM-DD",
  "source_freshness": {},
  "items": []
}
```

Every package item includes:

- stable package ID;
- canonical and raw agency names;
- date span;
- concise deterministic label;
- direction and matched phrases;
- coverage tags and mapping evidence;
- record and document-type counts;
- confidence and confidence reasons;
- priority score components;
- lifecycle state;
- supporting metrics;
- complete evidence list containing title, type, publication date, and official URL.

The label is constructed from structured fields, for example:

> `NCUA · 11 final actions · reduce_or_rescind · credit unions`

Human-friendly prose may be added later, but v0.2 does not require generated summaries.

## 11. Daily brief

The digest always emits a useful brief after a successful run.

Required order:

1. Health/freshness warning, if present.
2. Daily activity totals.
3. New high-confidence packages.
4. New medium-confidence packages.
5. Consequential standalone watchlist matches.
6. Newly elevated or resolved supporting metrics.
7. MARC horizon changes only when new monthly data exists.

The brief never prints a list of 50 continuing RCR conditions. It links to the dashboard for continuing states.

Example:

```text
FEDPULSE — 2026-08-06

TODAY: 254 FR records · 31 rules · 14 proposed · 205 notices · 4 presidential

HIGH-CONFIDENCE PACKAGE
NCUA · 11 final actions · reduce_or_rescind · credit unions
Why: 11 same-day final actions; 9 matched reduce/remove/rescind phrases; volume 7.6× baseline
Evidence: [11 official links]

WATCHLIST
NIST · RFI · National Vulnerability Database + artificial intelligence
Matched: cybersecurity watchlist / exact title phrases
Evidence: [official link]
```

## 12. Dashboard redesign

The dashboard becomes evidence-first:

### Primary view

- freshness banner;
- daily Federal Register totals;
- package cards ordered by priority;
- standalone watchlist cards;
- filters for agency, direction, sector, document family, confidence, and lifecycle;
- package expansion showing every underlying official record.

### Secondary views

- FR activity metrics;
- rulemaking-pipeline transitions;
- MARC Government Topic Horizon;
- methodology and data provenance.

Scores remain visible but subordinate. A card headline never consists only of a z-score or ratio.

## 13. Pipeline and operational design

Nightly sequence:

1. Acquire an exclusive non-blocking pipeline lock.
2. Record pipeline attempt.
3. Check Federal Register connectivity.
4. Ingest recent Federal Register records.
5. Check and apply MARC maintenance files.
6. Normalize agency identities.
7. Compute daily activity and supporting metrics.
8. Detect packages and standalone matches.
9. Update lifecycle state.
10. Write all JSON files atomically via temporary files plus rename.
11. Validate schema, dates, URLs, and freshness.
12. Record pipeline success.
13. Emit daily brief.

Failure rules:

- Federal Register failure exits nonzero and emits an error.
- MARC failure is visible but does not invalidate fresh FR output; health becomes degraded.
- Output older than 48 hours is stale and must trigger a warning.
- Overlapping runs exit nonzero with a clear lock message.
- Deleted-record CSV parsing normalizes headers and supports all observed variants.
- The Linuxbrew uv path is explicit in the cron wrapper.

Dashboard serving must run under a managed service and restart automatically after reboot.

## 14. Validation strategy

### 14.1 Unit tests

Add deterministic tests for:

- canonical agency alias mapping and unmapped behavior;
- complete weekly series with zero weeks;
- partial-week exclusion;
- one-week spike and four-week level shift;
- RCR eligibility, percentile, and lifecycle transition;
- package grouping and non-grouping counterexamples;
- direction dictionary and mixed-package behavior;
- sector mapping provenance;
- MARC same-day batch concentration;
- deleted CSV header variants;
- freshness warnings;
- atomic output writes;
- lifecycle new/continuing/resolved behavior;
- digest evidence links and non-empty quiet-day output.

### 14.2 Golden fixtures

Create sanitized metadata fixtures representing:

- the NCUA 11-action package;
- the PHMSA hazardous-material package;
- the CDC international funding round;
- the NIST standalone RFI;
- an unrelated same-day agency batch that must not group;
- a MARC catalog batch that must be downgraded.

Tests must not require network access or the production database.

### 14.3 Honest historical evaluation

Evaluation is separate from unit tests and package usefulness.

- Freeze event definitions before threshold tuning.
- RCR/API signals count as early only when they fire at least 30 days before an event.
- Scan the preceding 12–24 months instead of testing only the event date.
- TER counts only when first seen on or before the comparison event.
- Report precision, recall, false-positive rate, lead time, and negative controls.
- Horizon detections and predictive detections are reported separately.
- Existing `4/9` claims are retired.

## 15. Migration and compatibility

- Existing `records` remain the source of truth.
- Additive schema migrations preserve the production database.
- Existing `api.json`, `rcr.json`, and `ter.json` remain available during one transition release but are labeled legacy.
- New dashboard code reads only schema-version-2 outputs.
- Agency normalization can be rerun idempotently.
- Package and lifecycle tables can be rebuilt from records.
- No full Federal Register re-download is required unless stored metadata lacks a field needed by the v0.2 contract.

## 16. Acceptance criteria

FedPulse v0.2 is ready for internal release only when:

1. FR and MARC records are never mixed in the same time-series metric.
2. Every package links to all underlying official records.
3. The NCUA, PHMSA, and CDC golden fixtures form three distinct, correctly directed packages.
4. The NIST fixture appears as a standalone watchlist item.
5. An unrelated same-day pair does not form a package.
6. Missing calendar weeks are represented as zero; partial weeks are excluded from anomaly scoring.
7. Known CDC agency variants resolve to one canonical identity.
8. RCR excludes inadequate samples and does not notify unchanged continuing conditions.
9. A MARC batch-concentrated topic is labeled low confidence or `catalog_batch_risk`.
10. Every alert explains selection, confidence, score components, and source cadence.
11. A successful quiet-day run still produces daily activity totals.
12. A stale or failed pipeline emits a visible warning and a nonzero failure status where appropriate.
13. All JSON output is atomic and schema-versioned.
14. The complete offline test suite passes.
15. A real pipeline run succeeds under the cron environment.
16. The dashboard renders the new outputs and exposes evidence links without browser-console errors.
17. Documentation describes FedPulse as monitoring and prioritization, not pre-public prediction.

## 17. Scope boundaries

### Included in v0.2

- Canonical agency layer sufficient for active/current outputs;
- FR-only packages, activity, sustained shifts, and pipeline transitions;
- MARC-only topic horizon with batch confidence;
- exact-rule watchlists;
- lifecycle state;
- evidence-first daily brief and dashboard;
- operational health and failure visibility;
- honest evaluation framework.

### Explicitly excluded

- Full-text document ingestion or analysis;
- LLM-generated summaries;
- embeddings or semantic clustering;
- market-price backtesting;
- user accounts, billing, or paid API tiers;
- exhaustive normalization of every historical MARC organization;
- claims of causal or market prediction;
- automated sector-impact estimation beyond deterministic coverage tags.

## 18. Implementation order

1. Operations and data-integrity hardening.
2. Canonical agency schema and migration.
3. FR calendar-series metrics and lifecycle model.
4. Regulatory package engine.
5. Standalone watchlists and deterministic tags.
6. MARC horizon confidence.
7. Versioned outputs and daily brief.
8. Dashboard redesign.
9. Honest historical evaluation.
10. End-to-end cron and browser verification.

This order protects the most valuable invariant: every user-visible claim must be traceable to fresh, correctly attributed official records.