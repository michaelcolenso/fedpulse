# Pursuit brief pilot — Phase 0 baseline and feasibility audit

**Date:** 2026-09-22 · **Plan:** Fedpulse pivot agent build plan (2026-09-21)
**Repo revision:** `c0bfed973f304a1619a20c015c1dd8015b2167fb` (confirmed still
the default-branch HEAD at audit time)

## 0. Baseline

| Check | Result |
|---|---|
| Offline test suite | **121 tests pass** (matches the 19 Sep audit; reproduces on 3.12) |
| `bash -n scripts/nightly.sh` | clean |
| `python -m compileall -q src tests` | clean |
| Local dirty state | none (fresh archive of verified revision; the `uv.lock` one-liner noted in the plan lives in the earlier planning workspace, not here) |

Instruction-drift reconciliation is recorded in
`docs/adr-001-pursuit-scope-decision.md`. Component review of the mapped files
(`sam_opportunities_client.py`, `opportunities.py`, `action_graph.py`,
`ai_reranker.py`, `pipeline_v2.py`, `publish_dashboard.py`, `worker/src/index.js`,
`nightly.yml`) confirms every reuse/limitation note in plan §2, including:
office-geography leakage into `_geo_haystack`, award notices able to enter
`act_now`, 7-day lookback aging out older notices, upsert-overwrite in
`action_graph`, and publicly cacheable KV responses in the Worker.

## 1. Source extract

SAM.gov Contract Opportunities full datagov bulk CSV (public, keyless —
the same URL the existing client uses), downloaded 2026-09-22.

**Completeness caveat:** transfer stalls truncated the download; the audited
slice is **81,525 complete rows (~236 MB)** of a larger extract, taken from the
start of the file. All counts below are labeled accordingly and are a floor,
not a census. Re-running against the complete extract is a Phase 1 task (the
pipeline downloads it daily anyway). The slice is large relative to the
50-notice minimum the plan sets.

## 2. Corpus denominators (audited slice)

| Measure | Count | Notes |
|---|---|---|
| Total notice rows | 81,525 | all currently active (`Active=Yes`) |
| Construction NAICS (23xxxx, excl. A&E) | 13,048 | 16.0% of slice |
| A&E NAICS (541310–541380) | 2,568 | kept separate per plan |
| PoP state present | 25,344 (31%) | **69% of rows carry no structured PoP state** — geography screening must treat missing PoP as explicit unknown |
| Set-aside present | 38,022 (47%) | |
| Response deadline: datetime with UTC offset | 59,965 (74%) | |
| Response deadline: date-only | 10,569 (13%) | the plan's "time not supplied" precision case is common, not an edge |
| Response deadline: datetime, no offset | 731 (1%) | |
| Response deadline: missing | 10,260 (13%) | |
| Deadline already past at audit date | 58,640 | **the extract is heavily stale**: most rows with deadlines are past-due yet still `Active`. Exact-deadline and archive handling are load-bearing, not optional |

Type mix (slice): Combined Synopsis/Solicitation 25,593 · Solicitation 22,887 ·
Award Notice 13,159 · Presolicitation 7,613 · Special Notice 5,787 ·
Sources Sought 4,895 · Justification/J&A 923 · Modification/Amendment/Cancel 648 ·
Sale of Surplus 11 · Consolidate/Bundle 9.

Award Notices are 16% of the slice — the current ranker admits them to
`act_now`; the pursuit lane's stage rules must not.

## 3. Pilot-geography audit: construction in Washington

| Measure | Count (slice) |
|---|---|
| WA-PoP construction notices, all types | 228 |
| — Solicitation | 91 |
| — Combined Synopsis/Solicitation | 47 |
| — Presolicitation | 55 |
| — Sources Sought | 13 |
| — Award Notice / Special Notice / Justification | 22 |
| Open-bid lane (Solicitation + Combined) | 138 |
| — with deadline in the future | 19 |
| — with set-aside | 122 |
| **30-day posting flow, all types** | **90** |
| — 30-day flow, open-bid lane | **63 (≈2/day)** |
| Early-interest lane with future response date | 5 |
| Construction rows with **office in WA but PoP elsewhere** | 167 |

Read of the numbers:

- **Flow, not stock, is the pilot metric.** Standing actionable inventory
  (~19 open-lane items with future deadlines, collapsing to ~8 distinct
  solicitation families) is thin at any instant, but ~63 new open-lane items
  posted in 30 days gives a daily digest real material. Prospective
  observation during the pilot remains the definitive test, as the plan
  states.
- **Solicitation families collapse hard.** The 19 open items are 8 families;
  `W912EF26RA007` alone accounts for 4 rows. Without family grouping the
  product triple-counts everything.
- **Office-vs-PoP confusion is common** (167 construction rows in-slice have
  a WA office and out-of-state PoP; two of the five sample families below
  have non-WA offices for WA work). Geography matching must use PoP only.
- **Missing PoP (69% corpus-wide) is the dominant geography failure mode** —
  the "needs confirmation" path will see heavy use, and cited description
  text (Phase 3 enrichment) is the planned remedy.

## 4. Document access

`AdditionalInfoLink` is empty on all five sample families; the bulk extract
carries no description text and no attachment URLs. Description and
attachment access therefore depends on the GSA Get Opportunities API, which
requires an API key. **No key was available to this audit**, so:

- readable-document coverage: **unverified, blocked on API credential**
- adapter + recorded-fixture workflow: buildable without the key (plan §5)
- the five briefs below are metadata-only, labeled as such, exactly the
  Phase 2 fallback posture

Phase 1 should obtain a key and measure what fraction of the ~20 open-lane
families expose readable attachments; that number decides whether Phase 3
extraction is a feature or a fixture.

## 5. Five sample pursuit briefs (metadata-only demonstration)

**Demo profile (fictional):** "Cascade Demo Builders LLC" — WA small GC;
states: WA; NAICS 236220, 237110, 237310, 238220, 238290, 238990; total
small-business eligibility **asserted** (dated customer assertion, scope
238xxx); single-job bonding capacity **unknown**; comparable-project history
**not provided**; prime pursuit: yes.

Every fact below cites the bulk-extract row field. Document-derived
requirements (site visits, bonds, experience thresholds) are **not reviewed**:
coverage = `unavailable` for documents. These are demonstration briefs, not
customer deliverables.

---

### Brief 1 — Lower Monumental PH HVAC System Upgrade

- **Agency/office:** Dept. of the Army, USACE Walla Walla District
  [source: row `447b7bb9`, fields `Sub-Tier`, `Office`]
- **Solicitation:** W912EF26RA007 · **Stage:** Solicitation (open-bid lane)
- **PoP:** Kahlotus, WA 99335 [field `PopCity/PopState/PopZip`] — verified WA
- **Scope:** HVAC system upgrade, plumbing/HVAC trade (NAICS 238220, PSC
  Y1KA construction of office buildings) [fields `NaicsCode`,
  `ClassificationCode`]
- **Fit:** NAICS match (238220 in profile); PoP in included state; open
  unrestricted solicitation (no set-aside — compatible with any profile)
- **Unknowns needing confirmation:** bonding requirements not stated in
  metadata → *confirm bonding capacity*; site-visit and experience
  requirements not reviewed (documents unavailable)
- **Material change detected (metadata):** deadline extended
  2026-09-22T14:00-07:00 → **2026-09-30T14:00:00-07:00** across 4 posted
  versions of this solicitation [rows `55f654d8` (08-21), `ffea0b71`
  (09-02), `b788b429` (09-15), `4df3319a` (09-18 14:02) all show 09-22;
  row `447b7bb9` (09-18 17:52) shows 09-30]
- **Next action:** submit response by **2026-09-30 14:00 PDT** (exact, offset
  supplied) — 8 days. Later posting superseded earlier deadline; verify
  against the current solicitation text before relying on it.
- **Source freshness:** extract downloaded 2026-09-22; latest family member
  posted 2026-09-18. **Coverage:** metadata only; documents unavailable.

### Brief 2 — USCG Air Station Port Angeles Main Gate Replacement

- **Agency/office:** US Coast Guard, Base Seattle [row `8d1c4155`]
- **Solicitation:** 70Z03326Q201900012 · **Stage:** Combined
  Synopsis/Solicitation (open-bid lane)
- **PoP:** Port Angeles, WA 98362 — verified WA
- **Scope:** gate replacement, other heavy/civil specialty trade (NAICS
  238990, PSC Z2PZ)
- **Fit:** NAICS match; **Total Small Business Set-Aside** — compatible with
  the profile's dated SB assertion for 238xxx
- **Blockers/unknowns:** amendment history is dense (base + Amendments 01 and
  02 posted 09-09, 09-09, 09-17 ×2) — amendment contents not reviewed;
  bonding and visit requirements unknown
- **Next action:** respond by **2026-09-23 15:00 PDT** (exact) — 1 day.
  Deadline identical across all four family members; no deadline drift
  detected.
- **Coverage:** metadata only; documents unavailable. *At 1 day of runway
  this would normally surface as an urgent "already following?" item rather
  than a new pursuit.*

### Brief 3 — Air Handler Air Conditioning Units (Wapato)

- **Agency/office:** USDA Forest Service, CSA Intermountain 3, **Ogden, UT**
  [row `15a9579e`, fields `City/State`]
- **Solicitation:** 1240LN26Q0005 · **Stage:** Solicitation
- **PoP:** Wapato, WA 98951 — verified WA. **Office is in Utah**; an
  office-geography match would have (incorrectly) excluded or misattributed
  this. Live demonstration of the plan's PoP-only rule.
- **Scope:** air handler/AC units — NAICS 238220 (PSC J041
  maintenance/repair of HVAC). Borderline supply-vs-service; PSC J-codes
  suggest installed service work — flag for document review.
- **Fit:** NAICS match; Total SB set-aside compatible
- **Next action:** respond by **2026-09-24 12:30 CDT** (exact, offset
  supplied; note non-local timezone) — 2 days.
- **Coverage:** metadata only; documents unavailable.

### Brief 4 — Split-Unit HVAC Replacement, JBLM

- **Agency/office:** DoD, office in **North Carolina** [row `73d9faa0`]
- **Solicitation:** H9242126QE047 · **Stage:** Combined Synopsis/Solicitation
- **PoP:** Joint Base Lewis-McChord, WA 98433 — verified WA
- **Fit:** NAICS 238220 match; Total SB set-aside compatible
- **Material change (metadata):** earliest family member (posted 09-14
  09:24) carried deadline 2026-09-18T12:00-04:00; three later members carry
  **2026-09-24T13:00:00-04:00** — extension detected. Two members posted
  within 20 minutes of each other on 09-17 with identical content — likely
  a corrected re-post; dedup by content hash, not posting time.
- **Next action:** respond by **2026-09-24 13:00 EDT** — 2 days.
- **Coverage:** metadata only; documents unavailable.

### Brief 5 — Little Pend Oreille NWR Culvert Improvements

- **Agency/office:** FHWA Western Federal Lands Division, Vancouver, WA
  [row `d2185cb9`]
- **Solicitation:** 69056726B000007 · **Stage:** Solicitation — and the
  family includes a **presolicitation posted 2026-03-25** [row `dfb23756`],
  a six-month forecast-to-solicitation lifecycle visible in the data
- **PoP:** state WA only — city/ZIP missing → PoP precision is `partial`;
  title references Little Pend Oreille NWR (Stevens County) but title text
  is not authoritative geography
- **Scope:** culvert improvements, highway/street construction (NAICS
  237310, PSC Y1LB)
- **Fit:** NAICS match; Total SB set-aside compatible
- **Next action:** respond by **2026-10-20 14:00 PDT** — 28 days of runway;
  archive date 2026-12-30.
- **Coverage:** metadata only; documents unavailable.

## 6. Gate assessment (Phase 0 exit)

| Gate question | Finding |
|---|---|
| Target-buyer volume adequate? | **Yes, provisionally.** ~63 new WA open-lane construction items/30d in a partial extract; families collapse ~2.4:1. Real test is prospective flow during pilot. |
| Document access adequate? | **Unverified — blocked on GSA API key.** Zero description/attachment data in the bulk extract. |
| Instruction drift reconciled? | Yes — `docs/adr-001-pursuit-scope-decision.md` |
| Baseline reproducible? | Yes — 121/121 offline tests pass at the verified revision |
| Data supports the plan's hard rules? | Emphatically yes — amendment chains, deadline drift, office≠PoP, stale deadlines, and date-only precision all appear in a 20-family sample |

**Smallest remaining inputs to unblock Phase 0→1:** (1) GSA Get
Opportunities API key; (2) decision to proceed to Phase 1 (trustworthy
inventory) on this evidence.
