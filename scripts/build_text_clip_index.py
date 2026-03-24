#!/usr/bin/env python3
"""Build text-only retrieval index from existing B1K CLIP embeddings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def l2_normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True) + 1e-8
    return x / n


def main() -> None:
    parser = argparse.ArgumentParser(description="Build text-only CLIP index from asset_embeddings.npz")
    parser.add_argument(
        "--src-npz",
        default="/root/sgpromax/asset_embeddings.npz",
        help="Source NPZ with text_embeddings",
    )
    parser.add_argument(
        "--descriptions-jsonl",
        default="/root/sgpromax/patch-of-behavior-1k/asset_descriptions.jsonl",
    )
    parser.add_argument("--out-prefix", required=True, help="e.g. /root/B1KSceneSmithShadow/data/b1k_text_clip")
    args = parser.parse_args()

    src = np.load(args.src_npz, allow_pickle=True)
    text_embeddings = src["text_embeddings"].astype(np.float32)
    asset_ids = src["asset_ids"].astype(str)
    categories = src["categories"].astype(str)
    models = src["models"].astype(str)

    # De-duplicate by asset_id, keep first occurrence to avoid retrieval bias.
    first_idx: dict[str, int] = {}
    keep: list[int] = []
    for i, aid in enumerate(asset_ids):
        if aid in first_idx:
            continue
        first_idx[aid] = i
        keep.append(i)
    if len(keep) != len(asset_ids):
        print(f"De-duplicated: {len(asset_ids)} -> {len(keep)} rows")
    asset_ids = asset_ids[keep]
    categories = categories[keep]
    models = models[keep]
    text_embeddings = text_embeddings[keep]

    desc_map: dict[str, str] = {}
    desc_path = Path(args.descriptions_jsonl)
    if desc_path.exists():
        with open(desc_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                aid = row.get("asset_id")
                if aid:
                    desc_map[str(aid)] = str(row.get("description", "")).strip()

    descriptions = np.array([desc_map.get(aid, "") for aid in asset_ids], dtype=object)
    text_embeddings = l2_normalize(text_embeddings)

    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    out_npz = out_prefix.with_suffix(".npz")
    np.savez_compressed(
        out_npz,
        asset_ids=asset_ids,
        categories=categories,
        models=models,
        descriptions=descriptions,
        text_embeddings=text_embeddings,
    )
    print(f"Wrote: {out_npz} | count={len(asset_ids)} dim={text_embeddings.shape[1]}")

    meta = {
        "count": int(len(asset_ids)),
        "dim": int(text_embeddings.shape[1]),
        "source_npz": str(args.src_npz),
        "descriptions_jsonl": str(args.descriptions_jsonl),
    }
    out_meta = out_prefix.with_suffix(".meta.json")
    with open(out_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"Wrote: {out_meta}")

    try:
        import faiss  # type: ignore
    except Exception:
        print("faiss not installed, skip FAISS index")
        return

    index = faiss.IndexFlatIP(text_embeddings.shape[1])
    index.add(text_embeddings.astype(np.float32))
    out_faiss = out_prefix.with_suffix(".faiss")
    faiss.write_index(index, str(out_faiss))
    print(f"Wrote: {out_faiss}")


if __name__ == "__main__":
    main()
