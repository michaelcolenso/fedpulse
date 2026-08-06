"""MARC record parsers — MARCXML (stdlib ElementTree) and binary MARC21 UTF-8 (.mrc).

Extracts only the high-signal fields FedPulse needs:
  - 001/010  record number
  - 245      title
  - 086      SuDoc call number (stem = top-level class)
  - 110/710  corporate author (agency)
  - 650      Library of Congress subject headings (TER input)
  - 655      genre (e.g. "Legislative hearings")
  - 856      URL (PURL)
  - 005/008  dates (cataloged + publication)
  - Leader   record type
"""
from __future__ import annotations

import re
from xml.etree import ElementTree as ET

MARC_NS = "http://www.loc.gov/MARC21/slim"
_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_SUDOC_RE = re.compile(r"^([A-Z]{1,5}\d{0,2})")
_TRAIL_PUNCT = re.compile(r"[,\s;:/]+$")

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

# ---------------------------------------------------------------------------
# MARCXML
# ---------------------------------------------------------------------------

def _parse_datafield(el: ET.Element) -> tuple[str, str, list[tuple[str, str]]]:
    tag = el.attrib.get("tag", "")
    inds = (el.attrib.get("ind1", " ") + el.attrib.get("ind2", " ")).replace("#", " ")
    subs = [(sf.attrib.get("code", ""), (sf.text or "")) for sf in el if _local(sf.tag) == "subfield"]
    return tag, inds, subs

def parse_marcxml(data: str | bytes) -> list[dict]:
    """Parse MARCXML string/bytes. Handles a single <record> or a <collection>."""
    # XXE guard: these files come from GPO (trusted), but reject DTD/entity
    # declarations anyway — cheap defense against entity-expansion bombs.
    text = data if isinstance(data, str) else data.decode("utf-8", "replace")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("MARCXML contains DTD/entity declarations; refusing to parse")
    root = ET.fromstring(text)
    out: list[dict] = []
    if _local(root.tag) == "record":
        nodes = [root]
    elif _local(root.tag) == "collection":
        nodes = [r for r in root if _local(r.tag) == "record"]
    else:
        nodes = []
    for rec in nodes:
        fields = []
        for el in rec:
            tag = _local(el.tag)
            if tag == "controlfield":
                fields.append((el.attrib.get("tag", ""), el.text or ""))
            elif tag == "datafield":
                fields.append(_parse_datafield(el))
        out.append({"fields": fields})
    return out

# ---------------------------------------------------------------------------
# Binary MARC21 (UTF-8 .mrc)
# ---------------------------------------------------------------------------

def parse_marc_binary(data: bytes) -> list[dict]:
    """Parse one or more binary MARC21 records (each self-delimiting by leader length)."""
    records: list[dict] = []
    pos = 0
    while pos < len(data):
        leader = data[pos : pos + 24]
        if len(leader) < 24 or not leader[:5].isdigit():
            break
        rec_len = int(leader[:5])
        if rec_len <= 0 or pos + rec_len > len(data):
            break
        chunk = data[pos : pos + rec_len]
        pos += rec_len
        records.append(_parse_one_binary(leader, chunk))
    return records

def _parse_one_binary(leader: bytes, chunk: bytes) -> dict:
    base_addr = int(leader[12:17])
    n_fields = (base_addr - 24) // 12
    directory = chunk[24:base_addr]
    fields: list = []
    for i in range(0, len(directory) - 11, 12):
        entry = directory[i : i + 12]
        tag = entry[0:3].decode("ascii", "replace")
        f_len = int(entry[3:7])
        f_start = int(entry[7:12])
        # MARC21: directory offsets are relative to the base address of the data
        fdata = chunk[base_addr + f_start : base_addr + f_start + f_len]
        try:
            tag_num = int(tag)
        except ValueError:
            tag_num = 99
        if tag_num < 10:  # control field
            text = fdata.rstrip(b"\x1e").decode("utf-8", "replace")
            fields.append((tag, text))
        else:
            ind1 = fdata[0:1].decode("ascii", "replace")
            ind2 = fdata[1:2].decode("ascii", "replace")
            subs = fdata[2:]
            subfields: list[tuple[str, str]] = []
            p = 0
            while p < len(subs):
                if subs[p] == 0x1F and p + 1 < len(subs):
                    code = chr(subs[p + 1])
                    p += 2
                    end = p
                    while end < len(subs) and subs[end] not in (0x1F, 0x1E):
                        end += 1
                    val = subs[p:end].decode("utf-8", "replace")
                    subfields.append((code, val))
                    p = end
                else:
                    p += 1
            fields.append((tag, ind1 + ind2, subfields))
    return {"fields": fields}

# ---------------------------------------------------------------------------
# Record normalization
# ---------------------------------------------------------------------------

def _subfields(subs: list[tuple[str, str]], codes: str) -> list[str]:
    return [v for c, v in subs if c in codes and v.strip()]

def _first_subs(subs: list[tuple[str, str]], codes: str) -> str | None:
    vals = _subfields(subs, codes)
    return vals[0].strip() if vals else None

def _first_field(data: dict[str, list[list[tuple[str, str]]]], tag: str) -> list[tuple[str, str]]:
    fields = data.get(tag, [])
    return fields[0] if fields else []

def normalize_record(parsed: dict) -> dict | None:
    """Map a parsed MARC record to FedPulse's record dict."""
    ctl: dict[str, str] = {}
    data: dict[str, list[list[tuple[str, str]]]] = {}
    for f in parsed["fields"]:
        if len(f) == 2:
            tag, text = f
            ctl[tag] = text
        else:
            tag, _inds, subs = f
            data.setdefault(tag, []).append(subs)

    rec_id = ctl.get("001") or _first_subs(_first_field(data, "010"), "a") or ""
    if not rec_id:
        return None

    # title: 245, drop nonfiling chars (indicator2)
    title = None
    if data.get("245"):
        subs = data["245"][0]
        parts = [v for c, v in subs if c in "ab" and v.strip()]
        title = (" ".join(parts)).strip() if parts else None
        if title:
            title = _TRAIL_PUNCT.sub("", title)

    # SuDoc: 086 $a
    sudoc = _first_subs(_first_field(data, "086"), "a")
    sudoc_stem = None
    if sudoc:
        m = _SUDOC_RE.match(sudoc.strip())
        if m:
            sudoc_stem = m.group(1)

    # agency: 110 $a, else first 710 $a
    agency = _first_subs(_first_field(data, "110"), "a") or _first_subs(_first_field(data, "710"), "a")
    if agency:
        agency = _TRAIL_PUNCT.sub("", agency)

    # subjects: 650 full heading strings (a--x--y--z--v)
    subjects = []
    for subs in data.get("650", []):
        vals = [v for c, v in subs if c in "axyzv" and v.strip()]
        if vals:
            subjects.append("--".join(v.strip() for v in vals))

    genre = []
    for subs in data.get("655", []):
        g = _first_subs(subs, "a")
        if g:
            genre.append(_TRAIL_PUNCT.sub("", g))

    # URL: 856 $u
    url = _first_subs(_first_field(data, "856"), "u")

    # dates
    leader = ctl.get("LEADER", "")
    f008 = ctl.get("008", "")
    cataloged_date = None
    if len(f008) >= 6 and f008[:6].isdigit():
        yy = int(f008[:2])
        cataloged_date = f"{(1900 + yy) if yy >= 90 else (2000 + yy)}-{f008[2:4]}-{f008[4:6]}"
    elif len(ctl.get("005", "")) >= 8 and ctl["005"][:8].isdigit():
        d = ctl["005"][:8]
        cataloged_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    publication_date = None
    if len(f008) >= 11:
        y1 = f008[7:11]
        if y1.isdigit() and 1500 <= int(y1) <= 2100:
            publication_date = f"{y1}-01-01"
    if not publication_date:
        for tag in ("260", "264"):
            for subs in data.get(tag, []):
                c_val = _first_subs(subs, "c")
                if c_val:
                    m = _YEAR_RE.search(c_val)
                    if m:
                        publication_date = f"{m.group(1)}-01-01"
                        break
            if publication_date:
                break

    doc_type = leader[6:8] if len(leader) >= 8 else None
    if genre:
        doc_type = (doc_type + ":" + ";".join(genre[:3])) if doc_type else ";".join(genre[:3])

    return {
        "id": f"marc:{rec_id}",
        "source": "marc",
        "title": title,
        "agency": agency,
        "agency_slug": None,
        "sudoc": sudoc,
        "sudoc_stem": sudoc_stem,
        "doc_type": doc_type,
        "publication_date": publication_date,
        "cataloged_date": cataloged_date,
        "url": url,
        "subjects": subjects,
        "raw_json": parsed,
    }
