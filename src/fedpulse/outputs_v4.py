"""v0.4 additive lifecycle output layered onto the stable schema-v2 snapshot."""
from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from pathlib import Path

from .outputs_v2 import atomic_write_json
from .regulatory_lifecycle import build_lifecycles

OUTPUT_NAME = "regulatory_lifecycles"


def publish_regulatory_lifecycle_output(conn, as_of: str, out_dir: Path, now: dt.datetime) -> dict:
    """Add lifecycle JSON to the activated generation before external KV publication.

    The v0.3 seven-file contract remains untouched; this additive file uses the
    exact health snapshot metadata so Cloudflare's generation publisher can
    validate it as part of the same external atomic generation.
    """
    out_dir = Path(out_dir)
    health_path = out_dir / "current" / "health.json"
    health = json.loads(health_path.read_text())
    items = build_lifecycles(conn, as_of)
    payload = {
        "schema_version": 2,
        "generated_at": health.get("generated_at"),
        "generated_at_timezone": "UTC",
        "as_of": health.get("as_of"),
        "as_of_timezone": "America/New_York",
        "source_freshness": health.get("source_freshness", {}),
        "items": items,
    }
    target = out_dir / "current" / f"{OUTPUT_NAME}.json"
    atomic_write_json(target, payload)
    link_tmp = out_dir / f".{OUTPUT_NAME}.{uuid.uuid4().hex}.tmp"
    os.symlink(Path("current") / f"{OUTPUT_NAME}.json", link_tmp)
    os.replace(link_tmp, out_dir / f"{OUTPUT_NAME}.json")
    return payload
