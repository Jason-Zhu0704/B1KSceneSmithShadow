#!/usr/bin/env python3
"""Build CLIP embeddings for B1K text descriptions + OG visualization images."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import torch
from PIL import Image

import open_clip


def l2_normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True) + 1e-8
    return x / n


def read_descriptions(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
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


def select_visual_image(asset_dir: Path, view_priority: list[str]) -> Path | None:
    vis_dir = asset_dir / "visualizations"
    if not vis_dir.exists():
        return None
    for view in view_priority:
        cand = vis_dir / f"{view}.png"
        if cand.exists():
            return cand
    pngs = sorted(vis_dir.glob("*.png"))
    return pngs[0] if pngs else None


def collect_assets(
    og_objects_root: Path,
    descriptions: dict[str, str],
    limit: int | None,
    require_description: bool,
    view_priority: list[str],
) -> list[dict]:
    rows: list[dict] = []
    for category_dir in sorted(og_objects_root.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name
        for model_dir in sorted(category_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            model = model_dir.name
            asset_id = f"{category}/{model}"
            if require_description and asset_id not in descriptions:
                continue
            img = select_visual_image(model_dir, view_priority)
            if img is None:
                continue
            rows.append(
                {
                    "asset_id": asset_id,
                    "category": category,
                    "model": model,
                    "description": descriptions.get(asset_id, category.replace("_", " ")),
                    "image_path": str(img),
                }
            )
            if limit and len(rows) >= limit:
                return rows
    return rows


def build_embeddings(
    rows: list[dict],
    model_name: str,
    pretrained: str,
    device: str,
    batch_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name, pretrained=pretrained, device=device
    )
    tokenizer = open_clip.get_tokenizer(model_name)
    model.eval()

    text_vecs: list[np.ndarray] = []
    image_vecs: list[np.ndarray] = []

    with torch.no_grad():
        for i in range(0, len(rows), batch_size):
            chunk = rows[i : i + batch_size]
            texts = [r["description"] for r in chunk]
            imgs = [preprocess(Image.open(r["image_path"]).convert("RGB")) for r in chunk]

            toks = tokenizer(texts).to(device)
            img_tensor = torch.stack(imgs, dim=0).to(device)

            t = model.encode_text(toks)
            v = model.encode_image(img_tensor)
            t = t / t.norm(dim=-1, keepdim=True)
            v = v / v.norm(dim=-1, keepdim=True)

            text_vecs.append(t.cpu().numpy().astype(np.float32))
            image_vecs.append(v.cpu().numpy().astype(np.float32))

    return np.vstack(text_vecs), np.vstack(image_vecs)


def maybe_write_faiss(vecs: np.ndarray, out_prefix: Path) -> None:
    try:
        import faiss  # type: ignore
    except Exception:
        print("faiss not installed, skip FAISS index")
        return
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs.astype(np.float32))
    faiss.write_index(index, str(out_prefix.with_suffix(".faiss")))
    print(f"Wrote FAISS index: {out_prefix.with_suffix('.faiss')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build multimodal CLIP index for B1K assets")
    parser.add_argument(
        "--descriptions",
        default="/root/sgpromax/patch-of-behavior-1k/asset_descriptions.jsonl",
    )
    parser.add_argument(
        "--og-objects-root",
        default="/root/.omnigibson/datasets/objects",
    )
    parser.add_argument("--out-prefix", required=True, help="e.g. data/b1k_clip_mm")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--model-name", default="ViT-B-32")
    parser.add_argument("--pretrained", default="laion2b_s34b_b79k")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument(
        "--image-views",
        default="perspective,front,left,right,top,back",
        help="priority list for visualization image names",
    )
    parser.add_argument(
        "--allow-missing-description",
        action="store_true",
        help="use category text when description is missing",
    )
    args = parser.parse_args()

    desc_path = Path(args.descriptions)
    og_root = Path(args.og_objects_root)
    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    views = [x.strip() for x in args.image_views.split(",") if x.strip()]

    descriptions = read_descriptions(desc_path)
    rows = collect_assets(
        og_root,
        descriptions=descriptions,
        limit=args.limit,
        require_description=not args.allow_missing_description,
        view_priority=views,
    )
    if not rows:
        raise RuntimeError("No assets collected. Check paths / filters.")

    print(f"Collected assets: {len(rows)}")
    text_emb, img_emb = build_embeddings(
        rows,
        model_name=args.model_name,
        pretrained=args.pretrained,
        device=args.device,
        batch_size=args.batch_size,
    )
    fused_emb = l2_normalize(0.5 * text_emb + 0.5 * img_emb).astype(np.float32)

    npz_path = out_prefix.with_suffix(".npz")
    np.savez_compressed(
        npz_path,
        asset_ids=np.array([r["asset_id"] for r in rows], dtype=object),
        categories=np.array([r["category"] for r in rows], dtype=object),
        models=np.array([r["model"] for r in rows], dtype=object),
        descriptions=np.array([r["description"] for r in rows], dtype=object),
        image_paths=np.array([r["image_path"] for r in rows], dtype=object),
        text_embeddings=text_emb.astype(np.float32),
        image_embeddings=img_emb.astype(np.float32),
        fused_embeddings=fused_emb.astype(np.float32),
        model_name=args.model_name,
        pretrained=args.pretrained,
    )
    print(f"Wrote embeddings: {npz_path}")

    meta_path = out_prefix.with_suffix(".meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "count": len(rows),
                "model_name": args.model_name,
                "pretrained": args.pretrained,
                "device": args.device,
                "descriptions_path": str(desc_path),
                "og_objects_root": str(og_root),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Wrote metadata: {meta_path}")

    maybe_write_faiss(fused_emb, out_prefix)


if __name__ == "__main__":
    main()

