"""Canonical, evidence-preserving text representations for semantic retrieval.

These strings are retrieval documents, not factual evidence. Structured facts remain
in the government event graph and must be used for eligibility and verification.
"""
from __future__ import annotations

import json
from typing import Any

MAX_DESCRIPTION_CHARS = 6000


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _payload(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("payload")
    if isinstance(raw, dict):
        return raw
    raw = item.get("payload_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _pick(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return _clean(value)
    return ""


def _row(payload: dict[str, Any]) -> dict[str, Any]:
    row = payload.get("row")
    return row if isinstance(row, dict) else payload


def _line(label: str, value: Any) -> str | None:
    text = _clean(value)
    return f"{label}: {text}" if text else None


def _description(data: dict[str, Any]) -> str:
    value = _pick(
        data,
        "Description", "description", "Synopsis", "synopsis", "Abstract", "abstract",
        "AdditionalInformation", "additional_information", "summary", "Summary",
    )
    return value[:MAX_DESCRIPTION_CHARS]


def canonical_event_text(item: dict[str, Any]) -> str:
    """Build source-aware text optimized for semantic retrieval.

    Exact identifiers and authoritative structured fields are included to give the
    embedding useful context, but retrieval similarity never upgrades those fields
    into evidence.
    """
    payload = _payload(item)
    data = _row(payload)
    source = _clean(item.get("source"))
    kind = _clean(item.get("kind"))
    title = _clean(item.get("title"))
    agency = _clean(item.get("agency"))
    stage = _clean(item.get("stage"))

    lines = [
        _line("Title", title),
        _line("Source", source),
        _line("Type", kind),
        _line("Stage", stage),
        _line("Agency", agency),
    ]

    # SAM: place of performance is intentionally separate from office/contact geography.
    if source == "sam_opportunity" or kind == "contract_opportunity":
        pop = ", ".join(x for x in [
            _pick(data, "PopCity", "place_of_performance_city"),
            _pick(data, "PopState", "place_of_performance_state"),
            _pick(data, "PopZip", "place_of_performance_zip"),
        ] if x)
        lines += [
            _line("Place of performance", pop),
            _line("NAICS", _pick(data, "NaicsCode", "NAICS", "naics")),
            _line("Notice type", _pick(data, "Type", "notice_type")),
            _line("Set aside", _pick(data, "SetASide", "SetAside", "set_aside")),
            _line("Response deadline", _pick(data, "ResponseDeadLine", "response_deadline")),
            _line("Solicitation", _pick(data, "SolicitationNumber", "solicitation_number")),
        ]
    elif source == "grants_gov" or kind == "funding_opportunity":
        lines += [
            _line("Opportunity number", _pick(data, "OpportunityNumber", "opportunity_number")),
            _line("Assistance listing", _pick(data, "CFDANumbers", "CFDANumber", "assistance_listing")),
            _line("Eligibility", _pick(data, "EligibleApplicants", "eligibility")),
            _line("Estimated funding", _pick(data, "EstimatedFunding", "AwardCeiling", "estimated_funding")),
            _line("Close date", _pick(data, "CloseDate", "close_date")),
        ]
    elif source in {"reginfo", "oira_meetings"} or kind == "stakeholder_meeting":
        lines += [
            _line("RIN", _pick(data, "RIN", "rin")),
            _line("Regulatory action", _pick(data, "RuleTitle", "rule_title", "Title")),
            _line("Meeting participants", _pick(data, "Participants", "participants", "Organizations", "organizations")),
            _line("Meeting topic", _pick(data, "MeetingTopic", "meeting_topic")),
        ]
    elif source in {"federal_register", "fr"}:
        lines += [
            _line("Document type", _pick(data, "type", "document_type")),
            _line("RIN", _pick(data, "regulation_id_numbers", "rin")),
            _line("Docket", _pick(data, "docket_id", "docket")),
            _line("Action", _pick(data, "action")),
        ]
    elif source in {"congress_bill_status", "govinfo_bill_status"} or kind == "legislative_update":
        lines += [
            _line("Bill", _pick(data, "bill_id", "bill_number", "BillNumber")),
            _line("Congress", _pick(data, "congress", "Congress")),
            _line("Latest action", _pick(data, "latest_action", "LatestAction")),
            _line("Policy area", _pick(data, "policy_area", "PolicyArea")),
        ]
    elif source == "usaspending" or kind == "federal_award_action":
        lines += [
            _line("Award", _pick(data, "Award ID", "award_id", "generated_unique_award_id")),
            _line("Recipient", _pick(data, "Recipient Name", "recipient_name")),
            _line("NAICS", _pick(data, "NAICS", "naics_code")),
            _line("Place of performance", _pick(data, "Place of Performance", "place_of_performance")),
            _line("Transaction description", _pick(data, "Description", "transaction_description")),
        ]

    lines.append(_line("Description", _description(data)))
    return "\n".join(line for line in lines if line)


def canonical_profile_text(name: str, profile: dict[str, Any]) -> str:
    """Turn a deterministic watch profile into a semantic query document."""
    fields = [
        f"Watch profile: {_clean(profile.get('label') or name)}",
        _line("Topics and capabilities", ", ".join(profile.get("keywords", []))),
        _line("Geographies", ", ".join(profile.get("geographies", []))),
        _line("Relevant agencies", ", ".join(profile.get("agencies", []))),
        _line("NAICS", ", ".join(str(x) for x in profile.get("naics", []))),
    ]
    return "\n".join(x for x in fields if x)
