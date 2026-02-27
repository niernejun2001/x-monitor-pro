#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LPK_DIR="${LPK_DIR:-$ROOT_DIR/lazycat-lpk-online}"
MANIFEST_PATH="${MANIFEST_PATH:-$LPK_DIR/manifest.yml}"
SRC_IMAGE_REPO="${SRC_IMAGE_REPO:-registry.cn-hangzhou.aliyuncs.com/shoxk8s/x-monitor-pro}"
APP_PACKAGE="${APP_PACKAGE:-cloud.lazycat.app.xmonitor}"
TRACE_LEVEL="${TRACE_LEVEL:-quiet}"

TAG="${1:-v$(date +%Y%m%d-%H%M%S)}"
IMAGE_TAG="${SRC_IMAGE_REPO}:${TAG}"
IMAGE_LATEST="${SRC_IMAGE_REPO}:latest"

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令: $1"
}

bump_last_version_part() {
  local version="$1"
  IFS='.' read -r -a parts <<<"$version"
  local idx=$(( ${#parts[@]} - 1 ))

  [[ $idx -ge 0 ]] || die "无法解析 version: $version"
  [[ "${parts[$idx]}" =~ ^[0-9]+$ ]] || die "version 最后一段不是数字: $version"

  parts[$idx]=$((parts[$idx] + 1))

  local out="${parts[0]}"
  local i
  for ((i = 1; i < ${#parts[@]}; i++)); do
    out+=".${parts[$i]}"
  done
  printf '%s' "$out"
}

normalize_version() {
  local raw="$1"
  local nums
  nums="$(printf '%s' "$raw" | grep -Eo '[0-9]+' | tr '\n' ' ' | sed 's/[[:space:]]\+$//')"
  [[ -n "$nums" ]] || die "无法从 version 中提取数字: $raw"

  local -a arr=()
  read -r -a arr <<<"$nums"
  local count="${#arr[@]}"

  if (( count >= 3 )); then
    printf '%s.%s.%s' "${arr[0]}" "${arr[1]}" "${arr[2]}"
    return 0
  fi
  if (( count == 2 )); then
    printf '%s.%s' "${arr[0]}" "${arr[1]}"
    return 0
  fi
  printf '%s' "${arr[0]}"
}

extract_lazycat_image() {
  local raw="$1"
  local parsed
  parsed="$(printf '%s\n' "$raw" | tr -d '\r' | grep -Eo 'registry\.lazycat\.cloud[^[:space:]]+' | tail -n 1 || true)"
  [[ -n "$parsed" ]] || die "copy-image 输出中未找到微服镜像地址"
  printf '%s' "$parsed"
}

update_manifest() {
  local new_version="$1"
  local lazycat_image="$2"

  [[ -f "$MANIFEST_PATH" ]] || die "manifest 不存在: $MANIFEST_PATH"

  sed -i -E "0,/^version:[[:space:]]*/s|^version:[[:space:]].*$|version: ${new_version}|" "$MANIFEST_PATH"
  sed -i -E "0,/^[[:space:]]*image:[[:space:]]*/s|^[[:space:]]*image:[[:space:]].*|    image: ${lazycat_image}|" "$MANIFEST_PATH"
}

main() {
  require_cmd docker
  require_cmd lzc-cli
  require_cmd awk
  require_cmd sed
  require_cmd grep

  [[ -d "$LPK_DIR" ]] || die "LPK 目录不存在: $LPK_DIR"
  [[ -f "$MANIFEST_PATH" ]] || die "manifest 不存在: $MANIFEST_PATH"

  log "构建镜像: $IMAGE_TAG"
  docker build -t "$IMAGE_TAG" -t "$IMAGE_LATEST" "$ROOT_DIR"

  log "推送镜像: $IMAGE_TAG"
  docker push "$IMAGE_TAG"

  log "推送镜像: $IMAGE_LATEST"
  docker push "$IMAGE_LATEST"

  log "拷贝镜像到微服仓库"
  local copy_output
  copy_output="$(lzc-cli appstore copy-image "$IMAGE_TAG" --trace-level "$TRACE_LEVEL")"
  printf '%s\n' "$copy_output"
  local lazycat_image
  lazycat_image="$(extract_lazycat_image "$copy_output")"
  log "微服镜像: $lazycat_image"

  local current_version
  current_version="$(awk '/^version:[[:space:]]*/{sub(/^version:[[:space:]]*/, ""); print; exit}' "$MANIFEST_PATH")"
  [[ -n "$current_version" ]] || die "manifest 中未找到 version"
  local normalized_version
  normalized_version="$(normalize_version "$current_version")"
  local new_version
  new_version="$(bump_last_version_part "$normalized_version")"
  log "manifest 版本: ${normalized_version} -> ${new_version}"

  update_manifest "$new_version" "$lazycat_image"

  log "构建 LPK"
  (
    cd "$LPK_DIR"
    lzc-cli project build .
  )

  local lpk_file="$LPK_DIR/dist/${APP_PACKAGE}-v${new_version}.lpk"
  if [[ ! -f "$lpk_file" ]]; then
    lpk_file="$(ls -1t "$LPK_DIR"/dist/"${APP_PACKAGE}"-v*.lpk 2>/dev/null | head -n 1 || true)"
  fi
  [[ -n "${lpk_file:-}" && -f "$lpk_file" ]] || die "未找到生成的 LPK 包"
  log "安装应用: $lpk_file"
  lzc-cli app install "$lpk_file"

  log "检查应用状态: $APP_PACKAGE"
  lzc-cli app status "$APP_PACKAGE"

  log "部署完成"
}

main "$@"
