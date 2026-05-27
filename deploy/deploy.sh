#!/usr/bin/env bash
# 서비스 전체 배포 스크립트.
# 실행 순서: git pull -> collect.py -> cli.py -> signal-web build -> api/web restart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
VENV_PYTHON="${VENV_PYTHON:-$APP_DIR/.venv/bin/python}"

MARKET="${MARKET:-KOSPI}"
CACHE_ROOT="${CACHE_ROOT:-.cache}"
OUTPUT_DIR="${OUTPUT_DIR:-data}"
COLLECT_TIMEFRAMES="${COLLECT_TIMEFRAMES:-1D 1W 1h 30m}"
COLLECT_NO_SMART_SKIP="${COLLECT_NO_SMART_SKIP:-1}"

NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-https://sigbora.com}"
GIT_PULL="${GIT_PULL:-1}"
PIP_INSTALL="${PIP_INSTALL:-1}"
NPM_INSTALL="${NPM_INSTALL:-ci}" # ci | install | skip

API_SERVICE="${API_SERVICE:-signal-api}"
WEB_SERVICE="${WEB_SERVICE:-signal-web}"
SYSTEMD_DAEMON_RELOAD="${SYSTEMD_DAEMON_RELOAD:-1}"

log() {
  printf '\n==> %s\n' "$*"
}

abort() {
  printf '[ERROR] %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || abort "필수 명령을 찾을 수 없습니다: $1"
}

run_systemctl() {
  if [[ "${USE_SUDO:-1}" == "1" && "${EUID:-$(id -u)}" -ne 0 ]]; then
    sudo systemctl "$@"
  else
    systemctl "$@"
  fi
}

cd "$APP_DIR"

[[ -x "$VENV_PYTHON" ]] || abort "Python venv 실행 파일이 없습니다: $VENV_PYTHON"
require_cmd npm
require_cmd git

mkdir -p "$CACHE_ROOT" "$OUTPUT_DIR"

if [[ "$GIT_PULL" == "1" ]]; then
  log "최신 코드 반영"
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if ! git diff --quiet || ! git diff --cached --quiet; then
      abort "작업트리가 깨끗하지 않아 git pull을 중단합니다. 커밋/스태시 후 다시 실행하세요."
    fi
    git fetch --all --prune
    git pull --ff-only
  else
    abort "APP_DIR이 git 저장소가 아닙니다: $APP_DIR"
  fi
else
  log "git pull 건너뜀 (GIT_PULL=0)"
fi

if [[ "$PIP_INSTALL" == "1" ]]; then
  log "Python 의존성 설치"
  "$VENV_PYTHON" -m pip install -r requirements.txt
  "$VENV_PYTHON" -m pip install -r signal-api/requirements.txt
else
  log "Python 의존성 설치 건너뜀 (PIP_INSTALL=0)"
fi

log "시장 데이터 수집"
read -r -a TF_ARGS <<< "$COLLECT_TIMEFRAMES"
COLLECT_CMD=(
  "$VENV_PYTHON" scripts/collect.py
  --market "$MARKET"
  --cache-root "$CACHE_ROOT"
  --timeframes "${TF_ARGS[@]}"
)
if [[ "$COLLECT_NO_SMART_SKIP" == "1" ]]; then
  COLLECT_CMD+=(--no-smart-skip)
fi
"${COLLECT_CMD[@]}"

log "signals.json 생성"
"$VENV_PYTHON" cli.py \
  --strategy all \
  --cache-root "$CACHE_ROOT" \
  --output-dir "$OUTPUT_DIR" \
  --format signals_ui

log "signal-web 의존성/빌드"
pushd signal-web >/dev/null
case "$NPM_INSTALL" in
  ci)
    npm ci
    ;;
  install)
    npm install
    ;;
  skip)
    log "npm install 건너뜀 (NPM_INSTALL=skip)"
    ;;
  *)
    abort "NPM_INSTALL 값은 ci/install/skip 중 하나여야 합니다: $NPM_INSTALL"
    ;;
esac
NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" npm run build

[[ -d .next/standalone ]] || abort "Next standalone 빌드 산출물이 없습니다: signal-web/.next/standalone"
rm -rf .next/standalone/.next/static .next/standalone/public
mkdir -p .next/standalone/.next
cp -R .next/static .next/standalone/.next/static
if [[ -d public ]]; then
  cp -R public .next/standalone/public
fi
popd >/dev/null

log "systemd 서비스 재시작"
if [[ "$SYSTEMD_DAEMON_RELOAD" == "1" ]]; then
  run_systemctl daemon-reload
fi
run_systemctl restart "$API_SERVICE"
run_systemctl restart "$WEB_SERVICE"

log "서비스 상태 확인"
run_systemctl status "$API_SERVICE" --no-pager -l
run_systemctl status "$WEB_SERVICE" --no-pager -l

log "배포 완료"
