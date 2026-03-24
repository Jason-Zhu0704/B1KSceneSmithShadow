#!/usr/bin/env python3
"""Shadow Asset Proxy: text query -> B1K proxy asset metadata."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import numpy as np


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


class ShadowAssetProxy:
    """Retrieves B1K assets and returns visual/collision proxy file paths."""

    def __init__(
        self,
        embeddings: str | Path | None = None,
        descriptions: str | Path | None = None,
        drake_assets: str | Path | None = None,
    ):
        self.embeddings_path = Path(
            embeddings
            or os.environ.get(
                "B1K_EMBEDDINGS",
                "/root/B1KSceneSmithShadow/data/b1k_text_clip_index_full8662.npz",
            )
        )
        self.descriptions_path = Path(
            descriptions
            or os.environ.get(
                "B1K_DESCRIPTIONS",
                "/root/sgpromax/patch-of-behavior-1k/asset_descriptions.jsonl",
            )
        )
        self.drake_assets = Path(
            drake_assets
            or os.environ.get(
                "B1K_DRAKE_ASSETS_ROOT",
                "/root/SmithPlusOmnigibson/b1k_drake_assets",
            )
        )
        self.asset_ids: list[str] = []
        self.categories: list[str] = []
        self.descriptions: dict[str, str] = {}
        self.embedding_matrix: np.ndarray | None = None
        self.drake_index: dict[str, dict] = {}

    def load(self) -> None:
        if self.embeddings_path.exists():
            data = np.load(self.embeddings_path, allow_pickle=True)
            self.asset_ids = [str(x) for x in data["asset_ids"].tolist()]
            if "categories" in data:
                self.categories = [str(x) for x in data["categories"].tolist()]
            else:
                self.categories = [aid.split("/", 1)[0] if "/" in aid else aid.split("-", 1)[0] for aid in self.asset_ids]
            if "text_embeddings" in data:
                emb = data["text_embeddings"].astype(np.float32)
                norms = np.linalg.norm(emb, axis=1, keepdims=True) + 1e-8
                self.embedding_matrix = emb / norms

        if self.descriptions_path.exists():
            with open(self.descriptions_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    aid = row.get("asset_id")
                    if aid:
                        self.descriptions[aid] = str(row.get("description", "")).strip()

        index_file = self.drake_assets / "index.json"
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                self.drake_index = json.load(f)

    def _lookup_proxy_paths(self, asset_id: str) -> tuple[str | None, str | None, list[float] | None]:
        category, model = self.parse_asset_id(asset_id)
        key = f"{category}-{model}"
        entry = self.drake_index.get(key, {})
        visual = entry.get("visual_obj")
        collision = entry.get("collision_obj")
        bbox = None
        lb = entry.get("link_bboxes", {}).get("base_link", {})
        ext = lb.get("visual_extent") or entry.get("bbox_size")
        if isinstance(ext, list) and len(ext) >= 3:
            bbox = [float(ext[0]), float(ext[1]), float(ext[2])]

        if not visual:
            fallback = self.drake_assets / "objects" / category / model / "visual.obj"
            if fallback.exists():
                visual = str(fallback)
        if not collision:
            fallback = self.drake_assets / "objects" / category / model / "collision.obj"
            if fallback.exists():
                collision = str(fallback)
        if not collision and visual:
            collision = visual
        return visual, collision, bbox

    @staticmethod
    def parse_asset_id(asset_id: str) -> tuple[str, str]:
        if "/" in asset_id:
            category, model = asset_id.split("/", 1)
            return category, model
        category, model = asset_id.split("-", 1)
        return category, model

    def _lexical_score(self, query: str, idx: int) -> float:
        aid = self.asset_ids[idx]
        desc = self.descriptions.get(aid, "")
        cat = self.categories[idx] if idx < len(self.categories) else ""
        q = _tokenize(query)
        doc = _tokenize(desc) | _tokenize(cat.replace("_", " "))
        if not q:
            return 0.0
        overlap = len(q & doc)
        return overlap / max(1, len(q))

    def retrieve(self, query: str, topk: int = 5, category_hint: str | None = None) -> list[dict]:
        if not self.asset_ids:
            raise RuntimeError("No assets loaded. Call load() first.")

        candidate_idxs = list(range(len(self.asset_ids)))
        if category_hint:
            filtered = [i for i in candidate_idxs if self.categories[i] == category_hint]
            if filtered:
                candidate_idxs = filtered

        scored: list[tuple[int, float]] = []
        for i in candidate_idxs:
            s = self._lexical_score(query, i)
            scored.append((i, s))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for i, score in scored[:topk]:
            aid = self.asset_ids[i]
            category, model = self.parse_asset_id(aid)
            visual, collision, bbox = self._lookup_proxy_paths(aid)
            results.append(
                {
                    "asset_id": aid,
                    "category": category,
                    "model": model,
                    "description": self.descriptions.get(aid, ""),
                    "score": float(score),
                    "proxy_visual_obj": visual,
                    "proxy_collision_obj": collision,
                    "bbox_size_m": bbox,
                }
            )
        return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Query B1K shadow asset proxy")
    parser.add_argument("--query", required=True, help="Text query")
    parser.add_argument("--topk", type=int, default=5)
    parser.add_argument("--category", default=None)
    args = parser.parse_args()

    proxy = ShadowAssetProxy()
    proxy.load()
    rows = proxy.retrieve(args.query, topk=args.topk, category_hint=args.category)
    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
