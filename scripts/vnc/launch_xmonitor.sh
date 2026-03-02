#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${XMONITOR_APP_DIR:-/opt/x-monitor}"
APP_PORT="${XMONITOR_PORT:-56125}"
APP_USER="${XMONITOR_VNC_APP_USER:-kasm-user}"
PYTHON_BIN="${XMONITOR_VNC_PYTHON_BIN:-/opt/venv/bin/python}"
DATA_DIR="${XMONITOR_DATA_DIR:-/home/kasm-user/.local/share/x-monitor-pro}"
RUNTIME_LOG_FILE=""

pick_data_dir() {
  local wanted_dir="${DATA_DIR}"
  local fallback_dir="${HOME}/.local/share/x-monitor-pro-runtime"
  local probe_file=""

  mkdir -p "${wanted_dir}" 2>/dev/null || true
  probe_file="${wanted_dir}/.xmonitor_write_test"
  if touch "${probe_file}" >/dev/null 2>&1; then
    rm -f "${probe_file}" >/dev/null 2>&1 || true
    DATA_DIR="${wanted_dir}"
  else
    mkdir -p "${fallback_dir}"
    DATA_DIR="${fallback_dir}"
  fi

  export XMONITOR_DATA_DIR="${DATA_DIR}"
  RUNTIME_LOG_FILE="${DATA_DIR}/runtime-vnc.log"
  if ! touch "${RUNTIME_LOG_FILE}" >/dev/null 2>&1; then
    RUNTIME_LOG_FILE="/tmp/x-monitor-runtime-vnc.log"
    touch "${RUNTIME_LOG_FILE}" >/dev/null 2>&1 || true
  fi
}

pick_browser_bin() {
  local bin
  for bin in google-chrome-stable google-chrome chromium chromium-browser; do
    if command -v "${bin}" >/dev/null 2>&1; then
      printf '%s' "${bin}"
      return 0
    fi
  done
  return 1
}

wait_backend() {
  local i
  for i in $(seq 1 45); do
    if curl -fsS "http://127.0.0.1:${APP_PORT}/api/state" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_backend() {
  if pgrep -f "app.py" >/dev/null 2>&1; then
    return 0
  fi

  if [[ ! -x "${PYTHON_BIN}" ]]; then
    PYTHON_BIN="$(command -v python3 || command -v python)"
  fi

  export XMONITOR_PORT="${APP_PORT}"
  export XMONITOR_HEADLESS_DEFAULT="${XMONITOR_HEADLESS_DEFAULT:-0}"
  export XMONITOR_FORCE_HEADLESS="${XMONITOR_FORCE_HEADLESS:-0}"
  export XMONITOR_PERSIST_BROWSER_PROFILE="${XMONITOR_PERSIST_BROWSER_PROFILE:-1}"

  if [[ "$(id -u)" == "0" ]]; then
    su -s /bin/bash "${APP_USER}" -c "cd '${APP_DIR}' && nohup '${PYTHON_BIN}' -u app.py >> '${RUNTIME_LOG_FILE}' 2>&1 &"
  else
    bash -lc "cd '${APP_DIR}' && nohup '${PYTHON_BIN}' -u app.py >> '${RUNTIME_LOG_FILE}' 2>&1 &"
  fi
}

open_frontend() {
  local browser
  local target_url="http://127.0.0.1:${APP_PORT}"
  local browser_profile_dir="${DATA_DIR}/desktop-browser-profile"
  local browser_log_file="/tmp/xmonitor-vnc-browser.log"

  if ! browser="$(pick_browser_bin)"; then
    printf '未找到可用浏览器，请手动访问 %s\n' "${target_url}"
    return 1
  fi

  mkdir -p "${browser_profile_dir}" >/dev/null 2>&1 || true

  if pgrep -f "${browser}.*127.0.0.1:${APP_PORT}" >/dev/null 2>&1; then
    return 0
  fi

  DISPLAY="${DISPLAY:-:1}" nohup "${browser}" \
    --no-first-run \
    --no-default-browser-check \
    --disable-gpu \
    --disable-dev-shm-usage \
    --no-sandbox \
    --disable-setuid-sandbox \
    --user-data-dir="${browser_profile_dir}" \
    --new-window "${target_url}" >>"${browser_log_file}" 2>&1 &
}

pick_data_dir
start_backend
wait_backend || true
open_frontend || true

printf 'X Monitor 启动命令已执行。\n'
printf 'Web: http://127.0.0.1:%s\n' "${APP_PORT}"
printf 'Runtime Log: %s\n' "${RUNTIME_LOG_FILE}"
