"""Descriptive probe of FPDS construction awards (NAICS 23), FY2023-FY2025: field fill rates, offer
distributions, residential-repair and WA breakdowns, and how much money flows through IDV orders.
Its 'predictive' block is a superseded first pass; robust.py is the authoritative backtest.

Usage: python3 -I analyze.py <contracts_prime_award_summaries.csv> <out.json>
"""
import csv, json, statistics, sys
from collections import defaultdict
from datetime import date

src, out_path = sys.argv[1], sys.argv[2]
csv.field_size_limit(10**8)

def fy(d):
    y, m = int(d[:4]), int(d[5:7])
    return y + 1 if m >= 10 else y

def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None

rows = []
with open(src, newline="", encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        d = r.get("award_base_action_date") or ""
        if len(d) < 10: continue
        f = fy(d)
        if f < 2023 or f > 2025: continue  # new awards only, not mods of older awards
        offers = num(r.get("number_of_offers_received"))
        if offers is not None and (offers >= 999 or offers < 0): offers = None  # 999 = not captured
        rows.append({
            "key": r["contract_award_unique_key"], "date": d[:10], "fy": f,
            "is_order": bool((r.get("parent_award_id_piid") or "").strip()), "parent": (r.get("parent_award_id_piid") or "").strip(),
            # The download returns IDV base awards (CONT_IDV_ keys) despite the A-D type filter; they have no parent PIID.
            "is_idv": r["contract_award_unique_key"].startswith("CONT_IDV_"),
            "type": r.get("award_type") or "",
            "office": r.get("awarding_office_code") or "", "office_name": r.get("awarding_office_name") or "",
            "agency": r.get("awarding_agency_name") or "", "sub": r.get("awarding_sub_agency_name") or "",
            "naics": (r.get("naics_code") or "")[:6], "psc": (r.get("product_or_service_code") or "")[:4],
            "state": r.get("primary_place_of_performance_state_code") or "",
            "recipient": r.get("recipient_name") or "", "uei": r.get("recipient_uei") or "",
            "obligated": num(r.get("total_obligated_amount")) or 0.0,
            "ceiling": num(r.get("potential_total_value_of_award")),
            "sol": (r.get("solicitation_identifier") or "").strip(),
            "offers": offers, "competed": r.get("extent_competed") or "",
            "setaside": r.get("type_of_set_aside") or "", "size": r.get("contracting_officers_determination_of_business_size") or "",
        })

res = {"n_awards": len(rows)}
n = len(rows)
res["fill"] = {
    "offers_present_pct": round(100 * sum(r["offers"] is not None for r in rows) / n, 1),
    "solicitation_id_present_pct": round(100 * sum(bool(r["sol"]) for r in rows) / n, 1),
    "orders_under_idv_pct": round(100 * sum(r["is_order"] for r in rows) / n, 1),
}
res["by_fy"] = {f: sum(1 for r in rows if r["fy"] == f) for f in (2023, 2024, 2025)}
res["extent_competed_top"] = sorted(((c, sum(1 for r in rows if r["competed"] == c)) for c in {r["competed"] for r in rows}), key=lambda x: -x[1])[:10]

# Standalone competed awards are where offer counts mean what they say (orders often inherit IDV-level counts).
def competed(r):
    c = r["competed"].upper()
    return bool(c) and "NOT COMPETED" not in c and "NOT AVAILABLE" not in c
standalone = [r for r in rows if not r["is_order"] and not r["is_idv"]]
res["fill"]["offers_present_standalone_pct"] = round(100 * sum(r["offers"] is not None for r in standalone) / len(standalone), 1)
res["fill"]["idv_base_rows"] = sum(r["is_idv"] for r in rows)
comp = [r for r in standalone if r["offers"] is not None and competed(r)]
res["fill"]["solicitation_id_present_on_competed_standalone_pct"] = round(100 * sum(bool(r["sol"]) for r in comp) / len(comp), 1)
res["standalone_competed_with_offers"] = len(comp)
offs = [r["offers"] for r in comp]
res["offers_dist_standalone_competed"] = {
    "median": statistics.median(offs) if offs else None,
    "pct_1_offer": round(100 * sum(o == 1 for o in offs) / len(offs), 1) if offs else None,
    "pct_le2": round(100 * sum(o <= 2 for o in offs) / len(offs), 1) if offs else None,
    "pct_ge5": round(100 * sum(o >= 5 for o in offs) / len(offs), 1) if offs else None,
}

def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i]); rk = [0.0] * len(xs); i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]: j += 1
        for k in range(i, j + 1): rk[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return rk

def spearman(a, b):
    ra, rb = rank(a), rank(b); ma, mb = statistics.mean(ra), statistics.mean(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra); vb = sum((y - mb) ** 2 for y in rb)
    return round(cov / (va * vb) ** 0.5, 3) if va and vb else None

def predictive(keyfn, label, min_prior=3):
    """Walk awards chronologically; predict each award's offers from the median of strictly earlier awards in the same group."""
    hist = defaultdict(list); pred, act = [], []
    for r in sorted(comp, key=lambda r: r["date"]):
        k = keyfn(r); h = hist[k]
        if len(h) >= min_prior and r["fy"] >= 2024:  # FY2023 is warm-up history only
            pred.append(statistics.median(h)); act.append(r["offers"])
        h.append(r["offers"])
    if not pred: return {"label": label, "n": 0}
    lo = [a for p, a in zip(pred, act) if p <= 2]; hi = [a for p, a in zip(pred, act) if p >= 5]
    return {
        "label": label, "n_scored": len(pred), "spearman": spearman(pred, act),
        "n_pred_le2": len(lo), "actual_le2_pct_when_pred_le2": round(100 * sum(a <= 2 for a in lo) / len(lo), 1) if lo else None,
        "n_pred_ge5": len(hi), "actual_le2_pct_when_pred_ge5": round(100 * sum(a <= 2 for a in hi) / len(hi), 1) if hi else None,
        "base_rate_le2_pct": round(100 * sum(a <= 2 for a in act) / len(act), 1),
    }

res["predictive"] = [
    predictive(lambda r: (r["office"], r["naics"]), "office x NAICS6"),
    predictive(lambda r: r["office"], "office only"),
    predictive(lambda r: r["naics"], "NAICS6 only (nationwide)"),
    predictive(lambda r: (r["office"], r["psc"]), "office x PSC"),
]

# Occupied-residential repair niche: family housing, troop housing (barracks), other residential.
RES = {"Z1FA", "Z1FC", "Z1FZ", "Z2FA", "Z2FC", "Z2FZ"}
resid = [r for r in rows if r["psc"] in RES]
def summarize(rs):
    if not rs: return {"n": 0}
    ob = sorted(r["obligated"] for r in rs)
    o = [r["offers"] for r in rs if r["offers"] is not None and not r["is_order"] and not r["is_idv"] and competed(r)]
    return {
        "n": len(rs), "obligated_usd": round(sum(ob)), "median_obligated_usd": round(statistics.median(ob)),
        "pct_orders_under_idv": round(100 * sum(r["is_order"] for r in rs) / len(rs), 1),
        "pct_small_business": round(100 * sum("SMALL" in r["size"].upper() and "OTHER" not in r["size"].upper() for r in rs) / len(rs), 1),
        "standalone_median_offers": statistics.median(o) if o else None, "standalone_with_offers": len(o),
        "distinct_winners": len({r["uei"] or r["recipient"] for r in rs}),
        "distinct_small_winners": len({r["uei"] or r["recipient"] for r in rs if "SMALL" in r["size"].upper() and "OTHER" not in r["size"].upper()}),
        "distinct_offices": len({r["office"] for r in rs}),
    }
res["residential_repair_all"] = summarize(resid)
res["residential_repair_by_psc"] = {p: summarize([r for r in resid if r["psc"] == p]) for p in sorted(RES)}
res["residential_repair_by_fy"] = {f: summarize([r for r in resid if r["fy"] == f]) for f in (2023, 2024, 2025)}
st = defaultdict(float)
for r in resid: st[r["state"]] += r["obligated"]
res["residential_repair_top_states_usd"] = [(s, round(v)) for s, v in sorted(st.items(), key=lambda x: -x[1])[:12]]
ag = defaultdict(float)
for r in resid: ag[r["sub"]] += r["obligated"]
res["residential_repair_top_subagencies_usd"] = [(s, round(v)) for s, v in sorted(ag.items(), key=lambda x: -x[1])[:10]]
res["residential_repair_WA"] = summarize([r for r in resid if r["state"] == "WA"])
res["construction_WA_all"] = summarize([r for r in rows if r["state"] == "WA"])
wa_off = defaultdict(lambda: [0, 0.0])
for r in rows:
    if r["state"] == "WA": wa_off[r["office_name"]][0] += 1; wa_off[r["office_name"]][1] += r["obligated"]
res["construction_WA_top_offices"] = [(k, v[0], round(v[1])) for k, v in sorted(wa_off.items(), key=lambda x: -x[1][1])[:10]]

json.dump(res, open(out_path, "w"), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))

# Where does the money flow: standalone awards vs orders under IDV pools (MACCs etc.)?
def pool_share(rs, label):
    tot = sum(r["obligated"] for r in rs) or 1.0
    by_parent = defaultdict(lambda: [0, 0.0, set()])
    for r in rs:
        if r["is_order"]:
            p = r["parent"]; by_parent[p][0] += 1; by_parent[p][1] += r["obligated"]; by_parent[p][2].add(r["recipient"])
    return {"label": label, "n": len(rs), "obligated_usd": round(tot),
            "pct_usd_via_idv_orders": round(100 * sum(r["obligated"] for r in rs if r["is_order"]) / tot, 1),
            "top_parent_idvs": [(p, v[0], round(v[1]), sorted(v[2])[:4]) for p, v in sorted(by_parent.items(), key=lambda x: -x[1][1])[:8]]}
res["pool_residential_all"] = pool_share(resid, "residential repair (Z1F/Z2F A,C,Z), US")
res["pool_residential_WA"] = pool_share([r for r in resid if r["state"] == "WA"], "residential repair, WA")
res["pool_construction_WA"] = pool_share([r for r in rows if r["state"] == "WA"], "all NAICS 23, WA")
json.dump(res, open(out_path, "w"), indent=1, default=str)
print(json.dumps({k: res[k] for k in ("pool_residential_all", "pool_residential_WA", "pool_construction_WA")}, indent=1, default=str))
