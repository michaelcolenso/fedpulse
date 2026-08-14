"""Exact-rule standalone Federal Register watchlist selection."""
from __future__ import annotations
import json
from datetime import date, timedelta
from .taxonomy import AgencyIdentity, canonicalize_agency, watchlist_matches

def _row(row):
    if isinstance(row, dict): return row
    return dict(row)

def detect_standalone(conn, as_of: str, lookback_days: int = 14) -> list[dict]:
    end=date.fromisoformat(as_of); start=end-timedelta(days=lookback_days)
    rows=conn.execute("select * from records where source='fr' and publication_date between ? and ? order by publication_date,id",(start.isoformat(),end.isoformat())).fetchall(); out=[]
    for raw in rows:
        row=_row(raw); identity=AgencyIdentity("fr",row.get("agency") or "",row.get("canonical_agency_id"),row.get("canonical_agency_name"),None,"stored")
        if not identity.canonical_id: identity=canonicalize_agency("fr",identity.raw_name,row.get("raw_json"))
        matches=watchlist_matches(row,identity)
        if not matches: continue
        out.append({"record_id":row["id"],"canonical_agency_id":identity.canonical_id,"canonical_agency_name":identity.canonical_name,"raw_agency_name":row.get("agency"),"title":row.get("title"),"doc_type":row.get("doc_type"),"publication_date":row.get("publication_date"),"official_url":row.get("url"),"matches":matches,"evidence":{"topics":json.loads(row.get("subjects") or "[]") if isinstance(row.get("subjects"),str) else row.get("subjects") or [],"title":row.get("title"),"doc_type":row.get("doc_type")}})
    return out
