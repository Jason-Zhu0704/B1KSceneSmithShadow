#!/usr/bin/env python3
"""Reconstruct OG scene from shadow manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def dry_run(manifest: dict) -> None:
    objs = manifest.get("objects", [])
    print(f"scene_name: {manifest.get('scene_name')}")
    print(f"objects: {len(objs)}")
    for row in objs[:10]:
        print(
            f"- {row.get('name')} | {row.get('category')}/{row.get('model')} "
            f"pos={row.get('pos')}"
        )


def execute(manifest: dict, settle_steps: int) -> None:
    import omnigibson as og
    from omnigibson.objects import DatasetObject

    env = og.Environment(configs={"scene": {"type": "Scene"}})
    for row in manifest.get("objects", []):
        obj = DatasetObject(
            name=row["name"],
            category=row["category"],
            model=row["model"],
        )
        og.sim.import_object(obj)
        obj.set_position_orientation(row.get("pos", [0, 0, 0]), row.get("quat_xyzw", [0, 0, 0, 1]))
        joints = row.get("joints") or {}
        if joints:
            ordered = [joints[k] for k in sorted(joints.keys())]
            try:
                obj.set_joint_positions(ordered)
            except Exception:
                pass
    for _ in range(settle_steps):
        og.sim.step()
    print(f"OG reconstruction done, settle_steps={settle_steps}")
    env.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct OmniGibson scene from shadow manifest")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--execute", action="store_true", help="Actually launch OG and import objects")
    parser.add_argument("--settle-steps", type=int, default=20)
    args = parser.parse_args()

    with open(Path(args.manifest), "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if not args.execute:
        dry_run(manifest)
        return
    execute(manifest, settle_steps=args.settle_steps)


if __name__ == "__main__":
    main()

