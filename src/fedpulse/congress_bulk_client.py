"""Zero-key congressional Bill Status client using GovInfo bulk XML + RSS."""
from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET

from .action_graph import GovernmentEvent

USER_AGENT = "FedPulse/0.4 (public federal government monitoring)"
RSS_URL = "https://www.govinfo.gov/rss/billstatus-batch.xml"


def fetch_bytes(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def updated_bill_urls(rss_bytes: bytes, max_files: int = 200) -> list[str]:
    text = rss_bytes.decode("utf-8", "replace")
    urls = re.findall(r"https://www\.govinfo\.gov/bulkdata/BILLSTATUS/\d+/[a-z]+/BILLSTATUS-[^\s<&\"']+\.xml", html.unescape(text), re.I)
    return list(dict.fromkeys(urls))[:max_files]


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
    bill = root.find(".//bill") or root
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
    urls = updated_bill_urls(fetch_bytes(RSS_URL), max_files=max_files)
    out = []
    for url in urls:
        try:
            event = parse_bill(fetch_bytes(url), url)
        except (ET.ParseError, OSError, ValueError):
            continue
        if event: out.append(event)
    return out
