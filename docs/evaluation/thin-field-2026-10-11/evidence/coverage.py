"""Coverage: how many currently open SAM construction notices can get a forecast from FPDS history?

History = robust.py's unit: competed standalone procurements (no IDV orders, no IDV base awards,
no non-competed / NOT AVAILABLE), base date FY2023-2025, offers 1..998, one per office+solicitation.
Keyed by SAM 'AAC Code' == FPDS awarding_office_code and SAM ClassificationCode == FPDS PSC.

Reports both notice postings (amendments/reposts count separately) and unique solicitations
(Sol# upper-cased; the latest posting wins).

Usage: python3 -I coverage.py <fpds_contracts.csv> <sam_ContractOpportunitiesFullCSV.csv> <YYYY-MM-DD> [out.json]
"""
import csv, json, statistics, sys
from collections import defaultdict

csv.field_size_limit(10**9)
fpds_path, sam_path, today = sys.argv[1], sys.argv[2], sys.argv[3]
out_path = sys.argv[4] if len(sys.argv) > 4 else None


def fy(d):
    y, m = int(d[:4]), int(d[5:7])
    return y + 1 if m >= 10 else y


hist = defaultdict(dict); hist_office = defaultdict(dict)
for r in csv.DictReader(open(fpds_path, newline="", encoding="utf-8")):
    d = r["award_base_action_date"][:10]
    if len(d) < 10 or not (2023 <= fy(d) <= 2025): continue
    if r["parent_award_id_piid"].strip() or r["contract_award_unique_key"].startswith("CONT_IDV_"): continue
    c = r["extent_competed"].upper()
    if not c or "NOT COMPETED" in c or "NOT AVAILABLE" in c: continue
    try: o = float(r["number_of_offers_received"])
    except ValueError: continue
    if o <= 0 or o >= 999: continue
    k = r["solicitation_identifier"].strip().upper() or r["contract_award_unique_key"]
    hist[(r["awarding_office_code"], r["product_or_service_code"][:4])][k] = o
    hist_office[r["awarding_office_code"]][k] = o

OPEN_TYPES = {"Solicitation", "Combined Synopsis/Solicitation", "Presolicitation", "Sources Sought"}
BID_TYPES = {"Solicitation", "Combined Synopsis/Solicitation"}
postings = []
for r in csv.DictReader(open(sam_path, newline="", encoding="utf-8", errors="replace")):
    if r["Active"] != "Yes" or r["Type"] not in OPEN_TYPES: continue
    dl = (r["ResponseDeadLine"] or "")[:10]
    if not dl or dl < today: continue
    naics, psc = (r["NaicsCode"] or "").strip(), (r["ClassificationCode"] or "").strip()[:4]
    if not (naics.startswith("23") or psc[:1] in ("Y", "Z")): continue
    h, ho = hist.get((r["AAC Code"], psc), {}), hist_office.get(r["AAC Code"], {})
    # Forecast from office x PSC history when it has >=3 procurements, else fall back to the office's history.
    level, src = ("office_psc", h) if len(h) >= 3 else (("office", ho) if len(ho) >= 3 else (None, {}))
    postings.append({"sol": (r["Sol#"] or r["NoticeId"]).strip().upper(), "posted": r["PostedDate"], "type": r["Type"],
                     "title": r["Title"], "office": r["Office"], "aac": r["AAC Code"], "psc": psc, "deadline": dl,
                     "pop_state": r["PopState"], "setaside": r["SetASide"], "level": level,
                     "n_prior": len(src), "median": statistics.median(src.values()) if src else None,
                     "pct_single": round(100 * sum(v == 1 for v in src.values()) / len(src)) if src else None})

latest = {}
for p in postings:
    if p["sol"] not in latest or p["posted"] > latest[p["sol"]]["posted"]: latest[p["sol"]] = p
uniq = list(latest.values()); bids = [p for p in uniq if p["type"] in BID_TYPES]


def levels(ps):
    n = len(ps); a = sum(p["level"] == "office_psc" for p in ps); b = sum(p["level"] == "office" for p in ps)
    return {"n": n, "office_psc": a, "office_psc_pct": round(100 * a / n, 1), "office_only": b, "any_pct": round(100 * (a + b) / n, 1)}


def split(ps):
    return {"le2": sum(p["median"] <= 2 for p in ps), "between": sum(2 < p["median"] < 5 for p in ps), "ge5": sum(p["median"] >= 5 for p in ps)}


scored = [p for p in bids if p["median"] is not None]
out = {
    "postings": levels(postings),
    "unique_solicitations": levels(uniq),
    "unique_bid_solicitations": levels(bids),
    "bid_forecast_split_by_level": {lvl: split([p for p in scored if p["level"] == lvl]) for lvl in ("office_psc", "office")},
    "thin_bids": sorted(({k: p[k] for k in ("sol", "title", "office", "aac", "psc", "deadline", "pop_state", "setaside", "level", "n_prior", "median", "pct_single")}
                         for p in scored if p["median"] <= 2), key=lambda x: (x["level"] != "office_psc", x["median"], -x["n_prior"])),
}
print(json.dumps({k: v for k, v in out.items() if k != "thin_bids"}, indent=1))
print(f"{len(out['thin_bids'])} thin bids; first 5:")
for t in out["thin_bids"][:5]: print(" ", t["sol"], t["median"], t["n_prior"], t["pct_single"], t["title"][:60])
if out_path: json.dump(out, open(out_path, "w"), indent=1)
