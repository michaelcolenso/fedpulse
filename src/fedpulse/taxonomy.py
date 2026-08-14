"""Versioned, deterministic metadata taxonomy for FedPulse v0.2."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CONFIG = Path(__file__).parent / "config"

def _load(name: str) -> dict[str, Any]:
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))

AGENCY_CONFIG = _load("agency_aliases.json")
DIRECTION_CONFIG = _load("direction_phrases.json")
SECTOR_CONFIG = _load("sector_map.json")
WATCHLIST_CONFIG = _load("watchlists.json")

@dataclass(frozen=True)
class AgencyIdentity:
    source: str
    raw_name: str
    canonical_id: str | None
    canonical_name: str | None
    parent_id: str | None
    mapping_method: str
    alias_version: str = AGENCY_CONFIG["version"]


def normalize_org(name: str) -> str:
    """Normalize only harmless Unicode/punctuation/jurisdiction variants; never fuzzy match."""
    value = unicodedata.normalize("NFKD", name or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).casefold().strip()
    value = re.sub(r"\s*\((?:u\.?s\.?|united states)\)\s*$", "", value)
    value = re.sub(r"[\u2018\u2019`´]", "'", value)
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def canonicalize_agency(source: str, raw_name: str, raw_json: dict | None = None) -> AgencyIdentity:
    raw_name = raw_name or ""
    aliases = [a for a in AGENCY_CONFIG["aliases"] if a["source"] == source]
    exact = next((a for a in aliases if a["raw_name"] == raw_name), None)
    if exact:
        return AgencyIdentity(source, raw_name, exact["canonical_id"], exact["canonical_name"], exact.get("parent_id"), exact["mapping_method"])
    norm = normalize_org(raw_name)
    normalized = next((a for a in aliases if normalize_org(a["raw_name"]) == norm), None)
    if normalized:
        return AgencyIdentity(source, raw_name, normalized["canonical_id"], normalized["canonical_name"], normalized.get("parent_id"), "normalized_exact")
    return AgencyIdentity(source, raw_name, None, None, None, "unmapped")

_NEGATIONS = {"not", "no", "never", "without"}

def _plain(text: Any) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).casefold()
    return value

def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w]+(?:['’-][\w]+)?", text, flags=re.UNICODE)

def _find_phrase(text: str, phrase: str) -> list[tuple[int, int, list[str]]]:
    p = _plain(phrase).replace("’", "'")
    if not p: return []
    text = _plain(text)
    pattern = re.compile(r"(?<![\w])" + re.escape(p) + r"(?![\w])", re.UNICODE)
    tokens = _tokens(text)
    out = []
    for match in pattern.finditer(text):
        before = _tokens(text[:match.start()])[-3:]
        out.append((match.start(), match.end(), before))
    return out

def classify_direction(record: Mapping[str, Any]) -> dict[str, Any]:
    raw = record.get("raw_json") or {}
    if isinstance(raw, str):
        try: raw = json.loads(raw)
        except json.JSONDecodeError: raw = {}
    text = " ".join(str(record.get(k) or raw.get(k) or "") for k in ("action", "title", "abstract"))
    matches: list[dict[str, Any]] = []
    # Longer exact phrases win over single-word entries at the same location.
    candidates = []
    for direction, phrases in DIRECTION_CONFIG["directions"].items():
        for phrase in phrases:
            for start, end, before in _find_phrase(text, phrase):
                if any(token in _NEGATIONS for token in before):
                    continue
                candidates.append((start, -(len(_tokens(phrase))), direction, phrase))
    candidates.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    occupied: list[tuple[int, int]] = []
    for start, _, direction, phrase in candidates:
        end = start + len(_plain(phrase))
        if any(start < b and end > a for a, b in occupied):
            continue
        occupied.append((start, end))
        matches.append({"direction": direction, "phrase": phrase})
    tags = {m["direction"] for m in matches}
    direction = next(iter(tags)) if len(tags) == 1 else "mixed_or_unknown"
    return {"direction": direction, "matched_phrases": matches, "direction_dictionary_version": DIRECTION_CONFIG["version"]}


def _subjects(record: Mapping[str, Any]) -> list[str]:
    value = record.get("subjects") or record.get("topics") or []
    if isinstance(value, str):
        try: value = json.loads(value)
        except json.JSONDecodeError: value = [value]
    return [str(x) for x in value if x]

def coverage_tags(record: Mapping[str, Any], identity: AgencyIdentity) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    topics = _subjects(record)
    topic_map = SECTOR_CONFIG["topics"]
    for topic in topics:
        for configured, sectors in topic_map.items():
            if normalize_org(topic) == normalize_org(configured):
                for sector in sectors:
                    item = (sector, "exact_fr_topic", configured)
                    if item not in seen:
                        out.append({"sector": sector, "source": "exact_fr_topic", "matched_value": configured}); seen.add(item)
    for sector in SECTOR_CONFIG["agency_defaults"].get(identity.canonical_id or "", []):
        item = (sector, "canonical_agency", identity.canonical_id or "")
        if item not in seen:
            out.append({"sector": sector, "source": "canonical_agency", "matched_value": identity.canonical_id}); seen.add(item)
    title = _plain(record.get("title", ""))
    for phrase, sectors in SECTOR_CONFIG["title_keywords"].items():
        if _find_phrase(title, phrase):
            for sector in sectors:
                item = (sector, "exact_title_keyword", phrase)
                if item not in seen:
                    out.append({"sector": sector, "source": "exact_title_keyword", "matched_value": phrase}); seen.add(item)
    return out

def watchlist_matches(record: Mapping[str, Any], identity: AgencyIdentity) -> list[dict[str, Any]]:
    topics = _subjects(record)
    title = _plain(record.get("title", ""))
    doc_type = str(record.get("doc_type") or "").strip().lower().replace("-", "_").replace(" ", "_")
    out = []
    for rule in WATCHLIST_CONFIG["watchlists"]:
        if rule["agency_ids"] and identity.canonical_id not in rule["agency_ids"]: continue
        topic_hit = next((v for v in topics for x in rule["topics"] if normalize_org(v) == normalize_org(x)), None)
        phrase_hit = next((p for p in rule["phrases"] if _find_phrase(title, p)), None)
        type_hit = not rule["doc_types"] or doc_type in rule["doc_types"]
        if type_hit and (topic_hit or phrase_hit):
            out.append({"watchlist": rule["watchlist"], "rule": f"{rule['watchlist']}: exact metadata match", "matched_field": "topic" if topic_hit else "title", "matched_value": topic_hit or phrase_hit, "watchlist_version": WATCHLIST_CONFIG["version"]})
    return out
