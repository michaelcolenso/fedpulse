"""Daily v0.2 digest reader. Legacy-only output is an explicit compatibility error."""
from __future__ import annotations
import json
import sys
from pathlib import Path

OUT=Path(__file__).resolve().parents[2]/"data"/"outputs"

def load_brief(path: Path | None = None) -> dict:
    path=path or OUT/"brief.json"
    try: payload=json.loads(path.read_text())
    except FileNotFoundError as exc: raise RuntimeError("FedPulse v0.2 brief.json is missing; legacy outputs are not accepted") from exc
    except json.JSONDecodeError as exc: raise RuntimeError("FedPulse v0.2 brief.json is corrupted") from exc
    if payload.get("schema_version") != 2: raise RuntimeError("FedPulse v0.2 requires schema_version=2 brief.json")
    return payload

def main() -> int:
    try: brief=load_brief()
    except RuntimeError as exc: print(f"FEDPULSE: {exc}"); return 1
    from .outputs_v2 import render_text_brief
    print(render_text_brief(brief),end="")
    return 0

if __name__=="__main__": sys.exit(main())
