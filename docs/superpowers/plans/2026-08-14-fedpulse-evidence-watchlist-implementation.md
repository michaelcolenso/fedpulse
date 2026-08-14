# FedPulse Evidence-Ranked Watchlist Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace FedPulse’s mixed-feed anomaly dashboard with an evidence-ranked regulatory watchlist that deterministically detects coherent Federal Register packages, consequential standalone records, honest FR-only metrics, and MARC-only horizon signals.

**Architecture:** Preserve the existing parsers and ingestion path. Add an idempotent schema migration and isolated v0.2 modules for taxonomy, agency normalization, package detection, metrics, lifecycle, atomic outputs, and briefing. Build and test entirely against temporary SQLite databases and golden metadata fixtures; switch the nightly pipeline and dashboard only after all backend contracts pass. Production DB migration and a real nightly run are parent acceptance steps, not worker steps.

**Tech Stack:** Python 3.11+ standard library (`sqlite3`, `zoneinfo`, `datetime`, `statistics`, `hashlib`, `json`, `fcntl`, `tempfile`), vanilla JavaScript/CSS, SQLite WAL, uv. No runtime LLM, NLP framework, embeddings, third-party dependencies, or network-dependent tests.

**Approved design:** `docs/superpowers/specs/2026-08-14-fedpulse-evidence-watchlist-design.md`

**Worker safety boundary:** Do not modify `data/fedpulse.db`, `data/raw/`, `data/outputs/`, `reviews/`, `~/.hermes/`, cron state, Tailscale, or running services. Do not run live ingestion, migration, index generation, or nightly scripts. Tests must use temporary databases and fixtures. Commit only explicitly listed repository files.

---

## Task 1: Establish v0.2 golden fixtures and test helpers

**Objective:** Create reusable, sanitized Federal Register and MARC metadata fixtures for all approved positive and adversarial cases.

**Files:**
- Create: `tests/fixtures/v2_records.json`
- Create: `tests/v2_helpers.py`
- Create: `tests/test_v2_fixtures.py`

**Step 1: Write the failing fixture-contract test**

Test that the fixture file contains named cases:

```python
REQUIRED_CASES = {
    "ncua_package",
    "phmsa_package",
    "cdc_funding_package",
    "nist_standalone",
    "unrelated_same_day_notices",
    "transitive_date_chain",
    "negated_direction",
    "zero_variance_weeks",
    "small_marc_batch",
    "concentrated_marc_batch",
}
```

Each record must include `id`, `source`, `title`, `agency`, `doc_type`, appropriate dates, URL, subjects/topics, and structured `raw_json` metadata. FR records must use official-looking but non-live `https://www.federalregister.gov/...` fixture URLs.

**Step 2: Run the test and verify failure**

Run:

```bash
PYTHONPATH=src uv run python -m unittest tests.test_v2_fixtures -v
```

Expected: FAIL because fixtures/helpers do not exist.

**Step 3: Implement fixtures and helpers**

`tests/v2_helpers.py` must expose:

```python
def temp_db(): ...
def seed_records(conn, rows): ...
def load_case(name: str) -> list[dict]: ...
def fr_record(...): ...
def marc_record(...): ...
```

Fixtures must encode:

- NCUA: at least 5 final actions, same agency/date, `reduce_or_rescind`, credit-union topic/sector coherence.
- PHMSA: at least 5 hazardous-material actions within three inclusive dates.
- CDC: at least 5 grant/cooperative-agreement notices.
- NIST: one AI/NVD RFI.
- Three unrelated same-day notices from one agency with no shared topic or direction-plus-sector.
- A day-1/day-3/day-5 chain that would over-stretch naive union-find.
- `not proposing to remove` negation.
- A low-count zero-variance weekly series.
- Three MARC records over two days/three agencies.
- At least 10 MARC records concentrated over multiple agencies but >50% on one date.

**Step 4: Run fixture tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/fixtures/v2_records.json tests/v2_helpers.py tests/test_v2_fixtures.py
git commit -m "test: add FedPulse v2 golden metadata fixtures"
```

---

## Task 2: Add idempotent v0.2 schema migration

**Objective:** Add canonical-agency, package-version, lifecycle, and pipeline-health storage without rebuilding existing records.

**Files:**
- Modify: `src/fedpulse/schema.sql`
- Modify: `src/fedpulse/db.py`
- Create: `tests/test_v2_schema.py`

**Step 1: Write failing migration tests**

Tests must prove:

- `db.init_db()` on a new DB creates all v0.2 columns/tables.
- Calling `db.init_db()` twice is safe.
- Initializing a legacy `records` table adds `canonical_agency_id` and `canonical_agency_name` without losing rows.
- Tables exist: `agency_aliases`, `signal_state`, `package_versions`, `package_version_records`, `pipeline_state`.
- Required indexes and foreign keys exist.

**Step 2: Verify tests fail**

Run the focused test; expected missing columns/tables.

**Step 3: Implement migration**

Add `CREATE TABLE IF NOT EXISTS` definitions to `schema.sql`. Because SQLite lacks portable `ADD COLUMN IF NOT EXISTS`, add:

```python
def _ensure_column(conn, table: str, column: str, declaration: str) -> None:
    names = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in names:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
```

Call it from `init_db()` after the base schema. Add indexes on canonical agency/date and package/version lookup. Keep all migrations idempotent.

**Step 4: Verify focused and full suites pass**

```bash
PYTHONPATH=src uv run python -m unittest tests.test_v2_schema -v
PYTHONPATH=src uv run python -m unittest discover -s tests -v
```

**Step 5: Commit**

```bash
git add src/fedpulse/schema.sql src/fedpulse/db.py tests/test_v2_schema.py
git commit -m "feat: add idempotent FedPulse v2 schema"
```

---

## Task 3: Implement versioned deterministic taxonomy

**Objective:** Add exact agency aliases, direction classification with negation, sector provenance, and standalone watchlists.

**Files:**
- Create: `src/fedpulse/config/agency_aliases.json`
- Create: `src/fedpulse/config/direction_phrases.json`
- Create: `src/fedpulse/config/sector_map.json`
- Create: `src/fedpulse/config/watchlists.json`
- Create: `src/fedpulse/taxonomy.py`
- Create: `tests/test_v2_taxonomy.py`

**Step 1: Write failing taxonomy tests**

Required behavior:

```python
normalize_org("Centers for Disease Control and Prevention (U.S.)")
# -> normalized exact form matching CDC alias

classify_direction({"action": "Final rule.", "abstract": "The agency is not proposing to remove the requirement."})
# -> mixed_or_unknown, no reduce_or_rescind match

classify_direction({"abstract": "The Board is rescinding redundant requirements."})
# -> reduce_or_rescind + matched phrase + dictionary version
```

Also test:

- word boundaries and case folding;
- exact multiword phrase precedence;
- diacritic normalization;
- exact topic sector mapping;
- phrase-boundary title mapping, never substring;
- coverage tag provenance object;
- NIST fixture exact watchlist match and its selection rule;
- unknown inputs remain unmapped/unknown.

**Step 2: Verify failure**

**Step 3: Implement taxonomy module**

Required public API:

```python
@dataclass(frozen=True)
class AgencyIdentity: ...

def normalize_org(name: str) -> str: ...
def canonicalize_agency(source: str, raw_name: str, raw_json: dict | None = None) -> AgencyIdentity: ...
def classify_direction(record: Mapping[str, Any]) -> dict: ...
def coverage_tags(record: Mapping[str, Any], identity: AgencyIdentity) -> list[dict]: ...
def watchlist_matches(record: Mapping[str, Any], identity: AgencyIdentity) -> list[dict]: ...
```

Use Unicode NFKD/NFKC consistently, `casefold()`, token boundaries, and a three-token preceding negation window. Load configs relative to `__file__`; every result includes config versions.

Initial aliases must cover active FR agencies and known CDC variants. Keep mappings conservative.

**Step 4: Verify tests**

**Step 5: Commit**

```bash
git add src/fedpulse/config src/fedpulse/taxonomy.py tests/test_v2_taxonomy.py
git commit -m "feat: add deterministic agency and policy taxonomy"
```

---

## Task 4: Add canonical-agency normalization service

**Objective:** Populate and update canonical agency fields deterministically while preserving raw agency provenance.

**Files:**
- Create: `src/fedpulse/normalize_agencies.py`
- Modify: `src/fedpulse/db.py`
- Modify: `src/fedpulse/fr_client.py`
- Create: `tests/test_v2_agencies.py`

**Step 1: Write failing tests**

Prove:

- FR raw agency IDs map to canonical child identity.
- CDC variants collapse to one canonical identity.
- raw `agency` remains unchanged.
- parent ID is retained in alias metadata.
- normalization is idempotent.
- unmapped MARC organizations remain explicit `NULL` canonical IDs.
- parent-level package coordination is possible only across at least two children sharing coherent evidence.

**Step 2: Verify failure**

**Step 3: Implement**

Add:

```python
def normalize_record_agency(conn, record_id: str) -> AgencyIdentity: ...
def normalize_all(conn, batch_size: int = 5000) -> dict[str, int]: ...
```

`normalize_all` commits by batch and returns mapped/unmapped counts. Do not invoke it against production in worker validation.

Update `fr_client.to_record()` to preserve agency IDs/parent IDs in `raw_json` and supply canonical values for newly ingested records where possible. Extend `db.upsert_record()` for canonical columns without requiring them from old callers.

**Step 4: Verify tests and old FR mapping tests**

**Step 5: Commit**

```bash
git add src/fedpulse/normalize_agencies.py src/fedpulse/db.py src/fedpulse/fr_client.py tests/test_v2_agencies.py
git commit -m "feat: normalize canonical agency identities"
```

---

## Task 5: Implement coherent regulatory-package engine

**Objective:** Detect only evidence-coherent FR packages with globally bounded dates, stable logical identity, and immutable versions.

**Files:**
- Create: `src/fedpulse/packages.py`
- Create: `tests/test_v2_packages.py`

**Step 1: Write failing package tests**

Required tests:

- NCUA, PHMSA, and CDC fixtures form three separate packages with expected directions/tags.
- Three unrelated same-day/same-family notices form no package.
- Same-day/family alone creates no edge.
- Two-record package requires shared topic **and** direction-plus-sector.
- Three-record package requires at least one coherence form.
- Day-1/day-3/day-5 chain is partitioned so no package spans more than three inclusive dates.
- Child agencies remain split unless at least two siblings under one parent share coherent evidence.
- Count alone never produces high confidence.
- Missing URL prevents high confidence.
- Exact package ID and version ID are deterministic across repeated runs.
- Unchanged membership preserves both IDs.
- Material membership growth creates a new version with `supersedes_version_id`, while logical package ID remains stable.
- Score-only movement is not a material package change.
- All evidence records include source ID, URL, and exact matched metadata.

**Step 2: Verify failure**

**Step 3: Implement package engine**

Required API:

```python
@dataclass(frozen=True)
class EnrichedRecord: ...

def enrich_record(row) -> EnrichedRecord: ...
def candidate_edges(records: Sequence[EnrichedRecord]) -> list[tuple[str, str, dict]]: ...
def bounded_components(records, edges, max_span_days: int = 2) -> list[list[EnrichedRecord]]: ...
def package_identity(component, prior_state=None) -> dict: ...
def score_package(component, metrics=None, watchlists=None) -> dict: ...
def detect_packages(conn, as_of: str, lookback_days: int = 14) -> list[dict]: ...
def persist_package_versions(conn, packages: list[dict], now: str) -> list[dict]: ...
```

Use deterministic sorting everywhere. The core cluster key and version hashes must exactly follow the design. Confidence requires coherence; record count affects priority only.

**Step 4: Verify tests**

**Step 5: Commit**

```bash
git add src/fedpulse/packages.py tests/test_v2_packages.py
git commit -m "feat: detect coherent regulatory packages"
```

---

## Task 6: Implement honest FR calendar metrics

**Objective:** Replace mixed FR/MARC activity scores with complete-week FR spike and sustained-level metrics.

**Files:**
- Create: `src/fedpulse/metrics_v2.py`
- Create: `tests/test_v2_fr_metrics.py`

**Step 1: Write failing tests**

Test:

- Monday–Friday Eastern publication weeks.
- Holidays/missing weekdays and fully missing weeks appear as zero counts.
- Partial current week excluded from scoring.
- `as_of` Eastern and `generated_at` UTC metadata.
- Mean ≥5 positive-SD path uses z-score.
- Mean <5 path uses exact Poisson upper-tail probability.
- Zero variance emits no numeric z-score and reports `insufficient_zero_variance`.
- Baseline sample size and complete raw counts are exposed.
- Sustained four-week shift requires 50% increase, +4 absolute records, and activity in three recent weeks.
- MARC records never enter FR metrics.

**Step 2: Verify failure**

**Step 3: Implement**

Required API:

```python
EASTERN = ZoneInfo("America/New_York")

def complete_publication_weeks(as_of: date, count: int) -> list[tuple[date, date]]: ...
def poisson_upper_tail(k: int, mean: float) -> float: ...
def compute_fr_activity(conn, as_of: str) -> dict: ...
def compute_level_shifts(conn, as_of: str) -> dict: ...
```

Do not reuse the legacy `_week_start` behavior that omits zero weeks and scores the latest represented week.

**Step 4: Verify focused/full tests**

**Step 5: Commit**

```bash
git add src/fedpulse/metrics_v2.py tests/test_v2_fr_metrics.py
git commit -m "feat: add complete-week Federal Register metrics"
```

---

## Task 7: Implement proposal pipeline, workload ratio, and signal lifecycle

**Objective:** Separate proposal/final pipeline signal from notices-heavy workload and make notifications stateful.

**Files:**
- Modify: `src/fedpulse/metrics_v2.py`
- Create: `src/fedpulse/lifecycle.py`
- Create: `tests/test_v2_pipeline_metrics.py`
- Create: `tests/test_v2_lifecycle.py`

**Step 1: Write failing ratio tests**

Prove:

- `proposal_to_final_ratio` excludes notices.
- `activity_to_final_ratio` includes notices but is labeled workload.
- Eligibility is finals ≥10, or total ≥50 plus finals ≥5.
- Agency-history z requires 12 eligible windows.
- Zero-SD history suppresses z.
- Percentile path requires percentile ≥95 and ratio ≥1.25× prior month.
- History path requires z ≥2.5 and percentile ≥80.
- Small-sample agencies never flag.

**Step 2: Write failing lifecycle tests**

Prove `new`, `continuing`, `resolved`, and `stale`; 48-hour cooldown; score-only changes do not notify; direction/confidence/higher-family changes bypass cooldown; package membership follows material thresholds.

**Step 3: Implement**

Required API:

```python
def compute_pipeline_metrics(conn, as_of: str) -> dict: ...
def percentile_rank(values: Sequence[float], value: float) -> float: ...

def fingerprint(signal: Mapping[str, Any]) -> str: ...
def update_signal_state(conn, signals: Sequence[dict], now: str) -> list[dict]: ...
def should_notify(previous, current, now: datetime, cooldown_hours: int = 48) -> bool: ...
```

**Step 4: Verify tests**

**Step 5: Commit**

```bash
git add src/fedpulse/metrics_v2.py src/fedpulse/lifecycle.py tests/test_v2_pipeline_metrics.py tests/test_v2_lifecycle.py
git commit -m "feat: add honest pipeline metrics and signal lifecycle"
```

---

## Task 8: Implement MARC-only horizon confidence

**Objective:** Produce MARC horizon items with explicit catalog-batch and sample confidence.

**Files:**
- Create: `src/fedpulse/horizon.py`
- Create: `tests/test_v2_horizon.py`

**Step 1: Write failing tests**

Test:

- FR records never enter horizon calculations.
- High confidence requires ≥10 records, ≥3 cataloging dates, ≥3 canonical agencies, max daily concentration ≤50%.
- Three records/two days/three agencies are insufficient sample.
- Concentrated batch is `catalog_batch_risk`.
- Evidence includes record IDs, URLs, exact subject, raw/canonical agency, and catalog dates.
- First-seen language says “cataloged,” never “published.”

**Step 2: Verify failure**

**Step 3: Implement**

```python
def compute_marc_horizon(conn, as_of: str, recent_days: int = 28, baseline_days: int = 56) -> dict: ...
def horizon_confidence(...): ...
```

Use complete date ranges rather than only dates with records.

**Step 4: Verify tests**

**Step 5: Commit**

```bash
git add src/fedpulse/horizon.py tests/test_v2_horizon.py
git commit -m "feat: add MARC-only topic horizon confidence"
```

---

## Task 9: Harden MARC deletes and pipeline health

**Objective:** Make maintenance failures visible and support every observed deleted-record CSV header.

**Files:**
- Modify: `src/fedpulse/marc_sync.py`
- Create: `src/fedpulse/health.py`
- Create: `tests/test_v2_ops.py`

**Step 1: Write failing tests**

Test deleted headers:

- `Sys. No.`
- `System Number`
- `System Number `

Use first-column fallback only after normalized known-header matching. Test malformed/missing system numbers are counted as skipped and surfaced. Test pipeline state attempts/success/failure/degraded and >48-hour staleness.

**Step 2: Verify failure**

**Step 3: Implement**

`_delete_from_csv()` returns a structured result:

```python
{"rows": 10, "valid_ids": 9, "deleted": 7, "not_present": 2, "skipped": 1, "header": "Sys. No."}
```

Add health APIs:

```python
def record_attempt(conn, component, now): ...
def record_success(conn, component, now, detail=""): ...
def record_failure(conn, component, now, detail): ...
def source_freshness(conn, now): ...
```

**Step 4: Verify tests**

**Step 5: Commit**

```bash
git add src/fedpulse/marc_sync.py src/fedpulse/health.py tests/test_v2_ops.py
git commit -m "fix: harden MARC deletes and pipeline health"
```

---

## Task 10: Build versioned atomic outputs and evidence-first brief

**Objective:** Produce all schema-v2 output contracts atomically and an always-useful daily brief.

**Files:**
- Create: `src/fedpulse/outputs_v2.py`
- Create: `src/fedpulse/watchlist.py`
- Modify: `src/fedpulse/digest.py`
- Create: `tests/test_v2_outputs.py`
- Create: `tests/test_v2_digest.py`

**Step 1: Write failing tests**

Test output files/contracts:

- `daily_activity.json`
- `packages.json`
- `standalone.json`
- `fr_metrics.json`
- `marc_horizon.json`
- `health.json`
- `brief.json`

Every file must include schema version 2, UTC `generated_at`, Eastern `as_of`, explicit timezone fields, source freshness, and items. Atomic-write tests must prove an existing file is not partially replaced on serialization/write failure.

Test standalone NIST watchlist selection exposes exact match reason. Test a quiet successful day still emits totals. Test low-confidence packages never enter brief. Test stale/failed health appears first. Test evidence links/record IDs are included.

**Step 2: Verify failure**

**Step 3: Implement**

```python
def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None: ...
def build_v2_outputs(conn, as_of: str, out_dir: Path, now: datetime | None = None) -> dict: ...
def build_brief(payloads: Mapping[str, dict]) -> dict: ...
def render_text_brief(brief: Mapping[str, Any]) -> str: ...
```

Use temp file in destination directory, flush, `os.fsync`, then `os.replace`. Rewrite `digest.py` to read `brief.json`; retain a clear compatibility error if only legacy files exist.

**Step 4: Verify tests**

**Step 5: Commit**

```bash
git add src/fedpulse/outputs_v2.py src/fedpulse/watchlist.py src/fedpulse/digest.py tests/test_v2_outputs.py tests/test_v2_digest.py
git commit -m "feat: add atomic evidence-first FedPulse outputs"
```

---

## Task 11: Add safe v0.2 pipeline entry point and lock

**Objective:** Orchestrate normalization, metrics, packages, lifecycle, outputs, and health under an exclusive lock.

**Files:**
- Create: `src/fedpulse/pipeline_v2.py`
- Modify: `scripts/nightly.sh`
- Create: `tests/test_v2_pipeline.py`

**Step 1: Write failing tests**

Using dependency injection/mocks, prove:

- exclusive non-blocking lock prevents overlap;
- FR failure records failure and returns nonzero;
- MARC failure marks degraded but allows fresh FR output;
- successful quiet run generates brief;
- ordering matches the design;
- no production paths are needed in tests.

**Step 2: Verify failure**

**Step 3: Implement**

```python
def acquire_lock(path: Path): ...
def run_pipeline(db_path: Path, out_dir: Path, as_of: str | None = None, *, ingest_fr=True, sync_marc=True) -> int: ...
```

Add CLI flags `--db`, `--out`, `--as-of`, `--skip-ingest`, `--skip-marc`. Update `nightly.sh` to use explicit `/home/linuxbrew/.linuxbrew/bin/uv`, call one v0.2 entry point, and never silently swallow network/MARC health. Do not run it live as worker.

**Step 4: Verify tests and shell syntax**

```bash
bash -n scripts/nightly.sh
PYTHONPATH=src uv run python -m unittest tests.test_v2_pipeline -v
```

**Step 5: Commit**

```bash
git add src/fedpulse/pipeline_v2.py scripts/nightly.sh tests/test_v2_pipeline.py
git commit -m "feat: orchestrate locked FedPulse v2 pipeline"
```

---

## Task 12: Redesign dashboard around evidence packages

**Objective:** Replace the three score panels with freshness, daily totals, package cards, standalone matches, secondary metrics, and MARC horizon.

**Files:**
- Modify: `dashboard/index.html`
- Modify: `dashboard/style.css`
- Modify: `dashboard/app.js`
- Create: `tests/test_v2_dashboard.py`

**Step 1: Write static-contract tests**

Without third-party JS tooling, test HTML/JS text contracts:

- fetches all schema-v2 files;
- renders freshness banner and daily totals;
- package filters: agency, direction, sector, family, confidence, lifecycle;
- package expansion includes all evidence links;
- low-confidence styling is distinct;
- no legacy `api.json`/`rcr.json`/`ter.json` fetches;
- `esc()` is used for every dynamic HTML interpolation, including title attributes and URLs;
- external links use safe attributes.

**Step 2: Verify failure**

**Step 3: Implement dashboard**

Primary order:

1. health/freshness;
2. daily totals;
3. high/medium packages;
4. standalone matches;
5. secondary FR metrics;
6. MARC horizon;
7. methodology link.

Show priority components and confidence reasons, but never make a score the headline.

**Step 4: Verify static tests**

The parent will perform real browser/console verification after worker completion.

**Step 5: Commit**

```bash
git add dashboard tests/test_v2_dashboard.py
git commit -m "feat: redesign dashboard around regulatory packages"
```

---

## Task 13: Rewrite historical evaluation for honest lead time

**Objective:** Retire the misleading 4/9 test and pre-register reproducible events/negative controls.

**Files:**
- Create: `src/fedpulse/config/evaluation_events.json`
- Modify: `src/fedpulse/backtest.py`
- Create: `tests/test_v2_evaluation.py`

**Step 1: Write failing tests**

Test:

- event definitions include frozen ID/date/signal class/minimum lead days;
- RCR/API scan preceding 12–24 months and require ≥30-day lead;
- TER first-seen after event never passes;
- negative controls contribute to false-positive rate;
- exact lead times, precision, recall, false-positive rate, and median lead time are reported;
- horizon and predictive evaluations are separate;
- CFPB early fire can be represented while prior post-event TER examples fail as predictive signals.

**Step 2: Verify failure**

**Step 3: Implement**

Keep event fixture immutable except through reviewed commits. Output language must not mention “validated 4/9.”

**Step 4: Verify tests**

Do not run against the production DB as worker.

**Step 5: Commit**

```bash
git add src/fedpulse/config/evaluation_events.json src/fedpulse/backtest.py tests/test_v2_evaluation.py
git commit -m "test: evaluate FedPulse signals with honest lead time"
```

---

## Task 14: Update documentation and run offline integration verification

**Objective:** Document the monitoring product honestly and prove all components integrate on temporary fixtures.

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Create: `tests/test_v2_integration.py`

**Step 1: Write failing integration test**

Seed a temporary DB with golden fixtures, normalize, run v0.2 outputs, and assert:

- three coherent packages;
- NIST standalone item;
- no unrelated same-day package;
- bounded package spans;
- low-confidence exclusion from brief;
- valid schema-v2 files;
- evidence links and metadata provenance;
- health/freshness contract;
- rerun stability for package/version IDs;
- all JSON parses.

**Step 2: Verify failure**

**Step 3: Update docs and implementation wiring**

README/AGENTS must state:

- monitoring/prioritization, not pre-public prediction;
- FR daily vs MARC monthly clocks;
- package, standalone, metric, lifecycle, and confidence definitions;
- exact offline test and fixture commands;
- production migration/run commands reserved for operator execution.

**Step 4: Run complete offline verification**

```bash
PYTHONPATH=src uv run python -m unittest discover -s tests -v
bash -n scripts/nightly.sh
uv run python -m compileall -q src tests
```

Expected: all tests pass, shell syntax passes, compileall exits 0.

**Step 5: Inspect scope**

```bash
git status --short
git diff --check
```

Confirm no changes under `data/`, `reviews/`, `.hermes/`, or other forbidden paths.

**Step 6: Commit**

```bash
git add README.md AGENTS.md tests/test_v2_integration.py
git commit -m "docs: complete FedPulse v2 evidence watchlist"
```

---

## Parent acceptance after worker completion

The parent—not the implementation worker—must:

1. Inspect every commit and the complete diff against this plan and the approved design.
2. Verify forbidden paths and production DB hashes were unchanged by the worker.
3. Run the complete offline suite independently.
4. Run an independent spec-compliance review, then code-quality review.
5. Apply the idempotent migration to a production DB backup first.
6. Run agency normalization and v0.2 output generation against the backup.
7. Validate real NCUA, PHMSA, CDC, and NIST results against official evidence records.
8. Measure package volume, confidence mix, alert count, RCR eligibility, and false grouping.
9. Run a real locked nightly pipeline under the cron environment.
10. Verify JSON freshness, Telegram text, dashboard rendering, filters, evidence expansion, and browser console.
11. Configure managed dashboard serving only after application acceptance.
12. Update project state and report residual risks.

## Global completion criteria

- All 25 approved design acceptance criteria pass.
- Full offline tests pass without network or production DB.
- No FR/MARC clock mixing remains in v0.2 metrics.
- No count-only package confidence.
- No package spans more than three inclusive dates.
- No low-confidence package reaches the brief.
- Every user-visible claim has official evidence and exact selection metadata.
- Worker produces focused commits and no forbidden-path modifications.
