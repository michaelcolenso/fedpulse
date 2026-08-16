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


def _pick(row: dict, *names: str) -> str | None:
    lowered = {str(k).strip().lower().replace(" ", "").replace("_", ""): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower().replace(" ", "").replace("_", ""))
        if value is not None and str(value).strip(): return str(value).strip()
    return None


def parse_csv(body: bytes, *, max_rows: int | None = None) -> list[GovernmentEvent]:
    digest = hashlib.sha256(body).hexdigest()
    text = body.decode("utf-8-sig", "replace")
    # Some historical extracts have a few metadata lines; locate the real CSV header.
    lines = text.splitlines()
    header_idx = next((i for i, line in enumerate(lines[:20]) if "NoticeId" in line or "Notice ID" in line), 0)
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])))
    out = []
    for idx, row in enumerate(reader):
        if max_rows is not None and idx >= max_rows: break
        notice_id = _pick(row, "NoticeId", "Notice ID", "NoticeID")
        if not notice_id: continue
        solicitation = _pick(row, "Solicitation Number", "SolicitationNumber", "Sol#")
        title = _pick(row, "Title") or "Federal contract opportunity"
        agency = _pick(row, "Department/Ind.Agency", "Department", "Agency", "FullParentPathName")
        posted = _pick(row, "PostedDate", "Posted Date")
        notice_type = _pick(row, "Type", "NoticeType") or "opportunity"
        link = _pick(row, "Link", "AdditionalInfoLink", "UI Link") or f"https://sam.gov/opp/{notice_id}/view"
        naics = _pick(row, "NaicsCode", "NAICS Code")
        identifiers = [("sam_notice", notice_id)]
        if solicitation: identifiers.append(("solicitation", solicitation))
        if naics: identifiers.append(("naics", naics))
        out.append(GovernmentEvent(
            source="sam_opportunity", source_id=notice_id, kind="contract_opportunity", stage=notice_type,
            title=title, agency=agency, event_date=posted, official_url=link,
            identifiers=tuple(identifiers), payload={"source_sha256": digest, "row": row}, content_sha256=digest,
        ))
    return out


def pull_current(*, max_rows: int | None = None) -> tuple[str, str, list[GovernmentEvent]]:
    body = fetch_bytes()
    return BULK_URL, hashlib.sha256(body).hexdigest(), parse_csv(body, max_rows=max_rows)
