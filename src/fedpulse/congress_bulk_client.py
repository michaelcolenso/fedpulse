"""Zero-key Congressional Bill Status client using GovInfo bulk JSON directory listings + XML."""
from __future__ import annotations

import datetime as dt
import json
import urllib.request
import xml.etree.ElementTree as ET

from .action_graph import GovernmentEvent

USER_AGENT = "FedPulse/0.4 (public federal government monitoring)"
CURRENT_CONGRESS = 119
BULK_JSON_ROOT = f"https://www.govinfo.gov/bulkdata/json/BILLSTATUS/{CURRENT_CONGRESS}"


def fetch_bytes(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_json(url: str, timeout: int = 90) -> dict:
    return json.loads(fetch_bytes(url, timeout).decode("utf-8"))


def _modified(item: dict) -> dt.datetime:
    value = item.get("formattedLastModifiedTime") or ""
    for fmt in ("%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try: return dt.datetime.strptime(value, fmt)
        except ValueError: pass
    return dt.datetime.min


def recent_bill_urls(max_files: int = 100, congress: int = CURRENT_CONGRESS) -> list[str]:
    """Discover recently modified Bill Status XML files from GovInfo's public JSON bulk directory."""
    root_url = f"https://www.govinfo.gov/bulkdata/json/BILLSTATUS/{congress}"
    root = fetch_json(root_url)
    files = []
    for folder in root.get("files") or []:
        if not folder.get("folder"): continue
        folder_url = folder.get("link") or f"{root_url}/{folder.get('name')}"
        try:
            listing = fetch_json(folder_url)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for item in listing.get("files") or []:
            name = str(item.get("name") or item.get("justFileName") or "")
            if item.get("folder") or not name.lower().endswith(".xml"): continue
            link = item.get("link") or ""
            if not link: continue
            # JSON-directory links can point at the JSON representation; the raw
            # Bill Status XML lives at the same path without /json/.
            raw_link = link.replace("/bulkdata/json/", "/bulkdata/")
            files.append((_modified(item), raw_link))
    files.sort(key=lambda x: x[0], reverse=True)
    return [url for _, url in files[:max_files]]


def _text(node: ET.Element, path: str) -> str | None:
    found = node.find(path)
    return found.text.strip() if found is not None and found.text and found.text.strip() else None


def _all_text(node: ET.Element, suffix: str) -> list[str]:
    out = []
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1].lower() == suffix.lower() and child.text and child.text.strip():
            out.append(child.text.strip())
    return out


def parse_bill(xml_bytes: bytes, url: str) -> GovernmentEvent | None:
    root = ET.fromstring(xml_bytes)
    found_bill = root.find(".//bill")
    bill = found_bill if found_bill is not None else root
    congress = _text(bill, "congress") or next(iter(_all_text(bill, "congress")), None)
    bill_type = _text(bill, "type") or next(iter(_all_text(bill, "type")), None)
    number = _text(bill, "number") or next(iter(_all_text(bill, "number")), None)
    if not (congress and bill_type and number): return None
    bill_key = f"{congress}:{bill_type.lower()}:{number}"
    titles = _all_text(bill, "title")
    title = titles[0] if titles else bill_key
    introduced = _text(bill, "introducedDate") or next(iter(_all_text(bill, "introducedDate")), None)
    action_dates = _all_text(bill, "actionDate")
    action_texts = _all_text(bill, "text")
    event_date = max(action_dates) if action_dates else introduced
    latest_action = action_texts[-1] if action_texts else None
    laws = _all_text(bill, "lawNumber")
    stage = "enacted" if laws else (latest_action or "introduced")
    identifiers = [("bill", bill_key)]
    for law in laws: identifiers.append(("public_law", law))
    payload = {"congress": congress, "type": bill_type, "number": number, "introduced_date": introduced, "latest_action": latest_action, "laws": laws}
    return GovernmentEvent(
        source="bill_status", source_id=bill_key, kind="legislation", stage=stage,
        title=title, agency="United States Congress", event_date=event_date, official_url=url,
        identifiers=tuple(identifiers), payload=payload,
    )


def pull_recent_updates(max_files: int = 100) -> list[GovernmentEvent]:
    urls = recent_bill_urls(max_files=max_files)
    out = []
    for url in urls:
        try:
            event = parse_bill(fetch_bytes(url), url)
        except (ET.ParseError, OSError, ValueError):
            continue
        if event: out.append(event)
    return out
