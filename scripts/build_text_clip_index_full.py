#!/usr/bin/env python3
"""Build full 8662 text-embedding index by filling missing entries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch


def l2_normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True) + 1e-8
    return x / n


def load_descriptions(jsonl_path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            aid = row.get("asset_id")
            cat = row.get("category")
            model = row.get("model")
            if not aid or not cat or not model:
                continue
            rows.append(row)
    return rows


def build_existing_map(src_npz: Path) -> dict[str, np.ndarray]:
    data = np.load(src_npz, allow_pickle=True)
    ids = data["asset_ids"].astype(str)
    embs = data["text_embeddings"].astype(np.float32)
    out: dict[str, np.ndarray] = {}
    for i, aid in enumerate(ids):
        if aid in out:
            continue
        out[aid] = embs[i]
    return out


def encode_missing(
    rows_missing: list[dict],
    model_name: str,
    pretrained: str,
    device: str,
    batch_size: int,
) -> dict[str, np.ndarray]:
    import open_clip

    model, _, _ = open_clip.create_model_and_transforms(
        model_name, pretrained=pretrained, device=device
    )
    tokenizer = open_clip.get_tokenizer(model_name)
    model.eval()

    result: dict[str, np.ndarray] = {}
    with torch.no_grad():
        for i in range(0, len(rows_missing), batch_size):
            batch = rows_missing[i : i + batch_size]
            texts = []
            for r in batch:
                cat = str(r.get("category", "")).replace("_", " ")
                desc = str(r.get("description", "")).strip()
                texts.append(f"{cat}: {desc}" if desc else cat)
            tokens = tokenizer(texts).to(device)
            vec = model.encode_text(tokens)
            vec = vec / vec.norm(dim=-1, keepdim=True)
            vec = vec.cpu().numpy().astype(np.float32)
            for j, r in enumerate(batch):
                result[str(r["asset_id"])] = vec[j]
            print(f"encoded {min(i + batch_size, len(rows_missing))}/{len(rows_missing)}", flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build full text-only B1K index (8662)")
    parser.add_argument("--src-npz", default="/root/sgpromax/asset_embeddings.npz")
    parser.add_argument("--descriptions-jsonl", default="/root/sgpromax/patch-of-behavior-1k/asset_descriptions.jsonl")
    parser.add_argument("--out-prefix", required=True)
    parser.add_argument("--model-name", default="ViT-H-14-378-quickgelu")
    parser.add_argument("--pretrained", default="dfn5b")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    desc_rows = load_descriptions(Path(args.descriptions_jsonl))
    existing_map = build_existing_map(Path(args.src_npz))

    missing_rows = [r for r in desc_rows if str(r["asset_id"]) not in existing_map]
    print(f"description_rows={len(desc_rows)} existing_unique={len(existing_map)} missing={len(missing_rows)}")

    missing_map: dict[str, np.ndarray] = {}
    if missing_rows:
        missing_map = encode_missing(
            missing_rows,
            model_name=args.model_name,
            pretrained=args.pretrained,
            device=args.device,
            batch_size=args.batch_size,
        )

    asset_ids = []
    categories = []
    models = []
    descriptions = []
    emb_list = []
    for r in desc_rows:
        aid = str(r["asset_id"])
        emb = existing_map.get(aid)
        if emb is None:
            emb = missing_map[aid]
        asset_ids.append(aid)
        categories.append(str(r["category"]))
        models.append(str(r["model"]))
        descriptions.append(str(r.get("description", "")).strip())
        emb_list.append(emb)

    text_embeddings = l2_normalize(np.stack(emb_list).astype(np.float32))
    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    out_npz = out_prefix.with_suffix(".npz")
    np.savez_compressed(
        out_npz,
        asset_ids=np.array(asset_ids, dtype=object),
        categories=np.array(categories, dtype=object),
        models=np.array(models, dtype=object),
        descriptions=np.array(descriptions, dtype=object),
        text_embeddings=text_embeddings,
    )
    out_meta = out_prefix.with_suffix(".meta.json")
    with open(out_meta, "w", encoding="utf-8") as f:
        json.dump(
            {
                "count": len(asset_ids),
                "dim": int(text_embeddings.shape[1]),
                "existing_unique": len(existing_map),
                "filled_missing": len(missing_rows),
                "model_name": args.model_name,
                "pretrained": args.pretrained,
                "device": args.device,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Wrote: {out_npz}")
    print(f"Wrote: {out_meta}")


if __name__ == "__main__":
    main()

