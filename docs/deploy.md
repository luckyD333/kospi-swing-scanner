# DigitalOcean VM 배포 가이드

이 가이드는 DigitalOcean Droplet(Ubuntu 22.04)에 KOSPI Swing Scanner를 배포하는 전체 절차를 다룹니다.

---

## 0. 데이터 흐름 (SSOT)

운영 데이터는 **`data/signals.json`**(전략 결과·SSOT) + **`data/market_snapshot.json`**(시장 raw·overlay 소스) 2-파일이에요. 프론트는 이 파일을 직접 import하지 않고 signal-api 경유로 fetch만 합니다.

```
[cron Job A] 16:10 KST   scripts/collect.py            → .cache/{tf}/<ticker>.parquet  (OHLCV)
                                                         + data/market_snapshot.json    (KOSPI/KOSDAQ + ETF + 매크로)
[cron Job B] 16:40 KST   cli.py --format signals_ui    → data/signals.json             ★ 전략 SSOT
             09:01,31~   동일 (intraday 30분 간격, collect → cli 페어링)
[cron Job C] */2 09-15   scripts/collect_live.py        → data/market_snapshot.json    (현재가 + 시장지수 부분 갱신)
                                          ↓
[signal-api  :8000]   FastAPI 응답 시점 조인 (signal-api/app/services/join.py)
                       - signals.json (trade_plan / signal_date — freeze)
                       - market_snapshot.json (fundamentals / flow / external_links — fresh override)
                       - market_snapshot.json (live_quote.current_price — Job C 갱신분 override)
                       - merge_rsi_by_timeframe(rsi_1d/1h/30m)
                       → /api/signals, /api/signals/{ticker}, /api/signals/health
                              (SIGNAL_API_DATA_DIR 환경변수)
                                          ↓
[signal-web  :3000]   Next.js  fetch(${NEXT_PUBLIC_API_URL}/api/signals)
                              CatalogClient + DetailClient (2분 주기 router.refresh 자동 갱신)
                                          ↓
[nginx       :80  ]   /     → :3000 (signal-web)
                      /api/ → :8000 (signal-api)
```

**의존 파일 정리** (운영 시 `data/`/`.cache/`/프로젝트 루트에 존재해야 함):
- `data/signals.json` — Job B 산출물. 없으면 `/api/signals` 가 `503 signals_not_generated` 반환.
- `data/market_snapshot.json` — Job A 산출물. 없으면 fundamentals/flow overlay skip(stale 데이터 노출).
- `weights.yml` (프로젝트 루트) — `--decide` 와 ranking.decision 채움. 없으면 FACTOR BREAKDOWN 미노출.
- `.cache/regime_analysis.json` — `core.decision.market_regime.save_regime_analysis` 산출물. 없으면 MarketRegimePanel 누락.

**중요**: `signal-web/src/data/` 디렉토리는 사용하지 않아요(레거시). `.gitignore`에 등재되어 있어요. 데이터 갱신은 cli.py 실행 또는 cron Job B 트리거가 유일한 경로예요.

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

root로 접속하더라도 설치 경로는 반드시 **`/opt/apps/kospi-scanner`**를 사용하세요. root 홈(`/root`)은 기본 권한이 `700`이라 `www-data`가 파일을 읽지 못해요. `/opt`는 world-executable이므로 서비스 계정이 정상 접근할 수 있어요.

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

`scripts/vm_setup.sh`를 그대로 실행하면 `/opt/apps/kospi-scanner`에 설치돼요. 이 문서와 경로가 일치하므로 방법 A를 사용해도 됩니다.

```bash
bash scripts/vm_setup.sh
```

### 방법 B: 단계별 수동 설치

```bash
# 설치 경로
export APP_DIR="/opt/apps/kospi-scanner"
export VM_IP="YOUR_VM_IP"

# 패키지 설치
apt-get update -y
apt-get install -y python3.12 python3.12-venv python3-pip git nginx curl

# Node.js 22 (LTS)
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs

# 프로젝트 클론
git clone https://github.com/luckyD333/kospi-swing-scanner "$APP_DIR"
cd "$APP_DIR"

# Python 가상환경
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r signal-api/requirements.txt

# Next.js 빌드
cd signal-web
NEXT_PUBLIC_API_URL="http://${VM_IP}/api" npm ci
npm run build
# standalone 모드는 정적 파일을 자동 포함하지 않으므로 수동 복사 필수
cp -r .next/static .next/standalone/.next/static
cp -r public .next/standalone/public
cd ..

# 런타임 디렉토리
mkdir -p data .cache log

# 서비스 계정이 읽을 수 있게 권한 부여 (/opt는 기본 world-executable이지만 명시 설정)
chmod -R o+rX "$APP_DIR"
```

---

## 3. systemd 서비스 등록

### signal-api (FastAPI)

`deploy/signal-api.service` 템플릿은 `/opt/apps/kospi-scanner` 기준이에요. CORS origin(VM IP)만 치환하면 됩니다.

```bash
export APP_DIR="/opt/apps/kospi-scanner"
export VM_IP="YOUR_VM_IP"
cp "$APP_DIR/deploy/signal-api.service" /tmp/signal-api.service
sed -i \
  -e "s|YOUR_VM_IP|$VM_IP|g" \
  /tmp/signal-api.service

sudo cp /tmp/signal-api.service /etc/systemd/system/signal-api.service
sudo systemctl daemon-reload
sudo systemctl enable signal-api
sudo systemctl start signal-api
sudo systemctl status signal-api   # Active: active (running) 확인
```

### signal-web (Next.js)

```bash
export APP_DIR="/opt/apps/kospi-scanner"
cp "$APP_DIR/deploy/signal-web.service" /tmp/signal-web.service

sudo cp /tmp/signal-web.service /etc/systemd/system/signal-web.service
sudo systemctl daemon-reload
sudo systemctl enable signal-web
sudo systemctl start signal-web
sudo systemctl status signal-web   # Active: active (running) 확인
```

---

## 4. nginx 역방향 프록시 설정

```bash
export APP_DIR="/opt/apps/kospi-scanner"
sudo cp "$APP_DIR/deploy/nginx-kospi-scanner.conf" \
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

`deploy/crontab.example`을 그대로 사용하면 돼요 (`/opt/apps/kospi-scanner` 기준).

```crontab
APP_DIR=/opt/apps/kospi-scanner
VENV_PYTHON=/opt/apps/kospi-scanner/.venv/bin/python
LOG_DIR=/opt/apps/kospi-scanner/log

# Job A: 장 마감 후 OHLCV 수집 (평일 16:10 KST)
10 16 * * 1-5 cd $APP_DIR && $VENV_PYTHON scripts/collect.py --market KOSPI --cache-root .cache >> $LOG_DIR/collect.log 2>&1

# Job B (일봉 신호): 수집 30분 후 (평일 16:40 KST)
40 16 * * 1-5 cd $APP_DIR && $VENV_PYTHON cli.py --strategy all --cache-root .cache --output-dir data --format signals_ui >> $LOG_DIR/signals.log 2>&1

# Job B (장중 신호): 장 중 30분 간격 대신 collect → cli 페어링 권장
1,31 9-15 * * 1-5 cd $APP_DIR && $VENV_PYTHON scripts/collect.py --market KOSPI --cache-root .cache --timeframes 1D 1h 30m --smart-skip >> $LOG_DIR/collect_intraday.log 2>&1 && cd $APP_DIR && $VENV_PYTHON cli.py --strategy all --cache-root .cache --output-dir data --format signals_ui >> $LOG_DIR/signals_intraday.log 2>&1

# Job C (실시간 현재가): 시장 지수 + 시그널 종목 현재가만 갱신 (2분 주기, 09:00-15:59)
*/2 9-15 * * 1-5 cd $APP_DIR && $VENV_PYTHON scripts/collect_live.py >> $LOG_DIR/live.log 2>&1
```

### 5-1. 장중 30m 페어링 스크립트 (권장)

`crontab.example` 의 장중 entry는 cli.py 만 실행해서 raw 1m 캐시가 stale 일 때 시그널이 한 박자 늦어요. **collect → cli 를 한 스크립트로 묶고**, bar close 시각에서 1분 지연으로 호출하면 네이버 데이터 반영 지연(보통 30~60초)을 흡수할 수 있어요.

```bash
# /opt/apps/kospi-scanner/scripts/run_30m.sh
#!/bin/bash
cd /opt/apps/kospi-scanner
.venv/bin/python scripts/collect.py --market KOSPI --cache-root .cache \
    --timeframes 1D 1h 30m --smart-skip \
  && .venv/bin/python cli.py --strategy all --cache-root .cache \
    --format signals_ui --output-dir data
```

```crontab
# 30m bar close + 1분 (09:01, 09:31, 10:01, ..., 15:01, 15:31)
1,31 9-15 * * 1-5 /opt/apps/kospi-scanner/scripts/run_30m.sh >> /opt/apps/kospi-scanner/log/30m.log 2>&1
```

| 항목 | 값 | 이유 |
|------|-----|------|
| 분 필드 | `1,31` (≠ `*/30`) | bar close 직후 데이터 도착 대기 (`*/30` 은 :00/:30 정시라 너무 빠름) |
| 시 필드 | `9-15` | 09:01 첫 실행, 15:31 마지막 실행 |
| `--smart-skip` | flag | 30m TF는 30분 미만 경과 시 자동 skip — 빈 호출 비용 0 |
| `&&` 체인 | `||` 아님 | collect 실패 시 cli 자동 skip, stale cache 위에 결과 덮어쓰기 회피 |

**기존 `*/30 9-15` entry 와 병행 운영 금지** — 두 cron 이 같은 manifest.json 을 동시에 쓰면 충돌해요. 본 페어링 스크립트로 교체하거나, 시 필드를 어긋나게 두세요.

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
| API 응답 | `curl http://localhost:8000/api/signals` | JSON 응답 (`signals`, `generated_at` 등 포함) |
| UI 접속 | 브라우저 `http://YOUR_VM_IP/` | 신호 카드 목록 |

---

## 7. 코드 업데이트 (재배포)

로컬에서 `git push` 후 VM에서:

```bash
export APP_DIR="/opt/apps/kospi-scanner"
cd "$APP_DIR"
git pull
```

이후 변경 종류에 따라 `scripts/restart.sh`로 간편하게 처리해요:

```bash
# signal-api만 재시작 (Python 코드 변경)
bash scripts/restart.sh api

# signal-web 프로세스만 재시작 (소스 변경 없음)
bash scripts/restart.sh web

# signal-web 재빌드 + 재시작 (Next.js 소스/패키지 변경)
bash scripts/restart.sh web-build

# api + web 둘 다 재빌드 + 재시작
bash scripts/restart.sh
```

`web-build` 와 `both` 옵션은 빌드 후 standalone 정적 파일 복사까지 자동으로 처리해요:
```bash
cp -r .next/static .next/standalone/.next/static
cp -r public .next/standalone/public
```

**Python 의존성이 변경된 경우** 스크립트 실행 전에 수동으로 재설치하세요:
```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r signal-api/requirements.txt
```

### 변경 종류별 반영 방법

| 변경 내용 | 필요한 작업 | 재시작 필요 여부 |
|------|------|------|
| `data/signals.json`, `data/market_snapshot.json`, `.cache/` 만 갱신 | `scripts/collect.py` 또는 `cli.py` 재실행 | **불필요**. signal-api 는 요청마다 파일을 다시 읽어요. |
| `signal-api/app/**`, `signal-api/requirements.txt`, API 관련 Python 코드 | 의존성 재설치(필요 시) 후 `sudo systemctl restart signal-api` | **signal-api만 필요** |
| `signal-web/src/**`, `signal-web/package*.json`, `NEXT_PUBLIC_API_URL` | `cd signal-web && npm ci && npm run build` 후 `sudo systemctl restart signal-web` | **signal-web만 필요** |
| `deploy/*.service` 수정 | `/etc/systemd/system/` 재복사 후 `sudo systemctl daemon-reload` + 해당 서비스 restart | **해당 서비스 필요** |
| nginx 설정 수정 | `sudo nginx -t` 후 `sudo systemctl reload nginx` | **reload만 필요** |
| cron 수정 | `crontab -e` 저장 | **서비스 재시작 불필요** |

---

## 8. 트러블슈팅

### 로그 확인

```bash
# systemd 서비스 로그
sudo journalctl -u signal-api -n 50 --no-pager
sudo journalctl -u signal-web -n 50 --no-pager

# cron 작업 로그
tail -f /opt/apps/kospi-scanner/log/collect.log
tail -f /opt/apps/kospi-scanner/log/signals.log
tail -f /opt/apps/kospi-scanner/log/live.log        # Job C 실시간 현재가
```

### 자주 발생하는 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| `502 Bad Gateway` | signal-api 또는 signal-web 미실행 | `systemctl restart signal-api signal-web` |
| `curl /api/signals` → `503 signals_not_generated` | `data/signals.json` 미생성 | `cd /opt/apps/kospi-scanner && .venv/bin/python cli.py --strategy all --cache-root .cache --output-dir data --format signals_ui` 수동 실행 |
| `/_next/static/` JS 청크 400 Bad Request | standalone 빌드 후 정적 파일 미복사 — `.next/standalone/.next/static/` 가 비어 있음 | `bash scripts/restart.sh web-build` 실행 (빌드 + 복사 자동 처리) |
| Next.js 빌드 실패 (메모리 부족) | Droplet RAM 부족 | swap 추가: `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile` |
| cron 미실행 | 시간대 불일치 | `timedatectl set-timezone Asia/Seoul` 후 재설정 |
| `permission denied` on log/ | 실행 계정이 프로젝트 디렉토리 읽기/쓰기 불가 | `chmod -R o+rX /opt/apps/kospi-scanner` 후 `log/`, `data/`, `.cache/` 권한 재확인 |
| 디테일 페이지가 빈 데이터 / FACTOR BREAKDOWN 미노출 | 로컬에 signal-api 미실행 또는 `data/signals.json`에 decision 부재 | 9번 섹션의 로컬 dev 가이드대로 둘 다 띄우고, `cli.py --format signals_ui` 재실행 |

---

## 9. 로컬 개발 모드

VM 배포 없이 로컬에서 web + api를 동시에 띄워 테스트할 때 흐름이에요. 운영과 동일한 SSOT 모델을 따라요 (data/signals.json → signal-api → signal-web fetch).

### 9-1. 사전 준비

```bash
cd /Users/user/PycharmProjects/kospi-swing-scanner

# Python 가상환경 (최초 1회)
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r signal-api/requirements.txt

# Next.js 의존성 (최초 1회)
cd signal-web && npm install && cd ..
```

### 9-2. 데이터 생성 (signals.json)

signal-api는 `data/signals.json` 파일이 있어야 응답해요. 없으면 `503 signals_not_generated`를 반환해요.

```bash
# OHLCV 캐시가 이미 있다고 가정 (.cache/)
.venv/bin/python cli.py --strategy all --cache-root .cache --output-dir data --format signals_ui

# 캐시도 없는 첫 실행이면
.venv/bin/python scripts/collect.py --market KOSPI --cache-root .cache
.venv/bin/python cli.py --strategy all --cache-root .cache --output-dir data --format signals_ui

# 결과 확인
jq '.signals | length, .market_regime' data/signals.json
```

### 9-3. 두 서비스 동시 실행 (터미널 2개)

**터미널 A — signal-api (FastAPI :8000)**:

```bash
cd /Users/user/PycharmProjects/kospi-swing-scanner/signal-api

# data/ 디렉토리는 프로젝트 루트 기준 절대경로 또는 상대경로
SIGNAL_API_DATA_DIR=../data \
  ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

응답 확인:
```bash
curl -s http://127.0.0.1:8000/api/signals | jq '.signals | length, .market_regime'
```

**터미널 B — signal-web (Next.js :3000)**:

```bash
cd /Users/user/PycharmProjects/kospi-swing-scanner/signal-web

# .env.local 설정 (최초 1회)
echo 'NEXT_PUBLIC_API_URL=http://127.0.0.1:8000' > .env.local

npm run dev
```

브라우저: http://localhost:3000

### 9-4. 빠른 한 줄 (참고용)

`tmux` 또는 `concurrently`로 한 번에 띄우려면:

```bash
# tmux 사용 시 (각 페인에서)
tmux new -s kospi -d
tmux send-keys -t kospi 'cd signal-api && SIGNAL_API_DATA_DIR=../data ../.venv/bin/uvicorn app.main:app --port 8000 --reload' C-m
tmux split-window -t kospi
tmux send-keys -t kospi 'cd signal-web && npm run dev' C-m
tmux attach -t kospi
```

### 9-5. 데이터 갱신 흐름 (로컬)

```
[수동/cron Job B] cli.py --format signals_ui  →  data/signals.json 갱신 (시그널)
[수동/cron Job C] collect_live.py             →  data/market_snapshot.json 갱신 (현재가·시장지수)
        ↓
[자동] uvicorn --reload는 코드만 reload (signals.json / market_snapshot.json은 매 요청마다 read)
        ↓
[자동] signal-web: 2분마다 router.refresh() → 서버 컴포넌트 재실행 → 최신 현재가 표시
```

cron 없이 수동으로 `collect_live.py`를 재실행하면 즉시 반영돼요. signal-api 재시작 불필요.

### 9-6. 흔한 함정

| 증상 | 원인 | 해결 |
|------|------|------|
| `/api/signals` → 503 | data/signals.json 미존재 | 9-2 단계 실행 |
| 디테일 페이지 빈 화면 | `NEXT_PUBLIC_API_URL` 미설정 → 기본값 `http://localhost:8000` 사용. signal-api 미실행 | 9-3 터미널 A 실행 + .env.local 확인 |
| FACTOR BREAKDOWN 안 보임 | weights.yml 미로드 → ranking.decision: null | 프로젝트 루트에 weights.yml 존재 확인. cli.py 로그에 `weights.yml 로드 실패` 경고 있는지 점검 |
| market_regime null | regime_analysis.json 미존재 (1m 캐시 부족 시 1h 누락 가능) | `.venv/bin/python -c "from core.decision.market_regime import save_regime_analysis; save_regime_analysis('.cache')"` 후 cli.py 재실행 |
