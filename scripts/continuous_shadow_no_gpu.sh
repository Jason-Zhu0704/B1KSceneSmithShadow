#!/usr/bin/env bash
set -o pipefail

ROOT="/root/B1KSceneSmithShadow"
RUNS_DIR="${ROOT}/runs"
LOG_DIR="${ROOT}/logs"
LOCK_FILE="/tmp/b1k_shadow_no_gpu.lock"
CONTROL_STOP_FILE="${ROOT}/.stop_continuous_no_gpu"
SUMMARY_CSV="${LOG_DIR}/continuous_no_gpu_summary.csv"
LOOP_LOG="${LOG_DIR}/continuous_no_gpu_loop.log"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-10}"
TIMEOUT_SEC="${TIMEOUT_SEC:-1200}"
HEARTBEAT_SEC="${HEARTBEAT_SEC:-30}"
API_MAX_RETRIES="${API_MAX_RETRIES:-3}"
RATE_LIMIT_BASE_SLEEP="${RATE_LIMIT_BASE_SLEEP:-20}"
RATE_LIMIT_MAX_SLEEP="${RATE_LIMIT_MAX_SLEEP:-300}"
RATE_LIMIT_JITTER_MAX="${RATE_LIMIT_JITTER_MAX:-15}"

mkdir -p "${RUNS_DIR}" "${LOG_DIR}"
rm -f "${CONTROL_STOP_FILE}"

# Single-instance lock to prevent multiple loops stepping on each other.
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "$(date '+%F %T') another continuous loop instance is already running" >> "${LOOP_LOG}"
  exit 0
fi

if [[ ! -f "${SUMMARY_CSV}" ]]; then
  echo "iter,start_ts,end_ts,elapsed_sec,status,prompt,run_dir,resolved_config,scene_log,house_layout,shadow_manifest,error_lines" > "${SUMMARY_CSV}"
fi

PROMPTS=(
  "A compact bedroom with one bed and one nightstand."
)

echo "=== continuous no-gpu loop started at $(date '+%F %T %Z') ===" >> "${LOOP_LOG}"
echo "summary_csv=${SUMMARY_CSV}" >> "${LOOP_LOG}"
echo "api_max_retries=${API_MAX_RETRIES}" >> "${LOOP_LOG}"
echo "rate_limit_backoff=base:${RATE_LIMIT_BASE_SLEEP}s max:${RATE_LIMIT_MAX_SLEEP}s jitter<=${RATE_LIMIT_JITTER_MAX}s" >> "${LOOP_LOG}"

iter=0
rate_limit_streak=0
while true; do
  if [[ -f "${CONTROL_STOP_FILE}" ]]; then
    echo "$(date '+%F %T') stop signal found: ${CONTROL_STOP_FILE}" >> "${LOOP_LOG}"
    exit 0
  fi

  iter=$((iter + 1))
  prompt_idx=$(( (iter - 1) % ${#PROMPTS[@]} ))
  prompt="${PROMPTS[$prompt_idx]}"

  start_ts="$(date '+%F %T')"
  start_epoch="$(date +%s)"
  stamp="$(date '+%Y%m%d_%H%M%S')"
  run_dir="${RUNS_DIR}/continuous_no_gpu_${stamp}_iter$(printf '%04d' "${iter}")"

  echo "$(date '+%F %T') iter=${iter} run_dir=${run_dir}" >> "${LOOP_LOG}"
  echo "$(date '+%F %T') prompt=${prompt}" >> "${LOOP_LOG}"

  # Extra cleanup to avoid stale port conflicts across iterations.
  pkill -f '/root/SmithPlusOmnigibson/scripts/run.py --prompt' >/dev/null 2>&1 || true
  pkill -f '/data/scenesmith/scenesmith/agent_utils/blender/standalone_server.py' >/dev/null 2>&1 || true
  pkill -f '/root/SmithPlusOmnigibson/src/optimized_server.py --host 127.0.0.1 --port 7006' >/dev/null 2>&1 || true
  pkill -f 'articulated_retrieval_server' >/dev/null 2>&1 || true
  pkill -f 'materials_retrieval_server' >/dev/null 2>&1 || true
  for p in 7006 7007 7008; do
    fuser -k "${p}/tcp" >/dev/null 2>&1 || true
  done
  sleep 2

  timeout "${TIMEOUT_SEC}s" env B1K_RETRIEVAL_BACKEND=lexical bash "${ROOT}/scripts/run_shadow_main.sh" \
    "${prompt}" \
    "${run_dir}" \
    --config-overrides "${ROOT}/configs/behavior1k_rate_limited.yaml" \
    --api-max-retries "${API_MAX_RETRIES}" \
    --start-stage floor_plan \
    --stop-stage floor_plan \
    --num-workers 1 \
    >> "${LOOP_LOG}" 2>&1 &
  job_pid=$!

  while kill -0 "${job_pid}" >/dev/null 2>&1; do
    now_epoch="$(date +%s)"
    running_sec="$(( now_epoch - start_epoch ))"
    cfg_flag=0
    log_flag=0
    layout_flag=0
    if [[ -f "${run_dir}/resolved_config.yaml" ]]; then
      cfg_flag=1
    fi
    if [[ -f "${run_dir}/scene_000/scene.log" ]]; then
      log_flag=1
    fi
    if [[ -f "${run_dir}/scene_000/house_layout.json" ]]; then
      layout_flag=1
    fi
    echo "$(date '+%F %T') heartbeat iter=${iter} running=${running_sec}s cfg:${cfg_flag} log:${log_flag} layout:${layout_flag}" >> "${LOOP_LOG}" || true
    sleep "${HEARTBEAT_SEC}"
  done

  wait "${job_pid}"
  status=$?

  end_ts="$(date '+%F %T')"
  end_epoch="$(date +%s)"
  elapsed_sec="$(( end_epoch - start_epoch ))"

  resolved_config=0
  scene_log=0
  house_layout=0
  shadow_manifest=0
  error_lines=0

  if [[ -f "${run_dir}/resolved_config.yaml" ]]; then
    resolved_config=1
  fi
  if [[ -f "${run_dir}/scene_000/scene.log" ]]; then
    scene_log=1
  fi
  if [[ -f "${run_dir}/scene_000/house_layout.json" ]]; then
    house_layout=1
  fi
  if [[ -f "${run_dir}/scene_000/shadow_manifest.json" ]]; then
    shadow_manifest=1
  fi

  if [[ "${scene_log}" -eq 1 ]]; then
    error_lines="$(grep -E -i -n 'error|traceback|exception' "${run_dir}/scene_000/scene.log" | wc -l || true)"
  fi

  safe_prompt="${prompt//,/;}"
  echo "${iter},${start_ts},${end_ts},${elapsed_sec},${status},\"${safe_prompt}\",${run_dir},${resolved_config},${scene_log},${house_layout},${shadow_manifest},${error_lines}" >> "${SUMMARY_CSV}" || true

  echo "$(date '+%F %T') iter=${iter} status=${status} elapsed=${elapsed_sec}s artifacts=cfg:${resolved_config} log:${scene_log} layout:${house_layout} manifest:${shadow_manifest} errors:${error_lines}" >> "${LOOP_LOG}" || true

  has_429=0
  if [[ -f "${run_dir}/scene_000/scene.log" ]] && grep -q "429 Too Many Requests" "${run_dir}/scene_000/scene.log"; then
    has_429=1
  fi

  if [[ "${has_429}" -eq 1 ]]; then
    rate_limit_streak=$((rate_limit_streak + 1))
    backoff_sleep=$((RATE_LIMIT_BASE_SLEEP * (2 ** (rate_limit_streak - 1))))
    if (( backoff_sleep > RATE_LIMIT_MAX_SLEEP )); then
      backoff_sleep="${RATE_LIMIT_MAX_SLEEP}"
    fi
    jitter=$((RANDOM % (RATE_LIMIT_JITTER_MAX + 1)))
    total_sleep=$((backoff_sleep + jitter))
    echo "$(date '+%F %T') rate-limit detected (429), streak=${rate_limit_streak}, sleeping ${total_sleep}s (backoff=${backoff_sleep}s+jitter=${jitter}s)" >> "${LOOP_LOG}" || true
    sleep "${total_sleep}"
  else
    rate_limit_streak=0
    sleep "${SLEEP_BETWEEN}"
  fi
done
