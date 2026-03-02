#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/x-monitor"
APP_PORT="${XMONITOR_PORT:-56125}"
DATA_DIR="${XMONITOR_DATA_DIR:-/home/kasm-user/.local/share/x-monitor-pro}"
AUTOSTART_BROWSER="${XMONITOR_VNC_AUTOSTART_BROWSER:-1}"
PYTHON_BIN="${XMONITOR_VNC_PYTHON_BIN:-/opt/venv/bin/python}"
APP_USER="${XMONITOR_VNC_APP_USER:-kasm-user}"
LAUNCH_SCRIPT="/usr/local/bin/xmonitor-launch"
RUNTIME_LOG_FILE=""

export XMONITOR_PORT="${APP_PORT}"
export XMONITOR_HEADLESS_DEFAULT="${XMONITOR_HEADLESS_DEFAULT:-0}"
export XMONITOR_FORCE_HEADLESS="${XMONITOR_FORCE_HEADLESS:-0}"
export XMONITOR_PERSIST_BROWSER_PROFILE="${XMONITOR_PERSIST_BROWSER_PROFILE:-1}"
export XMONITOR_DATA_DIR="${DATA_DIR}"

prepare_data_dir() {
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

prepare_data_dir

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="$(command -v python3 || command -v python)"
fi

run_as_app_user() {
  local cmd="$1"
  if [[ "$(id -u)" == "0" ]]; then
    su -s /bin/bash "${APP_USER}" -c "${cmd}"
  else
    bash -lc "${cmd}"
  fi
}

ensure_desktop_launchers() {
  local app_home
  app_home="$(eval echo "~${APP_USER}")"
  [[ -n "${app_home}" ]] || app_home="/home/${APP_USER}"

  local desktop_dir="${app_home}/Desktop"
  mkdir -p "${desktop_dir}"

  cat > "${desktop_dir}/X Monitor Pro.desktop" <<DESKTOP_EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=X Monitor Pro
Comment=启动 X Monitor 并打开 Web 界面
Exec=${LAUNCH_SCRIPT}
Terminal=true
Icon=utilities-terminal
Categories=Network;
StartupNotify=true
DESKTOP_EOF

  cat > "${desktop_dir}/X Monitor Runtime Log.desktop" <<DESKTOP_EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=X Monitor Runtime Log
Comment=查看运行日志（tail -f）
Exec=sh -c 'tail -f "${RUNTIME_LOG_FILE}"'
Terminal=true
Icon=text-x-generic
Categories=Utility;
StartupNotify=true
DESKTOP_EOF

  chmod +x "${desktop_dir}/X Monitor Pro.desktop" "${desktop_dir}/X Monitor Runtime Log.desktop" || true
  if command -v gio >/dev/null 2>&1; then
    gio set "${desktop_dir}/X Monitor Pro.desktop" metadata::trusted true >/dev/null 2>&1 || true
    gio set "${desktop_dir}/X Monitor Runtime Log.desktop" metadata::trusted true >/dev/null 2>&1 || true
  fi

  chown -R "${APP_USER}:${APP_USER}" "${desktop_dir}" >/dev/null 2>&1 || true
}

start_backend() {
  if pgrep -f "app.py" >/dev/null 2>&1; then
    return 0
  fi
  run_as_app_user "cd '${APP_DIR}' && nohup '${PYTHON_BIN}' -u app.py >> '${RUNTIME_LOG_FILE}' 2>&1 &"
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

autostart_ui() {
  if [[ "${AUTOSTART_BROWSER}" == "0" || "${AUTOSTART_BROWSER}" == "false" ]]; then
    return 0
  fi

  local browser
  if ! browser="$(pick_browser_bin)"; then
    return 0
  fi

  if pgrep -f "${browser}.*127.0.0.1:${APP_PORT}" >/dev/null 2>&1; then
    return 0
  fi

  local target_url="http://127.0.0.1:${APP_PORT}"
  local browser_profile_dir="${DATA_DIR}/desktop-browser-profile"
  local browser_log_file="/tmp/xmonitor-vnc-browser.log"
  local launch_base="DISPLAY='${DISPLAY:-:1}' nohup ${browser} --no-first-run --no-default-browser-check --disable-gpu --disable-dev-shm-usage --user-data-dir='${browser_profile_dir}' --new-window '${target_url}' >>'${browser_log_file}' 2>&1 &"
  local launch_fallback="DISPLAY='${DISPLAY:-:1}' nohup ${browser} --no-first-run --no-default-browser-check --disable-gpu --disable-dev-shm-usage --no-sandbox --disable-setuid-sandbox --user-data-dir='${browser_profile_dir}' --new-window '${target_url}' >>'${browser_log_file}' 2>&1 &"

  run_as_app_user "mkdir -p '${browser_profile_dir}'"

  # 先按正常参数拉起，失败则兜底 no-sandbox 参数重试。
  run_as_app_user "${launch_base}"
  sleep 2
  if ! pgrep -f "${browser}.*${browser_profile_dir}" >/dev/null 2>&1; then
    run_as_app_user "${launch_fallback}"
    sleep 2
  fi
}

ensure_desktop_launchers
start_backend
wait_backend || true
autostart_ui

# Kasm vnc_startup.sh 期望 custom_startup 常驻；这里做后端保活，避免退出后触发 Unknown Service 日志刷屏。
while true; do
  if ! pgrep -f "app.py" >/dev/null 2>&1; then
    start_backend
    wait_backend || true
  fi
  sleep 5
done
