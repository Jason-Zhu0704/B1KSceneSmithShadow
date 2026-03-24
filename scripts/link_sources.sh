#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/B1KSceneSmithShadow"

ln -sfn /root/SmithPlusOmnigibson/b1k_drake_assets "$ROOT/b1k_drake_assets"
ln -sfn /root/sgpromax/patch-of-behavior-1k "$ROOT/patch-of-behavior-1k"
ln -sfn /root/.omnigibson "$ROOT/omnigibson_dataset"
ln -sfn /root/SmithPlusOmnigibson/scene_screenshot.py "$ROOT/scripts/scene_screenshot.py"

echo "Linked sources under: $ROOT"
ls -la "$ROOT" | sed -n '1,120p'

