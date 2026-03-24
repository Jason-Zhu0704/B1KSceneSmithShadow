#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <scene_json> <output_dir>"
  echo "Example: $0 /root/SmithPlusOmnigibson/outputs/b1k_mesh_drake_16/scene_000/omnigibson_scene_preserve.json /root/B1KSceneSmithShadow/runs/shot_001"
  exit 1
fi

SCENE_JSON="$1"
OUT_DIR="$2"
SCRIPT="/root/B1KSceneSmithShadow/scripts/scene_screenshot.py"

mkdir -p "$OUT_DIR"
python3 "$SCRIPT" --scene "$SCENE_JSON" --output-dir "$OUT_DIR"
