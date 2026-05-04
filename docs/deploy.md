# DigitalOcean VM 배포 가이드

이 가이드는 DigitalOcean Droplet(Ubuntu 22.04)에 KOSPI Swing Scanner를 배포하는 전체 절차를 다룹니다.

---

## 1. 사전 준비

### 1-1. Droplet 생성

DigitalOcean 콘솔에서 Droplet을 생성하세요:

- **Image**: Ubuntu 22.04 LTS
- **Plan**: Basic / Regular (최소 2 GB RAM 권장 — Next.js 빌드 중 메모리 사용량 고려)
- **Region**: SGP1 (Singapore) 또는 TYO1 (Tokyo) — 한국 레이턴시 최소화
- **Authentication**: SSH Key 등록 권장

Droplet 생성 후 **IP 주소**를 메모해 두세요.

### 1-2. SSH 접속

```bash
ssh root@YOUR_VM_IP
```

### 1-3. 시간대 설정 (KST)

cron이 KST 기준으로 실행되려면 반드시 설정:

```bash
timedatectl set-timezone Asia/Seoul
timedatectl status  # Asia/Seoul 확인
```

---

## 2. 초기 VM 설치

로컬에서 이미 `scripts/vm_setup.sh`가 저장소에 포함되어 있어요.
VM에서 직접 실행하거나, 아래 명령어를 단계별로 실행하세요.

### 방법 A: 스크립트 한 번에 실행

```bash
# VM에서 실행
curl -fsSL https://raw.githubusercontent.com/luckyD333/kospi-swing-scanner/main/scripts/vm_setup.sh \
  | sudo bash -s luckyD333 YOUR_VM_IP
```

### 방법 B: 단계별 수동 설치

```bash
# 패키지 설치
apt-get update -y
apt-get install -y python3.11 python3.11-venv python3-pip git nginx curl

# Node.js 22 (LTS)
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs

# 프로젝트 클론
git clone https://github.com/luckyD333/kospi-swing-scanner /opt/kospi-scanner
cd /opt/kospi-scanner

# Python 가상환경
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r signal-api/requirements.txt

# Next.js 빌드 (VM IP를 실제 값으로 교체)
cd signal-web
NEXT_PUBLIC_API_URL=http://YOUR_VM_IP/api npm ci
npm run build
cd ..

# 런타임 디렉토리
mkdir -p data .cache log
chown -R www-data:www-data /opt/kospi-scanner
```

---

## 3. systemd 서비스 등록

### signal-api (FastAPI)

`deploy/signal-api.service`의 `YOUR_VM_IP`를 실제 IP로 교체한 뒤 등록:

```bash
# IP 교체
sed -i "s/YOUR_VM_IP/실제IP/g" /opt/kospi-scanner/deploy/signal-api.service

sudo cp /opt/kospi-scanner/deploy/signal-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable signal-api
sudo systemctl start signal-api
sudo systemctl status signal-api   # Active: active (running) 확인
```

### signal-web (Next.js)

```bash
sudo cp /opt/kospi-scanner/deploy/signal-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable signal-web
sudo systemctl start signal-web
sudo systemctl status signal-web   # Active: active (running) 확인
```

---

## 4. nginx 역방향 프록시 설정

```bash
sudo cp /opt/kospi-scanner/deploy/nginx-kospi-scanner.conf \
        /etc/nginx/sites-available/kospi-scanner

# 기본 사이트 비활성화 (선택)
sudo rm -f /etc/nginx/sites-enabled/default

sudo ln -s /etc/nginx/sites-available/kospi-scanner \
           /etc/nginx/sites-enabled/kospi-scanner

sudo nginx -t                  # 문법 검사 (successful 확인)
sudo systemctl reload nginx
```

---

## 5. cron 스케줄 등록

```bash
# VM 시간대가 KST인지 재확인
date   # KST 시간 출력 확인

# crontab 편집
crontab -e
```

`deploy/crontab.example` 내용을 그대로 붙여넣기 하세요.

---

## 6. 동작 확인 체크리스트

```bash
# signal-api 응답 확인
curl http://localhost:8000/api/signals | head -c 200

# nginx를 통한 전체 경로 확인
curl http://YOUR_VM_IP/api/signals | head -c 200

# 브라우저에서 확인
# http://YOUR_VM_IP/  →  신호 카드 목록 표시
```

| 항목 | 명령어 | 기대 결과 |
|------|--------|----------|
| signal-api | `sudo systemctl status signal-api` | `active (running)` |
| signal-web | `sudo systemctl status signal-web` | `active (running)` |
| nginx | `sudo systemctl status nginx` | `active (running)` |
| API 응답 | `curl http://localhost:8000/api/signals` | JSON 배열 |
| UI 접속 | 브라우저 `http://YOUR_VM_IP/` | 신호 카드 목록 |

---

## 7. 코드 업데이트 (재배포)

로컬에서 `git push` 후 VM에서:

```bash
cd /opt/kospi-scanner
git pull

# Python 의존성 변경 시
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r signal-api/requirements.txt

# Next.js 변경 시 재빌드
cd signal-web
NEXT_PUBLIC_API_URL=http://YOUR_VM_IP/api npm ci
npm run build
cd ..

# 서비스 재시작
sudo systemctl restart signal-api signal-web
```

---

## 8. 트러블슈팅

### 로그 확인

```bash
# systemd 서비스 로그
sudo journalctl -u signal-api -n 50 --no-pager
sudo journalctl -u signal-web -n 50 --no-pager

# cron 작업 로그
tail -f /opt/kospi-scanner/log/collect.log
tail -f /opt/kospi-scanner/log/signals.log
```

### 자주 발생하는 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| `502 Bad Gateway` | signal-api 또는 signal-web 미실행 | `systemctl restart signal-api signal-web` |
| `curl /api/signals` → 빈 JSON `[]` | `data/signals.json` 미생성 | `cd /opt/kospi-scanner && .venv/bin/python cli.py --strategy all --output-dir data --format signals_ui` 수동 실행 |
| Next.js 빌드 실패 (메모리 부족) | Droplet RAM 부족 | swap 추가: `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile` |
| cron 미실행 | 시간대 불일치 | `timedatectl set-timezone Asia/Seoul` 후 재설정 |
| `permission denied` on log/ | www-data 권한 없음 | `chown -R www-data:www-data /opt/kospi-scanner` |
