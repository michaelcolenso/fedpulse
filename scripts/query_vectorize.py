#!/usr/bin/env python3
"""Query FedPulse Vectorize with a canonical watch profile."""
from __future__ import annotations

import argparse, json, os, urllib.error, urllib.request

from fedpulse.canonical_text import canonical_profile_text
from fedpulse.opportunities import load_profile
from scripts.bootstrap_vectorize import embed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="default")
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--index", default="fedpulse-opportunities-v1")
    args = ap.parse_args()

    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    profile = load_profile(args.profile)
    text = canonical_profile_text(args.profile, profile)
    vector = embed(account, token, [text])[0]
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/vectorize/v2/indexes/{args.index}/query"
    body = json.dumps({"vector": vector, "topK": args.top_k, "returnMetadata": "all"}).encode()
    req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(json.dumps({"http_status": exc.code, "body": detail}, indent=2))
        raise SystemExit(1)

    matches = ((data.get("result") or {}).get("matches") or []) if data.get("success") else []
    print(json.dumps({"profile": args.profile, "query_text": text, "count": len(matches), "matches": matches, "errors": data.get("errors") or []}, indent=2))
    if not data.get("success") or not matches:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
