#!/usr/bin/env python3
"""Query FedPulse Vectorize with a canonical watch profile."""
from __future__ import annotations

import argparse, json, os, urllib.error, urllib.request

from fedpulse.canonical_text import canonical_profile_text
from fedpulse.opportunities import load_profile

MODEL = "@cf/qwen/qwen3-embedding-0.6b"


def post_json(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(json.dumps({"url": url, "http_status": exc.code, "body": detail}, indent=2))
        raise


def embed(account: str, token: str, text: str) -> list[float]:
    data = post_json(f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}", token, {"text": [text]})
    result = data.get("result") or {}
    vectors = result.get("data") if isinstance(result, dict) else None
    if not isinstance(vectors, list) or len(vectors) != 1:
        raise RuntimeError(f"unexpected embedding response: {data}")
    return vectors[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="default")
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--index", default="fedpulse-opportunities-v1")
    args = ap.parse_args()
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]; token = os.environ["CLOUDFLARE_API_TOKEN"]
    text = canonical_profile_text(args.profile, load_profile(args.profile))
    vector = embed(account, token, text)
    data = post_json(f"https://api.cloudflare.com/client/v4/accounts/{account}/vectorize/v2/indexes/{args.index}/query", token, {"vector": vector, "topK": args.top_k, "returnMetadata": "all"})
    matches = ((data.get("result") or {}).get("matches") or []) if data.get("success") else []
    print(json.dumps({"profile": args.profile, "query_text": text, "count": len(matches), "matches": matches, "errors": data.get("errors") or []}, indent=2))
    if not data.get("success") or not matches: raise SystemExit(1)

if __name__ == "__main__": main()
