"""Pipeline component health and source freshness contracts."""
from __future__ import annotations

import datetime as dt
import sqlite3

def _stamp(value: str | dt.datetime) -> str:
    if isinstance(value, dt.datetime): value = value.isoformat()
    return value if value.endswith("Z") else value

def record_attempt(conn: sqlite3.Connection, component: str, now: str | dt.datetime) -> None:
    stamp=_stamp(now); conn.execute("insert into pipeline_state(component,last_attempt,last_success,status,detail) values(?,?,?,?,?) on conflict(component) do update set last_attempt=excluded.last_attempt,status='running'", (component,stamp,None,"running",None)); conn.commit()

def record_success(conn: sqlite3.Connection, component: str, now: str | dt.datetime, detail: str = "") -> None:
    stamp=_stamp(now); conn.execute("insert into pipeline_state(component,last_attempt,last_success,status,detail) values(?,?,?,?,?) on conflict(component) do update set last_attempt=excluded.last_attempt,last_success=excluded.last_success,status='fresh',detail=excluded.detail", (component,stamp,stamp,"fresh",detail)); conn.commit()

def record_failure(conn: sqlite3.Connection, component: str, now: str | dt.datetime, detail: str) -> None:
    stamp=_stamp(now); conn.execute("insert into pipeline_state(component,last_attempt,last_success,status,detail) values(?,?,?,?,?) on conflict(component) do update set last_attempt=excluded.last_attempt,status='failed',detail=excluded.detail", (component,stamp,None,"failed",detail)); conn.commit()

def source_freshness(conn: sqlite3.Connection, now: str | dt.datetime) -> dict[str, dict]:
    current = dt.datetime.fromisoformat(_stamp(now).replace("Z", "+00:00")); out={}
    for row in conn.execute("select * from pipeline_state order by component"):
        success = row["last_success"]
        status = row["status"]
        if success:
            try: age=(current - dt.datetime.fromisoformat(success.replace("Z", "+00:00"))).total_seconds()
            except ValueError: age=10**12
            if age > 48*3600: status="stale"
        elif status not in {"fresh"}:
            attempted = row["last_attempt"]
            if attempted:
                try: age=(current - dt.datetime.fromisoformat(attempted.replace("Z", "+00:00"))).total_seconds()
                except ValueError: age=10**12
                status="stale" if age > 48*3600 else ("failed" if status == "failed" else "degraded")
            else:
                status="failed" if status == "failed" else "degraded"
        component = row["component"]
        fields = {"last_attempt":row["last_attempt"],"last_success":success,"status":status,"detail":row["detail"]}
        if component == "federal_register":
            fields["last_publication_date"] = conn.execute("select max(publication_date) from records where source='fr' and publication_date is not null").fetchone()[0]
        if component == "marc":
            fields["last_cataloged_date"] = conn.execute("select max(cataloged_date) from records where source='marc' and cataloged_date is not null").fetchone()[0]
            fields["maintenance_applied_at"] = success
        out[component]=fields
    for component in ("federal_register", "marc"):
        if component in out:
            continue
        fields = {"last_attempt":None,"last_success":None,"status":"degraded","detail":"no ingest attempt recorded"}
        if component == "federal_register":
            fields["last_publication_date"] = conn.execute("select max(publication_date) from records where source='fr' and publication_date is not null").fetchone()[0]
        else:
            fields["last_cataloged_date"] = conn.execute("select max(cataloged_date) from records where source='marc' and cataloged_date is not null").fetchone()[0]
            fields["maintenance_applied_at"] = None
        out[component] = fields
    return out
