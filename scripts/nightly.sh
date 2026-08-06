#!/usr/bin/env bash
# FedPulse nightly pipeline — FR daily pull → MARC monthly check → indices → digest.
# Silent when network is unavailable (nothing to do, don't alarm anyone).
set -u
cd "$HOME/projects/fedpulse" || exit 1

# Gate: if we can't reach the FR API, skip quietly (network still blocked?).
if ! curl -s --max-time 10 -o /dev/null "https://www.federalregister.gov/api/v1/documents.json?per_page=1"; then
  exit 0
fi

export PATH="$HOME/.local/bin:$PATH"

# 1) Daily FR pull (last 3 days — FR publishes weekday mornings; this catches
#    weekends/holidays in one go without double-processing).
PYTHONPATH=src uv run python -m fedpulse.ingest fr --days 3 || exit 1

# 2) MARC monthly check: look for a new monthly file on GitHub (cheap ls-remote;
#    GPO pushes monthly New/Changed/Deleted files). Download+ingest if newer.
PYTHONPATH=src uv run python -m fedpulse.marc_sync || true

# 3) Recompute indices + emit daily digest (silent when nothing flagged).
PYTHONPATH=src uv run python -m fedpulse.indices || exit 1
PYTHONPATH=src uv run python -m fedpulse.digest
exit 0
