"""Zero-key USAspending transaction client.

The search window is transaction-oriented: an old award can have new obligations or
other modifications today. FedPulse therefore persists the observed transaction
amount/date instead of mislabeling the award's original start date as recent activity.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import urllib.error
import urllib.request

from .action_graph import GovernmentEvent

BASE = "https://api.usaspending.gov/api/v2"
USER_AGENT = "FedPulse/0.4 (public federal government monitoring)"
# USAspending validates award types by category. Keep every request inside one
# current API category rather than mixing assistance families.
AWARD_TYPE_GROUPS = [
    ["A", "B", "C", "D"],                                      # contracts
    ["02", "03", "04", "05", "F001", "F002"],                # grants/cooperative agreements
    ["07", "08", "F003", "F004"],                            # loans
    ["06", "10"],                                               # direct payments
    ["09", "11"],                                               # other financial assistance
    ["IDV_A", "IDV_B", "IDV_B_A", "IDV_B_B", "IDV_B_C", "IDV_C", "IDV_D", "IDV_E"],
]


def post_json(path: str, payload: dict, timeout: int = 90) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=body, method="POST",
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        raise RuntimeError(f"USAspending HTTP {exc.code}: {detail}") from exc


def normalize_award(row: dict) -> GovernmentEvent | None:
    """Legacy award-level normalizer retained for compatibility/tests."""
    award_id = row.get("generated_subaward_id") or row.get("generated_unique_award_id") or row.get("Award ID")
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
    if piid and str(piid) != str(award_id): identifiers.append(("award", str(piid)))
    if cfda: identifiers.append(("assistance_listing", str(cfda)))
    return GovernmentEvent(
        source="usaspending", source_id=str(award_id), kind="federal_award", stage="awarded",
        title=title, agency=agency, event_date=date, amount=amount, currency="USD" if amount is not None else None,
        official_url=f"https://www.usaspending.gov/award/{award_id}/", identifiers=tuple(identifiers), payload=row,
    )


def normalize_transaction(row: dict) -> GovernmentEvent | None:
    award_id = row.get("Award ID")
    action_date = row.get("Action Date")
    if not award_id or not action_date:
        return None
    amount_raw = row.get("Transaction Amount")
    try: amount = float(amount_raw) if amount_raw is not None else None
    except (TypeError, ValueError): amount = None
    mod = str(row.get("Mod") or "")
    seed = json.dumps(
        [award_id, mod, action_date, amount_raw, row.get("Recipient Name"), row.get("Award Type")],
        separators=(",", ":"), ensure_ascii=False,
    ).encode()
    tx_id = hashlib.sha256(seed).hexdigest()[:24]
    title = row.get("Recipient Name") or f"Federal award transaction {award_id}"
    payload = dict(row)
    payload["award_id"] = award_id
    return GovernmentEvent(
        source="usaspending", source_id=f"tx:{tx_id}", kind="federal_award_action", stage="transaction",
        title=title, agency=row.get("Awarding Agency"), event_date=action_date,
        amount=amount, currency="USD" if amount is not None else None,
        official_url=f"https://www.usaspending.gov/award/{award_id}/",
        identifiers=(("award", str(award_id)),), payload=payload,
    )


def pull_recent_awards(days: int = 3, *, today: dt.date | None = None, page_limit: int = 25) -> list[GovernmentEvent]:
    """Return recent award transactions; name retained for caller compatibility."""
    today = today or dt.date.today()
    start = today - dt.timedelta(days=max(days, 1) - 1)
    fields = ["Award ID", "Mod", "Recipient Name", "Action Date", "Transaction Amount", "Awarding Agency", "Award Type"]
    by_id: dict[str, GovernmentEvent] = {}
    for award_codes in AWARD_TYPE_GROUPS:
        page = 1
        while page <= page_limit:
            payload = {
                "filters": {
                    "time_period": [{"start_date": start.isoformat(), "end_date": today.isoformat()}],
                    "award_type_codes": award_codes,
                },
                "fields": fields,
                "page": page,
                "limit": 100,
                "sort": "Award ID",
                "order": "desc",
                "subawards": False,
            }
            data = post_json("/search/spending_by_transaction/", payload)
            rows = data.get("results") or []
            for row in rows:
                event = normalize_transaction(row)
                if event: by_id[event.event_id] = event
            page_meta = data.get("page_metadata") or {}
            if not rows or not page_meta.get("hasNext", False): break
            page += 1
    return list(by_id.values())
