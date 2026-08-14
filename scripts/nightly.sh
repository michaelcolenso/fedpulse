#!/usr/bin/env bash
# FedPulse v0.2 nightly pipeline. FR is daily; MARC maintenance is periodic.
set -u
cd "$HOME/projects/fedpulse" || exit 1
UV="/home/linuxbrew/.linuxbrew/bin/uv"
if [[ ! -x "$UV" ]]; then
  echo "FedPulse: required uv not found at $UV" >&2
  exit 1
fi
export PATH="$HOME/.local/bin:$PATH"
PYTHONPATH=src "$UV" run python -m fedpulse.pipeline_v2 "$@"
