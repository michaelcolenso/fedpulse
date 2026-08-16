"""Zero-key Grants.gov enhanced daily XML extract client."""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

from .action_graph import GovernmentEvent

USER_AGENT = "FedPulse/0.4 (public federal government monitoring)"
INDEX_URL = "https://www.grants.gov/xml-extract"
OPPORTUNITY_ELEMENTS = {"opportunitysynopsisdetail10", "opportunityforecastdetail10"}


def fetch_bytes(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def discover_latest_extract(index_html: str) -> str:
    matches = re.findall(r'href=["\']([^"\']*GrantsDBExtract(\d{8})v2\.zip[^"\']*)', index_html, re.I)
    if not matches:
        raise ValueError("no enhanced Grants.gov XML extract found")
    href, _ = max(matches, key=lambda x: x[1])
    return urllib.request.urljoin(INDEX_URL, href.replace("&amp;", "&"))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower().replace("_", "").replace("-", "")


def _flat(node: ET.Element) -> dict[str, str]:
    out = {}
    for child in node.iter():
        if child is node or not child.text or not child.text.strip(): continue
        out.setdefault(_local(child.tag), child.text.strip())
    return out


def _pick(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(name.lower().replace("_", "").replace("-", ""))
        if value: return value
    return None


def _iso_date(value: str | None) -> str | None:
    if not value: return None
    raw = value.strip()
    for fmt in ("%m%d%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try: return dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError: pass
    return raw


def _event_from_row(row: dict[str, str], digest: str) -> GovernmentEvent | None:
    opp_id = _pick(row, "opportunityid")
    title = _pick(row, "opportunitytitle")
    if not (opp_id and title): return None
    opp_no = _pick(row, "opportunitynumber")
    status = _pick(row, "opportunitystatus")
    forecast = bool(_pick(row, "forecastedpostdate", "estimatedpostdate"))
    stage = "forecast" if forecast else (status or "published")
    amount_raw = _pick(row, "estimatedtotalprogramfunding", "awardceiling")
    try: amount = float((amount_raw or "").replace(",", "").replace("$", "")) if amount_raw else None
    except ValueError: amount = None
    cfda = _pick(row, "cfdanumbers", "assistancelistingnumber", "cfda")
    agency = _pick(row, "agencyname", "agencycode")
    raw_date = _pick(row, "postdate", "forecastedpostdate", "estimatedpostdate")
    date = _iso_date(raw_date)
    identifiers = [("grants_opportunity", opp_id)]
    if opp_no: identifiers.append(("opportunity_number", opp_no))
    if cfda:
        for value in re.split(r"[,;\s]+", cfda):
            if value: identifiers.append(("assistance_listing", value))
    payload = {"opportunity_id": opp_id, "opportunity_number": opp_no, "status": status, "cfda": cfda, "event_date_raw": raw_date, "source_sha256": digest, "fields": row}
    return GovernmentEvent(
        source="grants", source_id=opp_id, kind="funding_opportunity", stage=stage,
        title=title, agency=agency, event_date=date, amount=amount, currency="USD" if amount is not None else None,
        official_url=f"https://www.grants.gov/search-results-detail/{opp_id}", identifiers=tuple(identifiers), payload=payload,
        content_sha256=digest,
    )


def parse_extract(zip_bytes: bytes) -> list[GovernmentEvent]:
    """Stream opportunity elements from the large daily archive."""
    digest = hashlib.sha256(zip_bytes).hexdigest()
    events: dict[str, GovernmentEvent] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml") and "schema" not in n.lower()]
        if not xml_names: raise ValueError("Grants.gov ZIP contains no XML data")
        with zf.open(max(xml_names, key=lambda n: zf.getinfo(n).file_size)) as fh:
            for _, node in ET.iterparse(fh, events=("end",)):
                if _local(node.tag) not in OPPORTUNITY_ELEMENTS:
                    continue
                event = _event_from_row(_flat(node), digest)
                if event:
                    prior = events.get(event.source_id)
                    if prior is None or (prior.stage == "forecast" and event.stage != "forecast"):
                        events[event.source_id] = event
                node.clear()
    return list(events.values())


def pull_latest() -> tuple[str, str, list[GovernmentEvent]]:
    index = fetch_bytes(INDEX_URL, 60).decode("utf-8", "replace")
    url = discover_latest_extract(index)
    body = fetch_bytes(url)
    return url, hashlib.sha256(body).hexdigest(), parse_extract(body)
