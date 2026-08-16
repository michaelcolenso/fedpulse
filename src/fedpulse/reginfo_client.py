"""Keyless RegInfo.gov XML client for OIRA and Unified Agenda data."""
from __future__ import annotations

import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

USER_AGENT = "FedPulse/0.4 (public federal regulatory monitoring)"
OIRA_PENDING_URL = "https://www.reginfo.gov/public/do/XMLViewFileAction?f=EO_RULES_UNDER_REVIEW.xml"
OIRA_COMPLETED_30_URL = "https://www.reginfo.gov/public/do/XMLViewFileAction?f=EO_RULE_COMPLETED_30_DAYS.xml"
UNIFIED_AGENDA_2026_URL = "https://www.reginfo.gov/public/do/XMLViewFileAction?f=REGINFO_RIN_DATA_202510.xml"


class RegInfoError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegInfoDocument:
    source: str
    source_url: str
    rin: str | None
    title: str | None
    agency: str | None
    stage: str | None
    status: str | None
    received_date: str | None
    concluded_date: str | None
    publication_date: str | None
    raw_sha256: str


def fetch_xml(url: str, *, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except Exception as exc:
        raise RegInfoError(f"failed to fetch RegInfo XML: {exc}") from exc
    if not body.lstrip().startswith(b"<"):
        raise RegInfoError("RegInfo response is not XML")
    return body


def _text(node: ET.Element, *names: str) -> str | None:
    wanted = {n.lower().replace("_", "") for n in names}
    for child in node.iter():
        tag = child.tag.rsplit("}", 1)[-1].lower().replace("_", "")
        if tag in wanted and child.text and child.text.strip():
            return child.text.strip()
    return None


def _candidate_records(root: ET.Element) -> list[ET.Element]:
    rows = []
    for node in root.iter():
        rin = _text(node, "RIN")
        title = _text(node, "TITLE", "RuleTitle")
        if rin and title:
            rows.append(node)
    unique: list[ET.Element] = []
    seen = set()
    for node in rows:
        key = (_text(node, "RIN"), _text(node, "TITLE", "RuleTitle"), _text(node, "RECEIVED_DATE", "ReceivedDate"))
        if key not in seen:
            seen.add(key); unique.append(node)
    return unique


def parse_oira(xml_bytes: bytes, *, source: str, source_url: str) -> list[RegInfoDocument]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise RegInfoError(f"invalid RegInfo XML: {exc}") from exc
    digest = hashlib.sha256(xml_bytes).hexdigest()
    out = []
    for node in _candidate_records(root):
        out.append(RegInfoDocument(
            source=source,
            source_url=source_url,
            rin=_text(node, "RIN"),
            title=_text(node, "TITLE", "RuleTitle"),
            agency=_text(node, "AGENCY", "AgencyName", "Agency", "Department"),
            stage=_text(node, "STAGE", "Stage", "RuleStage", "AgendaStageOfRulemaking"),
            status=_text(node, "STATUS", "Status", "ConcludedAction", "TimetableAction"),
            received_date=_text(node, "RECEIVED_DATE", "ReceivedDate"),
            concluded_date=_text(node, "CONCLUDED_DATE", "ConcludedDate"),
            publication_date=_text(node, "PUBLICATION_DATE", "PublicationDate", "FRPublicationDate"),
            raw_sha256=digest,
        ))
    return out


def pull_oira_pending() -> list[RegInfoDocument]:
    body = fetch_xml(OIRA_PENDING_URL)
    return parse_oira(body, source="oira_pending", source_url=OIRA_PENDING_URL)


def pull_oira_completed_30() -> list[RegInfoDocument]:
    body = fetch_xml(OIRA_COMPLETED_30_URL)
    return parse_oira(body, source="oira_completed_30", source_url=OIRA_COMPLETED_30_URL)


def pull_unified_agenda() -> list[RegInfoDocument]:
    body = fetch_xml(UNIFIED_AGENDA_2026_URL, timeout=180)
    return parse_oira(body, source="unified_agenda", source_url=UNIFIED_AGENDA_2026_URL)
