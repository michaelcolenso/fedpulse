"""Keyless OIRA EO 12866 meeting ingestion keyed by RIN.

RegInfo's machine-readable meeting exports currently lag the live meeting calendar,
so FedPulse queries the official public meeting search for RINs it already tracks.
"""
from __future__ import annotations

import hashlib
import html
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .action_graph import GovernmentEvent

USER_AGENT = "FedPulse/0.4 (public federal government monitoring)"
SEARCH_URL = "https://www.reginfo.gov/public/do/eom12866SearchResults?rin={rin}"
DETAIL_BASE = "https://www.reginfo.gov/public/do/"


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a": return
        href = dict(attrs).get("href")
        if href: self.links.append(href)


def fetch_text(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def detail_urls(search_html: str) -> list[str]:
    parser = _Links(); parser.feed(search_html)
    urls = []
    for href in parser.links:
        if "viewEO12866Meeting" not in href or "meetingId=" not in href: continue
        urls.append(urllib.parse.urljoin(DETAIL_BASE, html.unescape(href)))
    return sorted(set(urls))


def _field(text: str, label: str, next_labels: tuple[str, ...]) -> str | None:
    tail = "|".join(re.escape(x) for x in next_labels)
    m = re.search(rf"{re.escape(label)}\s*:\s*(.*?)(?=(?:{tail})\s*:|$)", text, re.I | re.S)
    if not m: return None
    return re.sub(r"\s+", " ", m.group(1)).strip(" -\n\t") or None


def parse_detail(page: str, url: str) -> GovernmentEvent | None:
    # Strip tags while preserving enough label text for deterministic extraction.
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.I | re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text)
    rin = _field(text, "RIN", ("Title", "Agency/Subagency", "Stage of Rulemaking", "Meeting Date/Time"))
    meeting_id = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("meetingId", [None])[0]
    if not meeting_id or not rin:
        return None
    title = _field(text, "Title", ("Agency/Subagency", "Stage of Rulemaking", "Meeting Date/Time"))
    agency = _field(text, "Agency/Subagency", ("Stage of Rulemaking", "Meeting Date/Time"))
    stage = _field(text, "Stage of Rulemaking", ("Meeting Date/Time", "Requestor"))
    date = _field(text, "Meeting Date/Time", ("Requestor", "Documents", "Attendees"))
    requestor = _field(text, "Requestor", ("Requestor's Name", "Documents", "Attendees"))
    payload = {"rin": rin, "meeting_id": meeting_id, "stage": stage, "requestor": requestor, "source_sha256": hashlib.sha256(page.encode()).hexdigest()}
    return GovernmentEvent(
        source="oira_meeting", source_id=meeting_id, kind="stakeholder_meeting", stage=stage,
        title=title, agency=agency, event_date=date, official_url=url,
        identifiers=(("rin", rin), ("oira_meeting", meeting_id)), payload=payload,
    )


def pull_for_rin(rin: str, *, max_meetings: int = 100) -> list[GovernmentEvent]:
    search = SEARCH_URL.format(rin=urllib.parse.quote(rin))
    urls = detail_urls(fetch_text(search))[:max_meetings]
    out = []
    for url in urls:
        event = parse_detail(fetch_text(url), url)
        if event: out.append(event)
    return out
