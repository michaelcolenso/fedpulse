"""Zero-key SAM.gov Contract Opportunities bulk CSV client."""
from __future__ import annotations

import csv
import hashlib
import io
import urllib.request

from .action_graph import GovernmentEvent

USER_AGENT = "FedPulse/0.4 (public federal government monitoring)"
BULK_URL = "https://sam.gov/api/prod/fileextractservices/v1/api/download/Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv?privacy=Public"


def fetch_bytes(url: str = BULK_URL, timeout: int = 240) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _norm_key(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def _pick(row: dict, *names: str) -> str | None:
    lowered = {_norm_key(k): v for k, v in row.items()}
    for name in names:
        value = lowered.get(_norm_key(name))
        if value is not None and str(value).strip(): return str(value).strip()
    return None


def _scoring_row(row: dict) -> dict:
    """Remove contracting-office geography while preserving place of performance.

    SAM's bulk extract contains both office-address location fields and Pop*/place-of-
    performance fields. Generic City/State/Address values describe the contracting
    office and must not be treated as project geography by downstream ranking.
    """
    out = {}
    location_tokens = ("state", "city", "county", "location", "place", "address", "performance", "worksite")
    for key, value in row.items():
        norm = _norm_key(key)
        is_locationish = any(token in norm for token in location_tokens)
        is_performance = norm.startswith("pop") or "placeofperformance" in norm or "performance" in norm
        if is_locationish and not is_performance:
            continue
        out[key] = value
    return out


def _amount(value: str | None) -> float | None:
    if not value: return None
    try: return float(value.replace("$", "").replace(",", "").strip())
    except ValueError: return None


def parse_csv(body: bytes, *, max_rows: int | None = None) -> list[GovernmentEvent]:
    digest = hashlib.sha256(body).hexdigest()
    text = body.decode("utf-8-sig", "replace")
    lines = text.splitlines()
    header_idx = next((i for i, line in enumerate(lines[:20]) if "NoticeId" in line or "Notice ID" in line), 0)
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])))
    out = []
    for idx, row in enumerate(reader):
        if max_rows is not None and idx >= max_rows: break
        notice_id = _pick(row, "NoticeId", "Notice ID", "NoticeID")
        if not notice_id: continue
        solicitation = _pick(row, "Solicitation Number", "SolicitationNumber", "Sol#")
        award_number = _pick(row, "AwardNumber", "Award Number")
        title = _pick(row, "Title") or "Federal contract opportunity"
        agency = _pick(row, "Department/Ind.Agency", "Department", "Agency", "FullParentPathName")
        posted = _pick(row, "PostedDate", "Posted Date")
        notice_type = _pick(row, "Type", "NoticeType") or "opportunity"
        link = _pick(row, "Link", "AdditionalInfoLink", "UI Link") or f"https://sam.gov/opp/{notice_id}/view"
        naics = _pick(row, "NaicsCode", "NAICS Code")
        amount = _amount(_pick(row, "Award$", "Award Amount", "AwardAmount"))
        identifiers = [("sam_notice", notice_id)]
        if solicitation: identifiers.append(("solicitation", solicitation))
        if award_number: identifiers.append(("award", award_number))
        if naics: identifiers.append(("naics", naics))
        out.append(GovernmentEvent(
            source="sam_opportunity", source_id=notice_id, kind="contract_opportunity", stage=notice_type,
            title=title, agency=agency, event_date=posted, amount=amount,
            currency="USD" if amount is not None else None, official_url=link,
            identifiers=tuple(identifiers), payload={"source_sha256": digest, "row": _scoring_row(row)}, content_sha256=digest,
        ))
    return out


def pull_current(*, max_rows: int | None = None) -> tuple[str, str, list[GovernmentEvent]]:
    body = fetch_bytes()
    return BULK_URL, hashlib.sha256(body).hexdigest(), parse_csv(body, max_rows=max_rows)
