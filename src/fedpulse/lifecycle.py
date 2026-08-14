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

def should_notify(previous: Mapping[str, Any] | None, current: Mapping[str, Any], now: dt.datetime, cooldown_hours: int = 48) -> bool:
    if previous is None: return True
    if not hasattr(previous, "get"):
        previous = dict(previous)
    old_payload = previous.get("payload_json")
    if isinstance(old_payload, str):
        try: old_payload = json.loads(old_payload)
        except json.JSONDecodeError: old_payload = {}
    old = {"signal_key":previous.get("signal_key"),"signal_type":previous.get("signal_type"),"direction":(old_payload or {}).get("direction"),"confidence":(old_payload or {}).get("confidence"),"status":previous.get("status"),"payload":old_payload or {}}
    changed = previous.get("fingerprint") != fingerprint(current)
    last = _as_dt(previous.get("last_notified"))
    if changed: return True
    return last is None or now - last >= dt.timedelta(hours=cooldown_hours)

def update_signal_state(conn: sqlite3.Connection, signals: list[dict[str, Any]], now: dt.datetime) -> list[dict[str, Any]]:
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
        lifecycle = "new" if prev is None else ("stale" if requested == "stale" else "continuing")
        notify = should_notify(prev, {**signal, "fingerprint":fp}, now)
        last_notified = stamp if notify else (prev["last_notified"] if prev else None)
        payload = dict(signal.get("payload") or {}); payload.update({k:signal[k] for k in ("direction","confidence") if k in signal})
        conn.execute("insert or replace into signal_state(signal_key,signal_type,status,first_seen,last_seen,last_notified,fingerprint,payload_json) values (?,?,?,?,?,?,?,?)",
                     (key, signal.get("signal_type","signal"), lifecycle, prev["first_seen"] if prev else stamp, stamp, last_notified, fp, json.dumps(payload, sort_keys=True)))
        out.append({**signal,"signal_key":key,"lifecycle":lifecycle,"notify":notify})
    for key, prev in sorted(existing.items()):
        if key in incoming: continue
        payload = json.loads(prev["payload_json"] or "{}")
        conn.execute("update signal_state set status='resolved', last_seen=?, payload_json=? where signal_key=?", (stamp, json.dumps(payload, sort_keys=True), key))
        out.append({"signal_key":key,"signal_type":prev["signal_type"],"lifecycle":"resolved","notify":should_notify(prev, {"signal_key":key,"signal_type":prev["signal_type"],"status":"resolved","payload":payload}, now),"payload":payload})
    conn.commit(); return out
