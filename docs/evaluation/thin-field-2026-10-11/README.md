# Thin Field: evaluation record (2026-10-11)

**Verdict: don't build.** Thin Field was the idea of forecasting how many offers an open federal construction bid will draw, from the issuing office's past awards.
- **The headline backtest overstated the signal.** On notices that look like real SAM construction bids it is weak, and a nationwide table that uses no office data matches it.
- **A free version already exists.** HigherGov shows an equivalent competition estimate on public pages.
- **My own stop rule triggered.** Validation step 1 said to stop if a competitor offers this cheaply.

This file replaces the earlier pitch. That pitch claimed Spearman 0.62 and a 77% thin-field hit rate, and said the office mattered far more than the industry. None of those claims survive.

Status labels:
- **Confirmed**: I re-ran it on the data downloaded 2026-10-11, or saw it directly.
- **Agent-confirmed**: an independent review agent ran or saw it; I did not repeat it.
- **Unverified**: not checked.

---

## 1. What was tested

**Data:** USAspending prime-award extract, NAICS 23 construction, action dates FY2023–FY2025, downloaded 2026-10-11. It has 108,316 rows; 78,314 have a base award date in FY2023–25.
- **Confirmed:** the download returned 7,110 IDV base-award rows despite the A–D type filter in `evidence/usaspending_request.json`. The scripts now drop them.

**Unit:** one competed standalone procurement, 18,218 in total (10,841 with a solicitation ID).
- Excluded: orders under IDVs, IDV base awards, non-competed awards, and awards coded "NOT AVAILABLE FOR COMPETITION" (sole source).
- A solicitation that produced several awards counts once.

**Test:** walk forward through time.
- Each FY2024–25 procurement is forecast from the median offers of ≥3 same-group procurements that are at least 30 days older.
- Two populations are scored:
  - **All units:** everything the method can score.
  - **SAM-like units:** has a solicitation ID, PSC Y or Z, and potential value ≥ $25k. These look like the open notices the product would score. Value is a post-award field, used here only to define the population.

## 2. Results (confirmed, `evidence/robust.py` → `robust.json`)

| Population | Forecast from | Scored | Spearman | Forecast ≤2 → actually ≤2 | Base rate ≤2 |
|---|---|---|---|---|---|
| All units | office × PSC | 3,906 | 0.63 | 77.6% (n=1,556) | 45.4% |
| All units, **minus GSA office 47QSWA** | office × PSC | 3,078 | 0.39 | 57.0% (n=728) | 31.9% |
| **SAM-like** | office × PSC | 1,453 | **0.37** | **41.8%** (n=292) | 26.1% |
| SAM-like | office only | 3,074 | 0.33 | 39.8% (n=553) | 23.9% |
| SAM-like | nationwide baseline: procedure × set-aside × PSC letter (no office data) | 3,161 | 0.28 | 44.8% (n=270) | 24.1% |
| SAM-like, same 1,441 units | office × PSC | 1,441 | 0.37 | 41.5% (n=289) | 26.0% |
| SAM-like, same 1,441 units | nationwide baseline | 1,441 | 0.31 | 47.3% (n=150) | 26.0% |

**What this means:**
- **The 0.63 / 77.6% headline is mostly one office.** GSA office 47QSWA is 21.2% of the scored set (828 units). Those are small supply buys (PSC 5640 wallboard/insulation, 7930) coded as NAICS 23, and nearly all draw one offer. None of them would appear as SAM construction notices.
- **On SAM-like notices the signal is real but modest.** Office history gives Spearman about 0.37. When it flags a thin field, about 42% actually are, against a 26% base rate. Most flags are wrong.
- **Office data adds little over the baseline.** A nationwide table of how a notice is bought (procedure × set-aside × construction-vs-repair letter) does about as well, and its thin calls are more often right.
- **Earlier comparisons across groupings were invalid.** Each grouping was scored on a different subset. On the 3,473 procurements every grouping can score, all five land at Spearman 0.59–0.67. That is in `robust.json` under `on_common_subset`.

**Agent-confirmed** (the review agent's scripts; not re-run by me):
- **The difference from the baseline isn't significant.** Office-clustered bootstrap: the SAM-like office × PSC Spearman 95% CI is 0.285–0.435. The paired difference vs the baseline is +0.042 (CI −0.027 to +0.126), which includes 0.
- **Within a single office the forecast ranks almost nothing.** Median within-office Spearman is 0.03 across 46 offices with ≥20 scored units.
- **Low forecasts are overconfident.** On SAM-like units, a forecast of 1 offer meant 21% actually got exactly 1, and the median actual was 3.
- **Stable but modest everywhere.** Results hold at 30-, 90- and 180-day gaps. FY2024 scores 0.34 and FY2025 0.43; DoD 0.34 and civilian 0.38. In every slice it is only a little above the baseline.
- **Raw n overstates precision.** Same-day clusters inflate it: one unit per office-day gives 0.53 on all units.

## 3. Someone already ships it

- **HigherGov** (confirmed). The free public page for open solicitation 1240BD27Q0001 (Bonners Ferry Road Grading, due 2026-10-20) shows **"Est. Level of Competition: Low"**.
  - **Agent-confirmed:** the field appeared on 6 of 6 open construction solicitations checked. Its tooltip reads: *"Accounting for the NAICS/PSC, agency, set-aside, and opportunity stage, similar solicitations in the past have averaged N competitive bids."* That conditioning is close to the baseline above.
  - Paid plans start at $500/year (pricing page, agent-confirmed 2026-10-11). The estimate itself needs no login.
- **CLEATUS** (agent-confirmed): shows a NAICS-level bidder benchmark ("median of 3 bidders · 38% single-bid") on open notice pages. DATA tier from $39/user/month billed annually.
- **No offer-count forecast found** (agent-checked, public material only): GovTribe, GovWin IQ, SamSearch, Sweetspot, Bloomberg Government, GovSpend, Federal Compass and GovDash. Products behind a login are unverified.

## 4. Outside construction (agent-confirmed; own-subset results only)

| Segment | Units | Office × PSC Spearman | Forecast ≤2 → ≤2 vs base |
|---|---|---|---|
| Construction, value ≥$25k | 10,835 | 0.40 | 49.6% vs 28.7% |
| Services (NAICS 54+56), excluding R&D, ≥$25k | 12,124 | 0.53 | 67.2% vs 43.7% |
| Supplies (NAICS 31–33, 42), ≥$25k, excluding DLA | 58,127 | 0.59 | 66.6% vs 44.4% |

**Unverified:** none of these were tested against the nationwide baseline or restricted to SAM-like units. Section 2 shows those two steps cut the construction result roughly in half, so read these as upper bounds. HigherGov covers every category anyway.

## 5. Other claims that did not hold

- **The outcome loop is unproven.** It relied on SAM `Sol#` matching FPDS `solicitation_identifier`, which was never tested. In the one available overlap (mostly IDV award notices), 6 of 112 matched (agent-confirmed).
- **The kill threshold was set against the wrong benchmark.** The prospective test's "≥60% vs 77% backtest" rule was miscalibrated. The achievable rate on SAM-like notices is about 40–42%.
- **"Competed" earlier included sole-source awards.** Corrected: among 18,369 competed standalone awards with an offer count, the median is 3 offers, 22.3% drew one offer and 39.0% drew ≤2. The earlier 33.0% / 46.4% figures included sole-source awards.

## 6. What is still useful (confirmed)

- **FedPulse Hidden Gems.** Don't imply "limited competition" from novelty alone. If a competition hint is wanted, a nationwide procedure × set-aside × PSC-letter prior, shown with its n, is about as informative as office history and needs no office data.
- **Data pitfalls for any FPDS work:**
  - The download returns IDV rows despite the A–D filter.
  - "NOT AVAILABLE FOR COMPETITION" is sole source.
  - Supply buys can carry NAICS 23.
  - Offer counts on orders under IDVs may reflect the parent vehicle.
  - Raw n overstates precision when many awards share an office and date.
- **WA market shape.** For WA-performed construction awards made in FY2023–25, 77.9% of obligations to date went through orders under existing IDVs/BPAs, such as NAVFAC NW MACCs. That is $1.55B obligated through 2026-10-11. For family, troop and other housing repair (PSC Z1F/Z2F A, C, Z; 21 awards, $36.9M), the share is 99.2%. 444 distinct small businesses won WA-performed construction work (509 firms of any size). Getting onto those IDV pools matters more than open notices. That lead is **untested as a product**.

## 7. fedpurchase: retired (confirmed)

- **Premise false.** FAR 4.606(c)(1) (FAC 2026-01): purchase-card transactions below the micro-purchase threshold are not reported to FPDS.
- **Measured before the database was deleted** (no longer re-derivable):
  - 1,745,015 rows of small FPDS actions, dominated by orders to incumbents and mandatory sources (FY25 row counts: AmerisourceBergen 54,582, ASRC 33,792, National Industries for the Blind 33,323).
  - 99.75% of FY25 rows had no agency mapping.
  - Each fiscal year was missing its first ~4 weeks.
- **Stale threshold.** It hardcoded a $10,000 micro-purchase threshold; FAC 2025-06 raised it to $15,000 on 2025-10-01.
- **D1 database `fedpurchase` deleted 2026-10-11** at the owner's request. No Worker or Pages project referenced it, and a lookup now returns "not found".
- **Leaked `ADMIN_SECRET`** (public repo) removed from the tree in fedpurchase PR #9. It remains in git history and must be treated as burned.

## Reproduce

All scripts are stdlib-only; run each with `python3 -I`. Each takes an optional output path.

| Script | What it does | Output |
|---|---|---|
| `evidence/robust.py <fpds.csv> [out.json]` | The full backtest: own subset, common subset, SAM-like population, baseline, office concentration | `robust.json` |
| `evidence/coverage.py <fpds.csv> <sam.csv> <YYYY-MM-DD> [out.json]` | Open-notice coverage, by posting and by unique solicitation | `coverage.json` |
| `evidence/analyze.py <fpds.csv> <out.json>` | Fill rates, offer distributions, WA and residential breakdowns | `result.json` |

- **Request:** the exact USAspending request is `evidence/usaspending_request.json`; IDV rows come back anyway and the scripts drop them.
- **SAM data:** the public ContractOpportunitiesFullCSV extract.
- **Agent outputs:** `evidence/generality/*.json`.
