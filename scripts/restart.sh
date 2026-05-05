#!/usr/bin/env bash
# VM에서 signal-api / signal-web 재시작
# 사용법:
#   bash scripts/restart.sh        # api + web 둘 다
#   bash scripts/restart.sh api    # api만
#   bash scripts/restart.sh web    # web만 (소스 변경 없이 프로세스만 재시작)
#   bash scripts/restart.sh web-build  # web 재빌드 + 재시작
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-both}"

restart_api() {
  echo "==> signal-api 재시작"
  sudo systemctl restart signal-api
  sudo systemctl status signal-api --no-pager -l
}

rebuild_web() {
  echo "==> signal-web 빌드"
  cd "$REPO_ROOT/signal-web"
  npm ci
  npm run build
  # standalone 모드는 정적 파일을 자동 포함하지 않으므로 수동 복사 필수
  cp -r .next/static .next/standalone/.next/static
  cp -r public .next/standalone/public
}

restart_web() {
  echo "==> signal-web 재시작"
  sudo systemctl restart signal-web
  sudo systemctl status signal-web --no-pager -l
}

case "$TARGET" in
  api)
    restart_api
    ;;
  web)
    restart_web
    ;;
  web-build)
    rebuild_web
    restart_web
    ;;
  both)
    restart_api
    rebuild_web
    restart_web
    ;;
  *)
    echo "사용법: $0 [api|web|web-build|both]" >&2
    exit 1
    ;;
esac

echo "==> 완료"
