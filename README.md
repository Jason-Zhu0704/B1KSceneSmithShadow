# B1K + SceneSmith Shadow Asset Proxy

这个目录是独立重开的工作区，用于按你给的方案做 B1K 融合，不改 SceneSmith 核心源码。

## 目标
- SceneSmith 内部使用 B1K 的 `OBJ` / collision proxy 跑布局和物理。
- 最终在 OmniGibson 使用 B1K 原生 USD 还原场景。
- 通过外挂脚本和环境变量接入，不改 `/data/scenesmith`。

## 目录
- `configs/shadow_proxy.env.example`: 环境变量模板。
- `shadow_proxy/asset_proxy.py`: Shadow 检索代理（文本 -> B1K 资产+代理网格）。
- `scripts/prepare_shadow_assets.py`: 生成三位一体资产目录（语义+视觉+物理信息汇总）。
- `scripts/clip_b1k_multimodal_index.py`: 用 CLIP 编码 description + OG 资产渲染图。
- `scripts/export_shadow_manifest.py`: 从 `omnigibson_scene_preserve.json` 导出闭环清单。
- `scripts/reconstruct_og_from_manifest.py`: 在 OG 中按清单重建（含 dry-run）。
- `scripts/run_shadow_pipeline.sh`: 用新工作区一键触发现有 SceneSmith-B1K 管线。
- `scripts/run_shadow_main.sh`: Shadow 固定主入口（强制注入 full8662 索引并自动导出 manifest）。
- `scripts/run_og_screenshot.sh`: 调用 `scene_screenshot.py` 对 OG 场景截图。
- `scripts/link_sources.sh`: 把原始数据源软链接到新目录。

## 快速开始
```bash
cd /root/B1KSceneSmithShadow
cp configs/shadow_proxy.env.example .env
bash scripts/link_sources.sh

# 1) 准备资产索引
python3 scripts/prepare_shadow_assets.py \
  --out data/shadow_asset_catalog.jsonl

# 1.1) 生成 8662 全覆盖文本 embedding（推荐默认）
HF_HUB_OFFLINE=1 python3 scripts/build_text_clip_index_full.py \
  --out-prefix /root/B1KSceneSmithShadow/data/b1k_text_clip_index_full8662 \
  --device cpu

# 2) 跑 SceneSmith（Shadow 固定主入口）
bash scripts/run_shadow_main.sh \
  "A compact bedroom with one bed and one nightstand." \
  /root/B1KSceneSmithShadow/runs/bedroom_shadow_001

# 3) 导出闭环 manifest
python3 scripts/export_shadow_manifest.py \
  --scene /root/B1KSceneSmithShadow/runs/bedroom_shadow_001/scene_000/omnigibson_scene_preserve.json \
  --out /root/B1KSceneSmithShadow/runs/bedroom_shadow_001/scene_000/shadow_manifest.json

# 4) OG 重建（先 dry-run，再 execute）
python3 scripts/reconstruct_og_from_manifest.py \
  --manifest /root/B1KSceneSmithShadow/runs/bedroom_shadow_001/scene_000/shadow_manifest.json

# 5) OG 截图
bash scripts/run_og_screenshot.sh \
  /root/SmithPlusOmnigibson/outputs/b1k_mesh_drake_16/scene_000/omnigibson_scene_preserve.json \
  /root/B1KSceneSmithShadow/runs/shot_001
```

## 备注
- 现在默认先做可落地骨架，和你现有 `b1k_drake_assets`、`omnigibson_scene_preserve.json` 对齐。
- 坐标系偏移（USD 原点 vs Drake 原点）在 manifest 阶段可做统一 `z_offset` 修正。
- Shadow 代理默认读取：`/root/B1KSceneSmithShadow/data/b1k_text_clip_index_full8662.npz`。
