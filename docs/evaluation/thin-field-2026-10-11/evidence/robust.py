"""Walk-forward test: does an office's prior award history forecast how many offers its next
competed construction procurement will draw?

Unit: one competed standalone procurement (first award per office + solicitation_identifier;
awards with no solicitation ID count individually). Excludes orders under IDVs, IDV base awards
(CONT_IDV_ keys -- the USAspending download returns them despite the A-D type filter), and
non-competed / 'NOT AVAILABLE FOR COMPETITION' awards. History must be >=30 days older than the
procurement being forecast; FY2023 is warm-up, FY2024-25 is scored.

Reports each grouping on (a) everything it can score, (b) the COMMON subset every grouping can
score (groupings scored on different subsets are not comparable), (c) the SAM-like population
(solicitation ID, PSC Y/Z, value >= $25k) against a nationwide composition baseline that uses no
office data, and (d) how concentrated the scored set is in a few offices.

Usage: uv run python -I robust.py <Contracts_PrimeAwardSummaries.csv> [out.json]
"""
import csv, json, statistics, sys
from collections import defaultdict
from datetime import date

csv.field_size_limit(10**8)
src = sys.argv[1]
out_path = sys.argv[2] if len(sys.argv) > 2 else None
GAP_DAYS, MIN_PRIOR = 30, 3


def fy(d):
    y, m = int(d[:4]), int(d[5:7])
    return y + 1 if m >= 10 else y


units = {}
for r in csv.DictReader(open(src, newline="", encoding="utf-8")):
    d = r["award_base_action_date"][:10]
    if len(d) < 10 or not (2023 <= fy(d) <= 2025): continue
    if r["parent_award_id_piid"].strip() or r["contract_award_unique_key"].startswith("CONT_IDV_"): continue
    c = r["extent_competed"].upper()
    if not c or "NOT COMPETED" in c or "NOT AVAILABLE" in c: continue
    try: o = float(r["number_of_offers_received"])
    except ValueError: continue
    if o <= 0 or o >= 999: continue  # 999 = not captured
    sol = r["solicitation_identifier"].strip().upper()
    k = ("S", r["awarding_office_code"], sol) if sol else ("A", r["contract_award_unique_key"])
    if k not in units or d < units[k]["date"]:
        try: v = float(r["potential_total_value_of_award"])
        except ValueError: v = 0.0
        units[k] = {"date": d, "fy": fy(d), "office": r["awarding_office_code"], "psc": r["product_or_service_code"][:4],
                    "naics": r["naics_code"][:6], "offers": o, "has_sol": bool(sol), "value": v,
                    "proc": r["solicitation_procedures"].upper(), "setaside": r["type_of_set_aside"].upper()}
comp = sorted(units.values(), key=lambda u: u["date"])
for i, u in enumerate(comp): u["i"] = i

GROUPINGS = [
    ("office x PSC", lambda u: (u["office"], u["psc"])),
    ("office x NAICS6", lambda u: (u["office"], u["naics"])),
    ("office only", lambda u: u["office"]),
    ("PSC only (nationwide)", lambda u: u["psc"]),
    ("NAICS6 only (nationwide)", lambda u: u["naics"]),
    # Uses no office information: how the notice is bought x set-aside x construction(Y)/repair(Z)/other.
    ("baseline: procedure x set-aside x PSC letter (nationwide)", lambda u: (u["proc"], u["setaside"], u["psc"][:1])),
]


def sam_like(u):
    """Looks like an open SAM construction notice: has a solicitation ID, PSC Y/Z, potential value >= $25k.
    (Value is post-award; used only to define the evaluation population.)"""
    return u["has_sol"] and u["psc"][:1] in ("Y", "Z") and u["value"] >= 25000


def forecasts(keyfn):
    """index -> median offers of same-group procurements >= GAP_DAYS older (if >= MIN_PRIOR of them)."""
    hist = defaultdict(list); out = {}
    for u in comp:
        d = date.fromisoformat(u["date"])
        h = [o for (hd, o) in hist[keyfn(u)] if (d - hd).days >= GAP_DAYS]
        if len(h) >= MIN_PRIOR and u["fy"] >= 2024: out[u["i"]] = statistics.median(h)
        hist[keyfn(u)].append((d, u["offers"]))
    return out


def rank(xs):
    o = sorted(range(len(xs)), key=lambda i: xs[i]); rk = [0.0] * len(xs); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and xs[o[j + 1]] == xs[o[i]]: j += 1
        for k in range(i, j + 1): rk[o[k]] = (i + j) / 2 + 1
        i = j + 1
    return rk


def spearman(a, b):
    ra, rb = rank(a), rank(b); ma, mb = statistics.mean(ra), statistics.mean(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra); vb = sum((y - mb) ** 2 for y in rb)
    return round(cov / (va * vb) ** 0.5, 3)


def score(label, fc, idx):
    pred = [fc[i] for i in idx]; act = [comp[i]["offers"] for i in idx]
    lo = [a for p, a in zip(pred, act) if p <= 2]; hi = [a for p, a in zip(pred, act) if p >= 5]
    pct = lambda xs: round(100 * sum(a <= 2 for a in xs) / len(xs), 1) if xs else None
    return {"label": label, "n_scored": len(idx), "spearman": spearman(pred, act), "base_le2_pct": pct(act),
            "pred_le2_n": len(lo), "pred_le2_actual_le2_pct": pct(lo),
            "pred_ge5_n": len(hi), "pred_ge5_actual_le2_pct": pct(hi)}


fcs = {label: forecasts(fn) for label, fn in GROUPINGS}
common = sorted(set.intersection(*(set(f) for f in fcs.values())))
out = {
    "units": len(comp), "units_with_solicitation_id": sum(1 for u in units if u[0] == "S"),
    "each_on_own_subset": [score(label, fcs[label], sorted(fcs[label])) for label, _ in GROUPINGS],
    "common_subset_n": len(common),
    "on_common_subset": [score(label, fcs[label], common) for label, _ in GROUPINGS],
}
# SAM-like population, each grouping on what it can score there, plus the paired office x PSC vs baseline comparison.
sl = {u["i"] for u in comp if sam_like(u)}
out["sam_like_units"] = len(sl)
out["sam_like_each_on_own_subset"] = [score(label, fcs[label], sorted(set(fcs[label]) & sl)) for label, _ in GROUPINGS]
pair = sorted(set(fcs["office x PSC"]) & set(fcs[GROUPINGS[-1][0]]) & sl)
out["sam_like_paired_n"] = len(pair)
out["sam_like_paired"] = [score(label, fcs[label], pair) for label in ("office x PSC", GROUPINGS[-1][0])]
# Concentration: which offices dominate the office x PSC scored set, and the result without the largest one.
scored = sorted(fcs["office x PSC"]); by_office = defaultdict(int)
for i in scored: by_office[comp[i]["office"]] += 1
top = sorted(by_office.items(), key=lambda x: -x[1])[:5]
out["office_x_psc_top_offices"] = [(o, n, round(100 * n / len(scored), 1)) for o, n in top]
out["office_x_psc_without_top_office"] = score("office x PSC minus " + top[0][0], fcs["office x PSC"], [i for i in scored if comp[i]["office"] != top[0][0]])
print(json.dumps(out, indent=1))
if out_path: json.dump(out, open(out_path, "w"), indent=1)
