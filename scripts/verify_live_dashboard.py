#!/usr/bin/env python3
"""Fail if the live dashboard cannot serve one coherent FedPulse generation."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

FEEDS = (
    "daily_activity.json",
    "packages.json",
    "standalone.json",
    "fr_metrics.json",
    "marc_horizon.json",
    "health.json",
    "brief.json",
    "opportunities_today.json",
    "hidden_gems.json",
)


def fetch(url: str) -> tuple[dict, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "FedPulse/live-verifier"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}: {url}")
            generation = response.headers.get("x-fedpulse-generation", "")
            payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise RuntimeError(f"non-object JSON: {url}")
            return payload, generation
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {url}: {body[:300]}") from exc


def verify(base_url: str) -> dict:
    base = base_url.rstrip("/") + "/data/outputs/current/"
    generations: dict[str, str] = {}
    metadata: dict[str, tuple[str | None, str | None]] = {}
    counts: dict[str, int | None] = {}

    for name in FEEDS:
        payload, generation = fetch(base + name)
        if not generation:
            raise RuntimeError(f"missing x-fedpulse-generation header: {name}")
        if generation == "legacy-fallback":
            raise RuntimeError(f"feed still requires legacy fallback: {name}")
        generations[name] = generation
        metadata[name] = (payload.get("generated_at"), payload.get("as_of"))
        items = payload.get("items")
        counts[name] = len(items) if isinstance(items, list) else None

    distinct_generations = set(generations.values())
    if len(distinct_generations) != 1:
        raise RuntimeError(f"mixed live generations: {generations}")

    known_metadata = {value for value in metadata.values() if value != (None, None)}
    if len(known_metadata) > 1:
        raise RuntimeError(f"mixed generated_at/as_of metadata: {metadata}")

    return {
        "generation": next(iter(distinct_generations)),
        "feeds": len(FEEDS),
        "item_counts": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--delay", type=float, default=5.0)
    args = parser.parse_args()

    last_error: Exception | None = None
    for attempt in range(1, args.attempts + 1):
        try:
            result = verify(args.base_url)
            print(json.dumps(result, sort_keys=True))
            return 0
        except Exception as exc:
            last_error = exc
            if attempt < args.attempts:
                print(f"live dashboard verification attempt {attempt} failed: {exc}")
                time.sleep(args.delay)
    raise SystemExit(f"live dashboard verification failed: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
