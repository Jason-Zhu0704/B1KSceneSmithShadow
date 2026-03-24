#!/usr/bin/env python3
"""Build a compact shadow catalog from existing B1K drake assets + descriptions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def load_descriptions(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            aid = row.get("asset_id")
            if aid:
                out[str(aid)] = str(row.get("description", "")).strip()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare B1K shadow asset catalog")
    parser.add_argument(
        "--drake-index",
        default=os.environ.get("B1K_DRAKE_ASSETS_ROOT", "/root/SmithPlusOmnigibson/b1k_drake_assets") + "/index.json",
    )
    parser.add_argument(
        "--descriptions",
        default=os.environ.get("B1K_DESCRIPTIONS", "/root/sgpromax/patch-of-behavior-1k/asset_descriptions.jsonl"),
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    drake_index = Path(args.drake_index)
    if not drake_index.exists():
        raise FileNotFoundError(f"Drake index not found: {drake_index}")

    with open(drake_index, "r", encoding="utf-8") as f:
        index = json.load(f)
    descriptions = load_descriptions(Path(args.descriptions))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for key, entry in index.items():
            if "-" not in key:
                continue
            category, model = key.split("-", 1)
            aid_slash = f"{category}/{model}"
            lb = entry.get("link_bboxes", {}).get("base_link", {})
            bbox = lb.get("visual_extent") or entry.get("bbox_size")
            row = {
                "asset_id": aid_slash,
                "asset_key": key,
                "category": category,
                "model": model,
                "description": descriptions.get(aid_slash, ""),
                "proxy_visual_obj": entry.get("visual_obj"),
                "proxy_collision_obj": entry.get("collision_obj"),
                "bbox_size_m": bbox,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1

    print(f"Wrote {n} rows to {out_path}")


if __name__ == "__main__":
    main()

