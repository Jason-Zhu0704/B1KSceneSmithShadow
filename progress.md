# B1KSceneSmithShadow Progress

## 更新时间
- 2026-03-20 (Asia/Shanghai)

## 今日完成
1. Shadow 代理默认索引切换为 8662 全覆盖文本 embedding：
   - `/root/B1KSceneSmithShadow/data/b1k_text_clip_index_full8662.npz`
2. 完成 8662 文本 embedding 索引构建与补齐：
   - `existing_unique=7670`
   - `filled_missing=992`
   - `final=8662`
3. 接入主流程固定入口：
   - 新增 `/root/B1KSceneSmithShadow/scripts/run_shadow_main.sh`
   - `run_shadow_pipeline.sh` 已转发到主入口
4. 打通 SceneSmith -> B1K server 参数传递：
   - `/root/SmithPlusOmnigibson/src/server_launcher.py` 支持 `B1K_EMBEDDINGS/B1K_DESCRIPTIONS`
   - `/root/SmithPlusOmnigibson/src/optimized_server.py` 真正读取 embeddings/descriptions 参数
5. 修复 B1K server 读取 full8662 索引报错：
   - `/root/SmithPlusOmnigibson/src/custom_retrieval.py` 改为 `np.load(..., allow_pickle=True)`
6. 修复运行中端口残留问题：
   - 主入口增加 stale process 清理 + 7006/7007/7008 端口清理
7. 为避免 bwrap 权限报错，增加 Shadow 本地 shim：
   - `/root/B1KSceneSmithShadow/bin/bwrap`
   - 主入口 `PATH` 已优先包含 `$ROOT/bin`

## 今日运行结果
尝试端到端运行：
- `runs/bedroom_shadow_main_001`：
  - 修复前：B1K server 启动失败（npz allow_pickle 问题）
- `runs/bedroom_shadow_main_002` / `003`：
  - 修复后：B1K server ready
  - 失败点：7007 端口被旧进程占用
- `runs/bedroom_shadow_main_004`：
  - 已进一步推进到 `scene_000/house_layout.json` 生成
  - 当前仍为未完整收敛的中断运行（今日已按要求停止）

当前可见产物：
- `/root/B1KSceneSmithShadow/runs/bedroom_shadow_main_004/resolved_config.yaml`
- `/root/B1KSceneSmithShadow/runs/bedroom_shadow_main_004/scene_000/scene.log`
- `/root/B1KSceneSmithShadow/runs/bedroom_shadow_main_004/scene_000/house_layout.json`

## 当前状态
- 所有本轮相关进程已手动停止。
- Shadow 主入口、文本索引、检索参数链路均已落地。
- 仍需下一轮继续验证“完整成功出 `omnigibson_scene(_preserve).json + shadow_manifest.json`”。

## 下次继续建议命令
```bash
bash /root/B1KSceneSmithShadow/scripts/run_shadow_main.sh \
  "A compact bedroom with one bed and one nightstand." \
  /root/B1KSceneSmithShadow/runs/bedroom_shadow_main_005
```

成功后执行：
```bash
find /root/B1KSceneSmithShadow/runs/bedroom_shadow_main_005 -maxdepth 3 -type f | \
  rg 'omnigibson_scene|shadow_manifest|scene.log|house_layout.json'
```
