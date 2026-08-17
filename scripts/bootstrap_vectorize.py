#!/usr/bin/env python3
"""Bootstrap/query FedPulse semantic retrieval using Workers AI + Vectorize.

Uses only authenticated Cloudflare APIs. The public dashboard Worker does not need to
expose semantic mutation endpoints.

Incremental mode fingerprints the exact canonical embedding text plus model identity.
The generated manifest must be committed only after Vectorize upsert succeeds.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
import urllib.request
from pathlib import Path

from fedpulse.canonical_text import canonical_event_text, canonical_profile_text
from fedpulse.opportunities import load_profile
from fedpulse.semantic_state import (
    EmbeddingState,
    changed_states,
    commit_states,
    content_fingerprint,
)

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


def _read_manifest(path: Path) -> list[EmbeddingState]:
    states: list[EmbeddingState] = []
    if not path.exists():
        raise FileNotFoundError(path)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        states.append(
            EmbeddingState(
                event_id=str(item["event_id"]),
                content_hash=str(item["content_hash"]),
                model=str(item["model"]),
            )
        )
    return states


def _atomic_write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as tmp:
        for line in lines:
            tmp.write(line)
            tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out")
    ap.add_argument("--profile", default="default")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--incremental", action="store_true")
    ap.add_argument("--manifest")
    ap.add_argument("--stats")
    ap.add_argument("--skip-query", action="store_true")
    ap.add_argument("--commit-manifest")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    if args.commit_manifest:
        states = _read_manifest(Path(args.commit_manifest))
        count = commit_states(conn, states)
        print(json.dumps({"committed": count, "model": MODEL}))
        return

    if not args.out:
        ap.error("--out is required unless --commit-manifest is used")
    if args.incremental and not args.manifest:
        ap.error("--manifest is required with --incremental")

    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]

    rows = rows_for_bootstrap(conn, args.limit)
    docs: list[tuple[dict, str, EmbeddingState]] = []
    for row in rows:
        item = dict(row)
        text = canonical_event_text(item)
        if text:
            state = EmbeddingState(
                event_id=str(item["event_id"]),
                content_hash=content_fingerprint(text, MODEL),
                model=MODEL,
            )
            docs.append((item, text, state))

    considered = len(docs)
    if args.incremental:
        changed = {state.event_id for state in changed_states(conn, [state for _, _, state in docs])}
        docs = [doc for doc in docs if doc[2].event_id in changed]

    vector_lines: list[str] = []
    manifest_lines: list[str] = []
    for start in range(0, len(docs), 20):
        batch = docs[start:start + 20]
        vectors = embed(account, token, [text for _, text, _ in batch])
        for (item, _text, state), vector in zip(batch, vectors):
            meta = {
                "event_id": str(item["event_id"])[:64],
                "source": str(item.get("source") or "")[:64],
                "kind": str(item.get("kind") or "")[:64],
                "title": str(item.get("title") or "")[:300],
                "event_date": str(item.get("event_date") or "")[:32],
            }
            vector_lines.append(
                json.dumps(
                    {
                        "id": str(item["event_id"])[:64],
                        "values": vector,
                        "metadata": meta,
                    },
                    separators=(",", ":"),
                )
            )
            manifest_lines.append(
                json.dumps(
                    {
                        "event_id": state.event_id,
                        "content_hash": state.content_hash,
                        "model": state.model,
                    },
                    separators=(",", ":"),
                )
            )

    out = Path(args.out)
    _atomic_write_lines(out, vector_lines)
    if args.manifest:
        _atomic_write_lines(Path(args.manifest), manifest_lines)

    if not args.skip_query:
        profile = load_profile(args.profile)
        qtext = canonical_profile_text(args.profile, profile)
        qvector = embed(account, token, [qtext])[0]
        Path(str(out) + ".query.json").write_text(
            json.dumps({"profile": args.profile, "text": qtext, "vector": qvector}),
            encoding="utf-8",
        )

    stats = {
        "considered": considered,
        "documents": len(docs),
        "skipped": considered - len(docs),
        "profile": args.profile,
        "model": MODEL,
        "incremental": args.incremental,
    }
    if args.stats:
        stats_path = Path(args.stats)
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(stats), encoding="utf-8")
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
