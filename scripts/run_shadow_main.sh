#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <prompt> <output_dir> [extra run.py args]"
  exit 1
fi

PROMPT="$1"
OUT_DIR="$2"
shift 2

ROOT="/root/B1KSceneSmithShadow"
SMITHPLUS="/root/SmithPlusOmnigibson"
export PATH="$ROOT/bin:$PATH"

# Fixed shadow entry configuration.
export B1K_DRAKE_ASSETS_ROOT="${B1K_DRAKE_ASSETS_ROOT:-$ROOT/b1k_drake_assets}"
export B1K_DESCRIPTIONS="${B1K_DESCRIPTIONS:-$ROOT/patch-of-behavior-1k/asset_descriptions.jsonl}"
export B1K_EMBEDDINGS="${B1K_EMBEDDINGS:-$ROOT/data/b1k_text_clip_index_full8662.npz}"
export B1K_RETRIEVAL_BACKEND="${B1K_RETRIEVAL_BACKEND:-clip}"
export SCENESMITH_PRESERVE_DRAKE_POSE="${SCENESMITH_PRESERVE_DRAKE_POSE:-1}"

mkdir -p "$OUT_DIR"

echo "[shadow] cleanup stale retrieval/blender processes"
pkill -f '/root/SmithPlusOmnigibson/src/optimized_server.py' 2>/dev/null || true
pkill -f 'articulated_retrieval_server' 2>/dev/null || true
pkill -f 'materials_retrieval_server' 2>/dev/null || true
pkill -f 'standalone_server.py' 2>/dev/null || true
for p in 7006 7007 7008; do
  fuser -k ${p}/tcp 2>/dev/null || true
done

echo "[shadow] run.py start"
echo "[shadow] B1K_EMBEDDINGS=$B1K_EMBEDDINGS"
bash "$SMITHPLUS/scripts/run_with_env.sh" \
  --prompt "$PROMPT" \
  --output-dir "$OUT_DIR" \
  "$@"

echo "[shadow] export manifests"
for scene_dir in "$OUT_DIR"/scene_*; do
  [[ -d "$scene_dir" ]] || continue
  scene_json="$scene_dir/omnigibson_scene_preserve.json"
  if [[ ! -f "$scene_json" ]]; then
    scene_json="$scene_dir/omnigibson_scene.json"
  fi
  if [[ ! -f "$scene_json" ]]; then
    echo "[shadow] skip $scene_dir (no omnigibson scene json)"
    continue
  fi
  python3 "$ROOT/scripts/export_shadow_manifest.py" \
    --scene "$scene_json" \
    --out "$scene_dir/shadow_manifest.json"
done

echo "[shadow] done: $OUT_DIR"
