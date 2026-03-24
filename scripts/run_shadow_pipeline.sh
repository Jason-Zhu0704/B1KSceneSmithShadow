#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <prompt> <output_dir>"
  exit 1
fi

PROMPT="$1"
OUT_DIR="$2"
shift 2

bash /root/B1KSceneSmithShadow/scripts/run_shadow_main.sh \
  "$PROMPT" \
  "$OUT_DIR" \
  "$@"
