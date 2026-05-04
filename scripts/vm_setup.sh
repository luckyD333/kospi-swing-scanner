#!/usr/bin/env bash
# DigitalOcean Ubuntu 22.04 초기 설치 스크립트
# 사용법: sudo bash scripts/vm_setup.sh <github_user> <vm_ip>
# 예시:   sudo bash scripts/vm_setup.sh luckyD333 123.456.789.0
set -euo pipefail

GITHUB_USER="${1:?첫 번째 인자로 GitHub 사용자명을 입력하세요}"
VM_IP="${2:?두 번째 인자로 VM IP를 입력하세요}"
APP_DIR="/opt/kospi-scanner"

# --- 시스템 패키지 ---
apt-get update -y
apt-get install -y python3.11 python3.11-venv python3-pip git nginx curl

# --- Node.js 22 (LTS) ---
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs

# --- 프로젝트 클론 ---
git clone "https://github.com/${GITHUB_USER}/kospi-swing-scanner" "$APP_DIR"
cd "$APP_DIR"

# --- Python 가상환경 ---
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r signal-api/requirements.txt

# --- Node 의존성 & 빌드 ---
cd signal-web
NEXT_PUBLIC_API_URL="http://${VM_IP}/api" npm ci
npm run build
cd ..

# --- 런타임 디렉토리 ---
mkdir -p data .cache log

# --- www-data 권한 설정 ---
chown -R www-data:www-data "$APP_DIR"

echo ""
echo "설치 완료. 다음 단계:"
echo "  1. sudo cp ${APP_DIR}/deploy/signal-api.service /etc/systemd/system/"
echo "  2. sudo cp ${APP_DIR}/deploy/signal-web.service /etc/systemd/system/"
echo "  3. sudo systemctl daemon-reload && sudo systemctl enable --now signal-api signal-web"
echo "  4. sudo cp ${APP_DIR}/deploy/nginx-kospi-scanner.conf /etc/nginx/sites-available/kospi-scanner"
echo "  5. sudo ln -s /etc/nginx/sites-available/kospi-scanner /etc/nginx/sites-enabled/"
echo "  6. sudo nginx -t && sudo systemctl reload nginx"
echo "  7. crontab -e 로 deploy/crontab.example 내용 추가"
