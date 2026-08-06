"""Daily digest — prints a compact signal brief, or NOTHING when there are no flags.

Used by the nightly cron as a silent watchdog: empty stdout = nothing to report.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "data" / "outputs"

def main() -> int:
    lines: list[str] = []
    try:
        api = json.loads((OUT / "api.json").read_text())
        rcr = json.loads((OUT / "rcr.json").read_text())
        ter = json.loads((OUT / "ter.json").read_text())
    except FileNotFoundError:
        return 0  # nothing ingested yet — stay silent
    except json.JSONDecodeError:
        print("FEDPULSE: outputs corrupted")
        return 1

    flagged_api = [a for a in api.get("agencies", []) if a.get("flagged")]
    flagged_rcr = [a for a in rcr.get("agencies", []) if a.get("flagged")]
    new_subj = ter.get("new_subjects", [])
    accel_subj = ter.get("accelerating_subjects", [])[:5]

    if not (flagged_api or flagged_rcr or new_subj or accel_subj):
        return 0  # quiet night

    lines.append("🔴 FEDPULSE DAILY SIGNAL — " + api.get("as_of", ""))
    if flagged_api:
        lines.append("\n⚡ AGENCY PULSE (z≥2.5):")
        for a in flagged_api[:8]:
            lines.append(f"  • {a['agency']}: z={a['z_score']} ({a['current_count']} rec this week)")
    if flagged_rcr:
        lines.append("\n🔄 CHURN (≥5:1, 12-mo):")
        for a in flagged_rcr[:8]:
            lines.append(f"  • {a['agency']}: {a['churn_ratio']}:1 ({a['proposed_rules']} prop / {a['notices']} notices / {a['final_rules']} final)")
    if new_subj:
        lines.append("\n🆕 NEW SUBJECTS (30d):")
        for s in new_subj[:10]:
            lines.append(f"  • {s['subject']} — first {s['first_seen']} ({s.get('agency') or 'n/a'})")
    if accel_subj:
        lines.append("\n📈 ACCELERATING:")
        for s in accel_subj:
            lines.append(f"  • {s['subject']} ×{s['multiple']} (last4w {s['last_4w_count']})")

    print("\n".join(lines))
    return 0

if __name__ == "__main__":
    sys.exit(main())
