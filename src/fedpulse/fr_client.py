"""Federal Register API v1 client — stdlib urllib only.

Docs: https://www.federalregister.gov/developers/documentation/api/v1
Key quirk: results are capped at 50 pages per query (count is capped at 10000,
total_pages at 50). Date-slice every query so we never exceed that.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.parse
import urllib.request

BASE = "https://www.federalregister.gov/api/v1"
USER_AGENT = "FedPulse/0.1 (regulatory metadata index; contact: michael@fedpulse.local)"
SLEEP = 0.4  # seconds between requests — be a good citizen

FIELDS = [
    "document_number",
    "type",
    "title",
    "publication_date",
    "agencies",
    "topics",
    "citation",
    "html_url",
    "raw_text_url",
    "abstract",
    "action",
    "sections",
    "significant",
    "docket_ids",
]


class FRAPIError(RuntimeError):
    pass


def _get(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    url = f"{BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_range(start: str, end: str, per_page: int = 1000) -> list[dict]:
    """Fetch all FR documents with publication_date in [start, end] (ISO dates).

    Slices by day if a range exceeds the API's 50-page cap.
    """
    out: list[dict] = []
    page = 1
    while True:
        params = {
            "per_page": per_page,
            "page": page,
            "fields[]": FIELDS,
            "conditions[publication_date][gte]": start,
            "conditions[publication_date][lte]": end,
        }
        data = _get("/documents.json", params)
        results = data.get("results", [])
        out.extend(results)
        total_pages = data.get("total_pages", 1)
        if page >= total_pages or page >= 50:
            break
        page += 1
        time.sleep(SLEEP)
    return out


def pull_days(days: int = 3) -> list[dict]:
    """Pull the last N days of FR documents (inclusive of today)."""
    today = dt.date.today()
    start = (today - dt.timedelta(days=days - 1)).isoformat()
    return fetch_range(start, today.isoformat())


def backfill(start: str, end: str | None = None) -> list[dict]:
    """Backfill documents from start to end (ISO dates; default end = today).

    Iterates month-by-month to stay under the 50-page/query cap.
    """
    if end is None:
        end = dt.date.today().isoformat()
    out: list[dict] = []
    cur = dt.date.fromisoformat(start)
    end_date = dt.date.fromisoformat(end)
    while cur <= end_date:
        month_end = min(cur.replace(day=28) + dt.timedelta(days=4), end_date)  # safe month roll
        month_end = month_end.replace(day=1) + dt.timedelta(days=32)
        month_end = (month_end.replace(day=1) - dt.timedelta(days=1)).replace(
            day=min(month_end.day, 31)
        )
        if month_end > end_date:
            month_end = end_date
        chunk = fetch_range(cur.isoformat(), month_end.isoformat())
        out.extend(chunk)
        print(f"  {cur.isoformat()}..{month_end.isoformat()}: {len(chunk)} docs")
        cur = month_end + dt.timedelta(days=1)
        time.sleep(SLEEP)
    return out


def to_record(doc: dict) -> dict:
    """Map an FR API document to FedPulse's records-table dict."""
    agencies = doc.get("agencies") or []
    agency = agencies[0].get("name") if agencies else None
    slug = agencies[0].get("slug") if agencies else None
    doc_type = doc.get("type")
    # normalize type to snake-case tokens used by RCR
    if doc_type:
        doc_type = doc_type.strip().lower().replace(" ", "_").replace("-", "_")
    topics = [t for t in (doc.get("topics") or []) if t]
    abstract = doc.get("abstract") or ""
    action = doc.get("action") or ""
    return {
        "id": f"fr:{doc.get('document_number', '')}",
        "source": "fr",
        "title": doc.get("title"),
        "agency": agency,
        "agency_slug": slug,
        "sudoc": None,
        "sudoc_stem": None,
        "doc_type": doc_type,
        "publication_date": doc.get("publication_date"),
        "cataloged_date": doc.get("publication_date"),
        "url": doc.get("html_url"),
        "subjects": topics,
        "raw_json": {
            "citation": doc.get("citation"),
            "abstract": abstract[:500],
            "action": action[:500],
            "significant": doc.get("significant"),
            "sections": doc.get("sections"),
            "docket_ids": doc.get("docket_ids"),
            "raw_text_url": doc.get("raw_text_url"),
        },
    }
