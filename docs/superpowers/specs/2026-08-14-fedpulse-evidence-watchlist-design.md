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
- `normalized_exact` is restricted to Unicode normalization, case folding, harmless punctuation, whitespace, and documented terminal jurisdiction markers such as `(U.S.)`; it must never become fuzzy matching.

Package grouping normally uses the most specific canonical child agency. Parent-level grouping is allowed only when a coherent candidate contains records from at least two distinct child agencies with the same parent and those records share an exact topic or a direction-plus-sector pair. A single-child package displays the child; a cross-child package displays the parent and lists every participating child.

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

A same-day, same-family batch may nominate records for coherence testing, but it is not sufficient evidence of a package.

### 6.3 Deterministic grouping rules

Two records receive a package edge only when all required rules hold:

1. Same canonical child agency, or an eligible coherent parent-level grouping under section 5.3.
2. Publication dates fall inside the same inclusive three-calendar-day window.
3. At least one coherence condition holds:
   - the records share at least one exact Federal Register topic; or
   - the records share the same deterministic direction tag and at least one exact sector tag.

Same-day/same-family evidence alone never creates an edge. Three unrelated notices from one agency on one day do not form a package.

Union-find may identify initial connected components, but transitive closure may not stretch the date boundary. For each component, sort records by publication date and deterministically partition it into non-overlapping, earliest-first windows where `latest_date - earliest_date <= 2 days`. Re-run the coherence check inside each partition. No emitted package may span more than three calendar dates.

Packages require at least two records. A two-record package requires both a shared exact topic and a shared direction-plus-sector pair; packages of three or more require at least one of those coherence forms.

### 6.4 Stable identity and versions

A package has a stable logical identity and immutable versions.

The logical `package_id` is assigned when a cluster first qualifies, processing records chronologically, and is then immutable:

```text
canonical_coordination_agency_id + earliest_publication_date + core_cluster_key
```

`core_cluster_key` is a 12-character SHA-256 prefix over a versioned canonical string derived from the strongest shared evidence among the records in the first qualifying version:

1. lexicographically first dominant exact topic, when one is shared by a majority of members; otherwise
2. dominant direction plus lexicographically first shared sector.

The identity does not hash all member IDs, so ordinary membership growth within the same coherent cluster does not create an unrelated logical package. The initial core key is persisted and never recomputed from later membership. A full rebuild reproduces identity by replaying records in publication-date and record-ID order.

Each emitted state also has a `package_version_id`, calculated from `package_id`, sorted member record IDs, direction, confidence, and dictionary/mapping versions. Membership, direction, or confidence changes create a new immutable version with `supersedes_version_id` pointing to the prior version. Unchanged membership and classifications reproduce the same version ID. Lifecycle state is keyed by logical `package_id`.

Membership change is materially notifiable only when it adds at least two records, increases membership by at least 25%, introduces a higher-priority document family, or changes direction or confidence. Every version remains visible in audit history.

### 6.5 Direction classification

Direction is derived only from Federal Register `action`, `title`, and `abstract` metadata using a versioned fixed phrase dictionary. It does not read full document text.

Matching uses Unicode normalization, case folding, token/phrase boundaries, and deterministic diacritic handling. A negation marker (`not`, `no`, `never`, `without`) within the preceding three tokens blocks a match unless a longer explicit dictionary phrase defines the intended meaning. For example, `not proposing to remove` must not produce `reduce_or_rescind`. Exact multiword phrases are evaluated before single-token entries.

Initial direction tags:

- `reduce_or_rescind`: rescind, remove, eliminate, streamline, reduce burden, reduce cost, withdraw;
- `increase_or_require`: require, mandate, establish requirement, prohibit, restrict;
- `fund_or_award`: award, grant, cooperative agreement, funding;
- `consult_or_collect`: request for information, request for comment, information collection, public hearing;
- `authorize_or_permit`: authorize, permit, approval, exemption, waiver;
- `technical_or_conforming`: technical amendment, conforming amendment, correction;
- `mixed_or_unknown`.

A package receives a direction when at least 60% of its records share one tag. Otherwise it is `mixed_or_unknown`. The output includes matched phrases so the classification is auditable.

Every output includes `direction_dictionary_version`.

### 6.6 Sector and affected-party tags

Affected sectors come from a versioned deterministic map:

- canonical agency → default sectors;
- exact Federal Register topic → sectors;
- exact title keyword → sectors, for narrow high-confidence terms only.

Examples include credit unions, banking, hazardous-material carriers, agriculture, food manufacturing, healthcare, cybersecurity, aviation, energy, and government contractors.

Federal Register topic mappings are manually reviewed. Title mappings use exact token-boundary phrases, never substrings. Agency defaults are deliberately small and conservative.

The output calls these **coverage tags**, not inferred economic impacts. If no mapping exists, the package says `sector_tags: []`. Every tag contains provenance:

```json
{
  "sector": "credit_union",
  "source": "exact_fr_topic",
  "matched_value": "Credit unions"
}
```

### 6.7 Package confidence

Confidence expresses evidence quality, not predicted impact.

- **High:** at least three records; a shared exact topic or shared direction-plus-sector pair; at least 60% direction coherence; canonical agency known; all official URLs present.
- **Medium:** at least three records satisfying one coherence form from section 6.3 with canonical agency known but missing one high-confidence requirement, or two records satisfying both the shared-topic and direction-plus-sector requirements.
- **Low:** package passes minimum grouping but has weak topic cohesion, missing agency mapping, or incomplete URLs.

Record count alone never creates high confidence. The medium rule still requires the package-edge coherence rules in section 6.3; same-day/same-family is not sufficient. No statistical z-score can raise a low-evidence package to high confidence.

### 6.8 Package priority

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

### 8.1 Time and week conventions

- The Federal Register publication week is Monday through Friday in `America/New_York`.
- A complete week contains all five publication days; federal holidays remain zero-count days rather than disappearing from the series.
- The partial current week runs from Monday through the latest available FR publication date and appears in daily activity only; it is never anomaly-scored.
- `as_of` is an Eastern calendar date and every output includes `as_of_timezone: "America/New_York"`.
- `generated_at` is an ISO-8601 UTC timestamp ending in `Z` and every output includes `generated_at_timezone: "UTC"`.
- Week labels use the Monday start date. These definitions must be identical in code, tests, output metadata, and documentation.

### 8.2 FR weekly activity spike

- Federal Register records only.
- Complete Monday–Friday publication weeks, including zero-count weeks.
- Latest complete week compared with the preceding 16 complete weeks.
- Require at least eight complete weeks of history and at least three current records.
- Always report baseline sample size, complete raw weekly counts, current count, baseline mean, and baseline standard deviation.
- When baseline mean is at least five and standard deviation is positive, report a z-score and require z ≥ 2.5.
- When baseline mean is below five, use an exact Poisson upper-tail probability computed with the standard library; require `p <= 0.01`, current count ≥ 5, and an absolute increase of at least three over the baseline mean.
- When baseline standard deviation is zero, do not emit a numeric z-score or z-score alert. Report `statistical_evidence: insufficient_zero_variance`; a low-count Poisson result may be shown only as a separate method when its prerequisites hold.
- Partial weeks appear in daily counts but never in spike scoring.

### 8.3 Sustained level shift

Detect sustained output mode separately from a one-week spike:

- Compare the most recent four complete weeks with the preceding 12 complete weeks.
- Require at least 50% increase, a minimum absolute increase of four records, and activity in at least three of the four recent weeks.
- Report both window totals and per-week rates.

### 8.4 Rulemaking-pipeline transition

Two FR-only rolling 12-month ratios are reported:

- `proposal_to_final_ratio = proposed_rules / final_rules`, the primary rulemaking-pipeline measure;
- `activity_to_final_ratio = (proposed_rules + notices) / final_rules`, a broader workload/churn measure formerly called RCR.

Changes:

- Minimum denominator: at least 10 final rules, or at least 50 total counted documents and at least five final rules.
- Require at least 12 eligible historical monthly windows before computing an agency-history z-score.
- Compute cross-agency percentile among eligible agencies.
- A new alert requires either:
  - z-score ≥ 2.5 against the agency's own history and current percentile ≥ 80; or
  - current percentile ≥ 95 and current ratio at least 1.25 times the prior-month ratio.
- If historical standard deviation is zero or fewer than 12 eligible windows exist, suppress the history z-score rather than manufacturing an extreme value. The cross-sectional path still requires the explicit 1.25× month-over-month increase.
- Persistent conditions do not repeatedly notify.
- Report `newly_elevated`, `continuing`, or `resolved`.

The primary alert is based on `proposal_to_final_ratio`. `activity_to_final_ratio` remains visible as context and may receive a separately named workload alert, but it may not be labeled a rulemaking-pipeline transition.

### 8.5 MARC horizon confidence

TER remains MARC only and reports:

- first-seen cataloging date;
- last-four-week catalog count;
- prior baseline;
- distinct canonical agencies;
- same-day concentration;
- top source records.

A heading is high confidence only when the last four weeks contain at least 10 records across at least three distinct cataloging dates and three canonical agencies, and no single cataloging day contributes more than 50% of recent records. Batch-heavy or smaller headings remain visible but are labeled `catalog_batch_risk` or insufficient-sample confidence as appropriate.

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

CREATE TABLE package_versions (
    package_version_id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL,
    supersedes_version_id TEXT,
    created_at TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE package_version_records (
    package_version_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    PRIMARY KEY (package_version_id, record_id)
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

Material change is type-specific:

- packages: membership thresholds defined in section 6.4, direction change, confidence change, or a higher-priority document family;
- rulemaking/workload metrics: transition between elevated and normal, not ordinary ratio or z-score movement;
- FR activity: transition into or out of spike/level-shift state, not a score-only change;
- MARC horizon: confidence-state change or at least 25% growth with three or more added records.

The same logical signal may not notify again within 48 hours unless its direction or confidence changes, it gains a higher-priority document family, or it becomes stale/resolved. Score movement alone never bypasses the cooldown.

Telegram includes new, materially changed, resolved, and stale signals. Low-confidence packages are dashboard-only and never appear in the daily brief. The dashboard includes all states and version history.

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
  "generated_at_timezone": "UTC",
  "as_of": "YYYY-MM-DD",
  "as_of_timezone": "America/New_York",
  "source_freshness": {},
  "items": []
}
```

`source_freshness` has an explicit per-feed contract:

```json
{
  "federal_register": {
    "last_publication_date": "2026-08-06",
    "fetched_at": "2026-08-07T05:02:03Z",
    "status": "fresh"
  },
  "marc": {
    "last_cataloged_date": "2026-07-31",
    "maintenance_applied_at": "2026-08-07T05:05:00Z",
    "status": "degraded"
  }
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
- complete evidence list containing source record ID, title, type, publication date, official URL, and the exact metadata fields and matched values used for grouping, direction, coverage tags, confidence, priority, or watchlist selection.

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

Low-confidence packages never appear in the daily brief. They remain available on the dashboard with their confidence reasons.

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
- three unrelated same-day/same-family notices from one agency that must not group;
- a transitive date chain on days 1, 3, and 5 that must be split into globally bounded clusters;
- a negated direction phrase (`not proposing to remove`) that must not classify as `reduce_or_rescind`;
- a zero-variance baseline that must not emit a numeric z-score alert;
- a three-record/two-day MARC batch that must not become high confidence;
- a larger concentrated MARC catalog batch that must be downgraded.

Tests must not require network access or the production database.

### 14.3 Honest historical evaluation

Evaluation is separate from unit tests and package usefulness.

- Freeze event definitions before threshold tuning.
- Pre-register event dates, expected signal classes, minimum lead times, and negative controls in a versioned repository fixture before running or tuning the evaluation.
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
18. Three unrelated same-day/same-family notices from one agency do not form a high- or medium-confidence package and never enter the daily brief.
19. No package spans more than three inclusive publication dates after connected-component partitioning.
20. A zero-variance baseline never produces a numeric z-score alert and is reported as insufficient statistical evidence.
21. The complete Monday–Friday Eastern publication-week definition is identical in code, tests, outputs, and documentation.
22. An unchanged package reproduces the same package and version IDs; a material membership change creates a deterministic new version with `supersedes_version_id`.
23. MARC high confidence requires at least 10 records, three cataloging dates, three canonical agencies, and no single date above 50% concentration.
24. Direction classification handles word boundaries and three-token negation windows, including the required counterexample.
25. Low-confidence packages never appear in the daily brief.

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