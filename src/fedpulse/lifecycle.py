"""Persistent lifecycle and notification cooldown for v0.2 signals."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from typing import Any, Mapping

_IGNORE = {"priority_score", "score", "z_score", "current_count", "updated_at", "generated_at"}

def _stable(value: Any) -> Any:
    if isinstance(value, Mapping): return {k: _stable(v) for k, v in sorted(value.items()) if k not in _IGNORE}
    if isinstance(value, (list, tuple)): return [_stable(v) for v in value]
    return value

def fingerprint(signal: Mapping[str, Any]) -> str:
    material = {"signal_type":signal.get("signal_type"), "signal_key":signal.get("signal_key"), "direction":signal.get("direction"), "confidence":signal.get("confidence"), "status":signal.get("status"), "payload":_stable(signal.get("payload", {}))}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def _as_dt(value: str | dt.datetime | None) -> dt.datetime | None:
    if value is None: return None
    if isinstance(value, dt.datetime): return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))

def _previous_payload(previous: Mapping[str, Any]) -> dict[str, Any]:
    if not hasattr(previous, "get"):
        previous = dict(previous)
    value = previous.get("payload_json") or {}
    if isinstance(value, str):
        try: return json.loads(value)
        except json.JSONDecodeError: return {}
    return dict(value)

def _record_ids(payload: Mapping[str, Any]) -> set[str]:
    return {str(item.get("record_id")) for item in payload.get("evidence", []) if item.get("record_id")}

def _family_weight(payload: Mapping[str, Any]) -> int:
    weights = {"presidential_document": 4, "rule": 3, "final_rule": 3, "proposed_rule": 2, "notice": 1}
    return max((weights.get(name, 0) for name, count in payload.get("document_type_counts", {}).items() if count), default=0)

def _material_change(signal_type: str, old: Mapping[str, Any], new: Mapping[str, Any]) -> bool:
    if signal_type == "package":
        return _record_ids(old) != _record_ids(new) or _family_weight(old) != _family_weight(new)
    if signal_type == "horizon":
        old_count = int(old.get("record_count") or old.get("last_four_week_catalog_count") or 0)
        new_count = int(new.get("record_count") or new.get("last_four_week_catalog_count") or 0)
        return new_count - old_count >= 3 and new_count >= old_count * 1.25
    if signal_type == "metric":
        return bool(old.get("newly_elevated") != new.get("newly_elevated") or old.get("alert") != new.get("alert"))
    return False

def should_notify(previous: Mapping[str, Any] | None, current: Mapping[str, Any], now: dt.datetime, cooldown_hours: int = 48) -> bool:
    if previous is None: return True
    if not hasattr(previous, "get"):
        previous = dict(previous)
    if previous.get("fingerprint") == fingerprint(current): return False
    old = _previous_payload(previous); new = dict(current.get("payload") or {})
    new.update({key: current[key] for key in ("direction", "confidence") if key in current})
    if previous.get("status") == "resolved": return True
    requested = current.get("status")
    if requested in {"resolved", "stale"} and previous.get("status") != requested: return True
    if current.get("critical") or new.get("critical"): return True
    if old.get("direction") != new.get("direction") or old.get("confidence") != new.get("confidence"): return True
    if _family_weight(new) > _family_weight(old): return True
    last = _as_dt(previous.get("last_notified"))
    if last is not None and now - last < dt.timedelta(hours=cooldown_hours): return False
    if old.get("_pending_material_change"): return True
    return _material_change(str(current.get("signal_type") or previous.get("signal_type") or ""), old, new)

def update_signal_state(conn: sqlite3.Connection, signals: list[dict[str, Any]], now: dt.datetime, *, commit: bool = True) -> list[dict[str, Any]]:
    now = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc); stamp = now.isoformat().replace("+00:00", "Z")
    incoming = {}
    for signal in signals:
        signal = dict(signal); signal.setdefault("signal_key", f"{signal.get('signal_type','signal')}:{signal.get('package_id', signal.get('agency','unknown'))}")
        incoming[signal["signal_key"]] = signal
    existing = {r["signal_key"]:r for r in conn.execute("select * from signal_state").fetchall()}
    out=[]
    for key, signal in sorted(incoming.items()):
        prev = existing.get(key); fp = fingerprint(signal)
        requested = signal.get("status", "qualified")
        if prev is None or prev["status"] == "resolved": lifecycle = "new"
        elif requested == "stale" and prev["status"] != "stale": lifecycle = "stale"
        elif requested == "stale": lifecycle = "stale"
        else: lifecycle = "continuing"
        notify = should_notify(prev, {**signal, "status": requested, "fingerprint":fp}, now)
        last_notified = stamp if notify else (prev["last_notified"] if prev else None)
        payload = dict(signal.get("payload") or {}); payload.update({k:signal[k] for k in ("direction","confidence") if k in signal})
        old_payload = _previous_payload(prev) if prev else {}
        pending = bool(prev and not notify and _material_change(signal.get("signal_type", "signal"), old_payload, payload))
        if pending: payload["_pending_material_change"] = True
        elif notify: payload.pop("_pending_material_change", None)
        stored_fp = fp if notify or prev is None else prev["fingerprint"]
        conn.execute("insert or replace into signal_state(signal_key,signal_type,status,first_seen,last_seen,last_notified,fingerprint,payload_json) values (?,?,?,?,?,?,?,?)",
                     (key, signal.get("signal_type","signal"), lifecycle, prev["first_seen"] if prev and prev["status"] != "resolved" else stamp, stamp, last_notified, stored_fp, json.dumps(payload, sort_keys=True)))
        out.append({**signal,"signal_key":key,"lifecycle":lifecycle,"notify":notify})
    for key, prev in sorted(existing.items()):
        if key in incoming: continue
        if prev["status"] == "resolved":
            continue
        payload = json.loads(prev["payload_json"] or "{}")
        resolved = {"signal_key":key,"signal_type":prev["signal_type"],"status":"resolved","payload":payload}
        resolved_fp = fingerprint(resolved)
        notify = should_notify(prev, resolved, now)
        last_notified = stamp if notify else prev["last_notified"]
        conn.execute("update signal_state set status='resolved', last_seen=?, last_notified=?, fingerprint=?, payload_json=? where signal_key=?", (stamp, last_notified, resolved_fp, json.dumps(payload, sort_keys=True), key))
        out.append({"signal_key":key,"signal_type":prev["signal_type"],"lifecycle":"resolved","notify":notify,"payload":payload})
    if commit: conn.commit()
    return out
