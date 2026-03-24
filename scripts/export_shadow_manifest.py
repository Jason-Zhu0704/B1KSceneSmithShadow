#!/usr/bin/env python3
"""Export a compact scene manifest for OG reconstruction from preserve JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export shadow manifest from omnigibson_scene_preserve.json")
    parser.add_argument("--scene", required=True, help="Path to omnigibson_scene_preserve.json")
    parser.add_argument("--out", required=True, help="Output manifest path")
    parser.add_argument(
        "--z-offset",
        type=float,
        default=0.0,
        help="Global Z offset for USD origin alignment",
    )
    args = parser.parse_args()

    scene_path = Path(args.scene)
    with open(scene_path, "r", encoding="utf-8") as f:
        scene = json.load(f)

    object_registry = (
        scene.get("state", {})
        .get("registry", {})
        .get("object_registry", {})
    )
    object_init = scene.get("objects_info", {}).get("init_info", {})

    objects: list[dict] = []
    for name, state in object_registry.items():
        init = object_init.get(name, {})
        init_args = init.get("args", {})
        rl = state.get("root_link", {})
        pos = list(rl.get("pos", [0.0, 0.0, 0.0]))
        if len(pos) == 3:
            pos[2] = float(pos[2]) + float(args.z_offset)
        item = {
            "name": name,
            "category": init_args.get("category"),
            "model": init_args.get("model"),
            "pos": pos,
            "quat_xyzw": rl.get("ori", [0.0, 0.0, 0.0, 1.0]),
            "joints": state.get("joints", {}),
            "fixed_base": bool(init_args.get("fixed_base", False)),
            "in_rooms": init_args.get("in_rooms", []),
        }
        objects.append(item)

    manifest = {
        "source_scene": str(scene_path),
        "scene_name": scene.get("metadata", {}).get("scene_name", scene_path.stem),
        "objects": objects,
        "drake_structures": scene.get("metadata", {}).get("drake_structures", []),
        "meta": {
            "total_objects": len(objects),
            "z_offset": args.z_offset,
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Wrote manifest: {out_path} ({len(objects)} objects)")


if __name__ == "__main__":
    main()

