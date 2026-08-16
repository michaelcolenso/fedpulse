"""Minimal Regulations.gov v4 GET client (stdlib only)."""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from typing import Iterable

BASE = "https://api.regulations.gov/v4"
USER_AGENT = "FedPulse/0.4 (federal evidence intelligence)"
RETRYABLE = {429, 500, 502, 503, 504}


class RegulationsAPIError(RuntimeError):
    pass


def _get(path: str, params: dict, api_key: str, *, attempts: int = 4) -> dict:
    qs = urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(
        f"{BASE}{path}?{qs}",
        headers={"User-Agent": USER_AGENT, "X-Api-Key": api_key},
    )
    last = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last = exc
            status = getattr(exc, "code", None)
            if status not in RETRYABLE or attempt == attempts - 1:
                break
            time.sleep(min(2 ** attempt, 8))
    raise RegulationsAPIError(str(last)) from last


def fetch_documents(start: str, end: str, api_key: str, *, page_size: int = 250) -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        payload = _get(
            "/documents",
            {
                "filter[postedDate][ge]": start,
                "filter[postedDate][le]": end,
                "page[size]": page_size,
                "page[number]": page,
                "sort": "postedDate,documentId",
            },
            api_key,
        )
        rows = payload.get("data") or []
        out.extend(rows)
        meta = payload.get("meta") or {}
        total_pages = meta.get("totalPages") or meta.get("total_pages")
        if not rows or (total_pages and page >= int(total_pages)) or len(rows) < page_size:
            break
        page += 1
    return out


def fetch_docket(docket_id: str, api_key: str) -> dict:
    return _get(f"/dockets/{urllib.parse.quote(docket_id, safe='')}", {}, api_key)


def pull_days(api_key: str, days: int = 7, *, today: dt.date | None = None) -> list[dict]:
    today = today or dt.date.today()
    start = (today - dt.timedelta(days=max(days, 1) - 1)).isoformat()
    return fetch_documents(start, today.isoformat(), api_key)


def normalize_document(item: dict) -> dict:
    attrs = item.get("attributes") or {}
    document_id = item.get("id") or attrs.get("documentId")
    docket_id = attrs.get("docketId")
    return {
        "document_id": document_id,
        "docket_id": docket_id,
        "agency_id": attrs.get("agencyId"),
        "document_type": attrs.get("documentType"),
        "title": attrs.get("title"),
        "posted_date": attrs.get("postedDate"),
        "last_modified_date": attrs.get("lastModifiedDate"),
        "comment_end_date": attrs.get("commentEndDate"),
        "withdrawn": bool(attrs.get("withdrawn")),
        "object_id": attrs.get("objectId"),
        "fr_doc_number": attrs.get("frDocNum") or attrs.get("frDocNumber"),
        "raw_json": item,
    }
