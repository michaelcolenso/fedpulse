#!/usr/bin/env python3
"""Bootstrap/query FedPulse semantic retrieval using Workers AI + Vectorize.

Uses only authenticated Cloudflare APIs. The public dashboard Worker does not need to
expose semantic mutation endpoints.
"""
from __future__ import annotations

import argparse, json, os, sqlite3, urllib.request
from pathlib import Path

from fedpulse.canonical_text import canonical_event_text, canonical_profile_text
from fedpulse.opportunities import load_profile

MODEL = "@cf/qwen/qwen3-embedding-0.6b"


def post_json(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def embed(account: str, token: str, texts: list[str]) -> list[list[float]]:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}"
    data = post_json(url, token, {"text": texts})
    result = data.get("result") or {}
    vectors = result.get("data") if isinstance(result, dict) else None
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise RuntimeError(f"unexpected embedding response: {data}")
    return vectors


def rows_for_bootstrap(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT event_id,source,kind,stage,title,agency,event_date,amount,currency,official_url,payload_json
           FROM government_events
           WHERE kind IN ('contract_opportunity','funding_opportunity')
           ORDER BY COALESCE(event_date,'') DESC, last_seen DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--profile", default="default")
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()

    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    conn = sqlite3.connect(args.db); conn.row_factory = sqlite3.Row
    rows = rows_for_bootstrap(conn, args.limit)
    docs = []
    for row in rows:
        item = dict(row)
        text = canonical_event_text(item)
        if text:
            docs.append((item, text))

    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for start in range(0, len(docs), 20):
            batch = docs[start:start+20]
            vectors = embed(account, token, [text for _, text in batch])
            for (item, text), vector in zip(batch, vectors):
                meta = {
                    "event_id": str(item["event_id"])[:64],
                    "source": str(item.get("source") or "")[:64],
                    "kind": str(item.get("kind") or "")[:64],
                    "title": str(item.get("title") or "")[:300],
                    "event_date": str(item.get("event_date") or "")[:32],
                }
                fh.write(json.dumps({"id": str(item["event_id"])[:64], "values": vector, "metadata": meta}, separators=(",", ":")) + "\n")

    profile = load_profile(args.profile)
    qtext = canonical_profile_text(args.profile, profile)
    qvector = embed(account, token, [qtext])[0]
    Path(str(out) + ".query.json").write_text(json.dumps({"profile": args.profile, "text": qtext, "vector": qvector}))
    print(json.dumps({"documents": len(docs), "profile": args.profile, "model": MODEL}))

if __name__ == "__main__":
    main()
