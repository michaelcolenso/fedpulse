"""Zero-key USAspending award client."""
from __future__ import annotations

import datetime as dt
import json
import urllib.request

from .action_graph import GovernmentEvent

BASE = "https://api.usaspending.gov/api/v2"
USER_AGENT = "FedPulse/0.4 (public federal government monitoring)"
AWARD_TYPE_CODES = ["A", "B", "C", "D", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"]


def post_json(path: str, payload: dict, timeout: int = 90) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=body, method="POST",
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_award(row: dict) -> GovernmentEvent | None:
    award_id = row.get("generated_subaward_id") or row.get("generated_unique_award_id") or row.get("Award ID") or row.get("Award ID")
    if not award_id: return None
    title = row.get("Description") or row.get("description") or row.get("Recipient Name") or "Federal award"
    agency = row.get("Awarding Agency") or row.get("awarding_agency_name")
    date = row.get("Start Date") or row.get("start_date") or row.get("Action Date") or row.get("action_date")
    amount = row.get("Award Amount") if "Award Amount" in row else row.get("award_amount")
    try: amount = float(amount) if amount is not None else None
    except (TypeError, ValueError): amount = None
    cfda = row.get("CFDA Number") or row.get("cfda_number")
    piid = row.get("Award ID") or row.get("piid")
    identifiers = [("award", str(award_id))]
    if piid: identifiers.append(("award", str(piid)))
    if cfda: identifiers.append(("assistance_listing", str(cfda)))
    url = f"https://www.usaspending.gov/award/{award_id}/"
    return GovernmentEvent(
        source="usaspending", source_id=str(award_id), kind="federal_award", stage="awarded",
        title=title, agency=agency, event_date=date, amount=amount, currency="USD" if amount is not None else None,
        official_url=url, identifiers=tuple(identifiers), payload=row,
    )


def pull_recent_awards(days: int = 3, *, today: dt.date | None = None, page_limit: int = 25) -> list[GovernmentEvent]:
    today = today or dt.date.today()
    start = today - dt.timedelta(days=max(days, 1) - 1)
    fields = ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency", "Start Date", "Description", "CFDA Number"]
    out = []
    page = 1
    while page <= page_limit:
        payload = {
            "filters": {
                "time_period": [{"start_date": start.isoformat(), "end_date": today.isoformat()}],
                "award_type_codes": AWARD_TYPE_CODES,
            },
            "fields": fields,
            "page": page,
            "limit": 100,
            "subawards": False,
        }
        data = post_json("/search/spending_by_award/", payload)
        rows = data.get("results") or []
        for row in rows:
            event = normalize_award(row)
            if event: out.append(event)
        page_meta = data.get("page_metadata") or {}
        if not rows or not page_meta.get("hasNext", False): break
        page += 1
    return out
