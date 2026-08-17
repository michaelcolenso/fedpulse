#!/usr/bin/env python3
"""Publish a complete dashboard generation to Cloudflare KV, then atomically move the pointer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

OUTPUTS = (
    "daily_activity",
    "packages",
    "standalone",
    "fr_metrics",
    "marc_horizon",
    "health",
    "brief",
    "opportunities_today",
    "hidden_gems",
)


def put(account: str, namespace: str, token: str, key: str, body: bytes) -> None:
    encoded = urllib.parse.quote(key, safe="")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/storage/kv/namespaces/{namespace}/values/{encoded}"
    request = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"KV PUT failed for {key}: HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--legacy-flat", action="store_true", help="also update pre-v0.3 flat keys during migration")
    args = parser.parse_args()

    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    namespace = os.environ["CLOUDFLARE_KV_NAMESPACE_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    root = args.directory

    payloads: dict[str, bytes] = {}
    manifest_files: dict[str, dict[str, object]] = {}
    generated_at = None
    as_of = None
    for name in OUTPUTS:
        path = root / f"{name}.json"
        body = path.read_bytes()
        parsed = json.loads(body)
        generated_at = generated_at or parsed.get("generated_at")
        as_of = as_of or parsed.get("as_of")
        if parsed.get("generated_at") != generated_at or parsed.get("as_of") != as_of:
            raise SystemExit(f"mixed output generation detected before publish: {name}")
        payloads[name] = body
        manifest_files[f"{name}.json"] = {
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
            "items": len(parsed.get("items", [])),
        }

    git_sha = os.environ.get("GITHUB_SHA", "local")
    generation = f"{str(generated_at).replace(':', '').replace('-', '')}-{git_sha[:12]}"
    manifest = {
        "schema_version": 4,
        "generation": generation,
        "generated_at": generated_at,
        "as_of": as_of,
        "git_sha": git_sha,
        "files": manifest_files,
    }

    for name, body in payloads.items():
        put(account, namespace, token, f"generation/{generation}/{name}.json", body)
    put(account, namespace, token, f"generation/{generation}/manifest.json", json.dumps(manifest, sort_keys=True).encode())

    if args.legacy_flat:
        for name, body in payloads.items():
            put(account, namespace, token, f"{name}.json", body)

    # Pointer is deliberately last: readers either see the complete previous generation or the complete new one.
    put(account, namespace, token, "current.json", json.dumps(manifest, sort_keys=True).encode())
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())