# Cron 예시 — 수집 및 스캔 Job 자동화

KOSPI 스윙 스캐너의 수집(collect) 및 전략 스캔(strategy scan)을 cron으로 자동화하기 위한 예시 모음입니다.

## 1. 개요

### 왜 수집과 스캔을 분리하나

- **수집(collect)**: 네이버 금융에서 OHLCV 데이터를 가져와 `.cache/{tf}/{ticker}.parquet`에 저장
  - 네트워크 의존. 장 마감(15:30 KST) 이후 실행 권장
  - 여러 타임프레임(1D, 1W, 1h, 30m) 동시 수집 가능
  - 증분 수집이므로 smart-skip(기본 활성화)으로 재수집 주기 회피
  
- **스캔(scan)**: 수집된 cache를 읽어 지표 계산 및 시그널 감지
  - 오프라인(cache 기반) 실행 가능. 매우 빠름 (수초 내)
  - 여러 전략을 병렬 실행 가능
  - manifest.json 갱신이 필요하므로 시간 분리로 동시 쓰기 회피

### 의존성 흐름

```
수집(23:00) → cache 채우기
       ↓
스캔(23:30, 23:35, 23:40, ...) → cache 읽고 결과 저장
```

수집이 먼저 완료되어야 스캔이 최신 데이터를 사용합니다.

---

## 2. 수집 Job 예시

### 기본 설정

KOSPI/KOSDAQ를 평일 23:00에 수집합니다. 로그는 `logs/collect.log`에 append됩니다.

```bash
#!/bin/bash

# 프로젝트 루트로 이동 (cron은 홈 디렉토리에서 실행)
cd /path/to/kospi-swing-scanner

# 환경 변수 설정 (한글 출력, 타임존)
export LANG=ko_KR.UTF-8
export LC_ALL=ko_KR.UTF-8
export TZ=Asia/Seoul
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

# 로그 디렉토리 생성
mkdir -p logs

# KOSPI/KOSDAQ 수집 (smart-skip 기본 활성화 — TF별 최소 주기 미달 시 기존 종목 건너뜀)
.venv/bin/python scripts/collect.py \
  --market KOSPI \
  --market KOSDAQ \
  --cache-root .cache \
  --timeframes 1D 1W 1h 30m \
  --lookback-days 90 \
  --max-universe 500 \
  >> logs/collect.log 2>&1
```

### Crontab Entry

```crontab
# 환경 변수 (crontab 맨 위에 한 번만)
SHELL=/bin/bash
LANG=ko_KR.UTF-8
LC_ALL=ko_KR.UTF-8
TZ=Asia/Seoul
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

# 수집 job — 평일 23:00 (KOSPI 장 마감 후 ~7.5시간)
0 23 * * 1-5 /path/to/kospi-swing-scanner/scripts/collect_job.sh >> /path/to/kospi-swing-scanner/logs/cron.log 2>&1
```

**주의:**
- `1-5` = 월~금 (0=일, 6=토)
- `/path/to/kospi-swing-scanner` 는 절대 경로로 수정
- `>> logs/cron.log 2>&1` 로 stdout/stderr 모두 기록

### 옵션 설명

| 옵션 | 값 | 설명 |
|------|-----|------|
| `--market` | `KOSPI \| KOSDAQ` | 시장 선택 (여러 개 지정 가능) |
| `--cache-root` | `.cache` | 캐시 저장 경로 |
| `--timeframes` | `1D 1W 1h 30m` | 수집할 타임프레임 |
| `--lookback-days` | `90` | 과거 몇 일까지 수집할지 (기본: 90) |
| `--no-smart-skip` | flag | smart-skip 비활성화 (기본: 활성화 — TF별 최소 주기 미달 시 기존 종목 skip) |
| `--max-universe` | `500` | 시총 상위 N개만 수집 (빠른 수집용) |

**smart-skip (기본 활성화) 동작:**
- 1D는 마지막 수집 이후 20시간 이상, 1h는 1시간 이상 경과 후 재수집
- 10~30분 주기로 수집 job을 돌려야 할 때 유용 (중복 네트워크 호출 회피)
- 비활성화하려면 `--no-smart-skip` 플래그 사용

---

## 3. 전략별 스캔 Job 예시

### 각 전략을 독립 Job으로 실행

수집 완료 후 여러 전략을 병렬 실행합니다. **manifest.json 동시 쓰기 회피를 위해 각 전략 job을 5분 이상 띄웁니다.**

#### Job 1: Strategy One D v2 (Mean Reversion, 일봉)

```bash
#!/bin/bash
cd /path/to/kospi-swing-scanner
export LANG=ko_KR.UTF-8
export TZ=Asia/Seoul
mkdir -p logs/scan

.venv/bin/python cli.py \
  --strategy strategy_one_d_v2 \
  --market KOSPI \
  --cache-root .cache \
  --output-dir scan_results \
  --format json \
  --top 20 \
  >> logs/scan/strategy_one_d_v2.log 2>&1
```

#### Job 2: Strategy One 1h v2 (Mean Reversion, 1시간봉)

```bash
#!/bin/bash
cd /path/to/kospi-swing-scanner
export LANG=ko_KR.UTF-8
export TZ=Asia/Seoul
mkdir -p logs/scan

.venv/bin/python cli.py \
  --strategy strategy_one_1h_v2 \
  --market KOSPI \
  --cache-root .cache \
  --output-dir scan_results \
  --format json \
  --top 20 \
  >> logs/scan/strategy_one_1h_v2.log 2>&1
```

#### Job 3: Strategy Two (Cross-sectional Momentum, Jegadeesh-Titman)

```bash
#!/bin/bash
cd /path/to/kospi-swing-scanner
export LANG=ko_KR.UTF-8
export TZ=Asia/Seoul
mkdir -p logs/scan

.venv/bin/python cli.py \
  --strategy strategy_two_cross_sectional_momentum \
  --market KOSPI \
  --cache-root .cache \
  --output-dir scan_results \
  --format json \
  --top 20 \
  >> logs/scan/strategy_two_cross_sectional_momentum.log 2>&1
```

#### Job 4: Strategy Three (Trend Following, Donchian 20일)

```bash
#!/bin/bash
cd /path/to/kospi-swing-scanner
export LANG=ko_KR.UTF-8
export TZ=Asia/Seoul
mkdir -p logs/scan

.venv/bin/python cli.py \
  --strategy strategy_three_trend_following \
  --market KOSPI \
  --cache-root .cache \
  --output-dir scan_results \
  --format json \
  --top 20 \
  >> logs/scan/strategy_three_trend_following.log 2>&1
```

### Crontab Entry (전략 Job 집합)

```crontab
# 수집 완료 후 5분 간격으로 각 전략 실행
# (manifest.json 동시 쓰기 회피 + 순차 안정성)

SHELL=/bin/bash
LANG=ko_KR.UTF-8
LC_ALL=ko_KR.UTF-8
TZ=Asia/Seoul
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

# 수집 job — 평일 23:00
0 23 * * 1-5 /path/to/kospi-swing-scanner/scripts/collect_job.sh

# 스캔 job — 23:30, 23:35, 23:40, 23:45 (수집 후 30분부터 시작)
30 23 * * 1-5 /path/to/kospi-swing-scanner/scripts/scan_strategy_one_d_v2.sh
35 23 * * 1-5 /path/to/kospi-swing-scanner/scripts/scan_strategy_one_1h_v2.sh
40 23 * * 1-5 /path/to/kospi-swing-scanner/scripts/scan_strategy_two.sh
45 23 * * 1-5 /path/to/kospi-swing-scanner/scripts/scan_strategy_three.sh
```

### 스캔 Job 실행 시간표

| 시간 | Job | 설명 |
|------|-----|------|
| 23:00 | `collect_job.sh` | 수집 시작 (보통 10~30분 소요) |
| 23:30 | `scan_strategy_one_d_v2.sh` | Strategy 1 (일봉) |
| 23:35 | `scan_strategy_one_1h_v2.sh` | Strategy 1 (1시간) |
| 23:40 | `scan_strategy_two.sh` | Strategy 2 (Momentum) |
| 23:45 | `scan_strategy_three.sh` | Strategy 3 (Trend Following) |

**각 스캔은 수초 내 완료되므로 5분 간격이면 충분합니다.**

---

## 4. 신규 전략 추가 시 운영 절차

### Step 1: 전략 코드 작성

`strategies/strategy_four_xxx.py`에 새 전략 클래스를 작성합니다.

```python
# strategies/strategy_four_xxx.py
from core.strategy_base import Strategy, Candidate

class StrategyFourXxx(Strategy):
    name = "strategy_four_xxx"  # CLI에서 노출될 이름
    
    def scan(self, ohlcv: dict, ...) -> list[Candidate]:
        # 전략 로직 구현
        pass
```

### Step 2: 전략 등록

`strategies/__init__.py`에 import + registry 한 줄 추가 (기존 전략은 수정 금지):

```python
from .strategy_four_xxx import StrategyFourXxx

REGISTRY: dict[str, Callable[[], Strategy]] = {
    "strategy_one_d_v2": lambda: StrategyOneDv2(timeframe="1D"),
    "strategy_one_w_v2": lambda: StrategyOneDv2(timeframe="1W"),
    "strategy_one_1h_v2": lambda: StrategyOneDv2(timeframe="1h"),
    "strategy_one_30m_v2": lambda: StrategyOneDv2(timeframe="30m"),
    StrategyTwoCrossSectionalMomentum.name: StrategyTwoCrossSectionalMomentum,
    StrategyThreeTrendFollowing.name: StrategyThreeTrendFollowing,
    "strategy_four_xxx": StrategyFourXxx,  # ← 새로 추가 (한 줄)
}
```

### Step 3: 단위 테스트 작성

`backtest_engine/tests/` 또는 `tests/`에 테스트 추가. 기존 테스트는 수정하지 않습니다:

```bash
pytest backtest_engine/tests/ -v  # 71개+ 통과 확인
```

### Step 4: Cron Entry 추가

`/path/to/kospi-swing-scanner/scripts/scan_strategy_four_xxx.sh`를 생성:

```bash
#!/bin/bash
cd /path/to/kospi-swing-scanner
export LANG=ko_KR.UTF-8
export TZ=Asia/Seoul
mkdir -p logs/scan

.venv/bin/python cli.py \
  --strategy strategy_four_xxx \
  --market KOSPI \
  --cache-root .cache \
  --output-dir scan_results \
  --format json \
  --top 20 \
  >> logs/scan/strategy_four_xxx.log 2>&1
```

그리고 crontab에 한 줄 추가 (기존 entry는 수정 금지):

```crontab
50 23 * * 1-5 /path/to/kospi-swing-scanner/scripts/scan_strategy_four_xxx.sh
```

**핵심: 기존 전략(1, 2, 3)의 cron entry와 코드는 절대 수정하지 않습니다. 신규 전략만 추가 job으로 등록합니다.**

---

## 5. 운영 팁

### 환경 변수 설정

Crontab의 맨 위에 필수 환경 변수를 정의합니다:

```crontab
SHELL=/bin/bash
LANG=ko_KR.UTF-8
LC_ALL=ko_KR.UTF-8
TZ=Asia/Seoul
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
MAILTO=your-email@example.com  # 에러 시 알림 (선택)
```

- **LANG / LC_ALL**: 한글 출력 인코딩
- **TZ**: Asia/Seoul (한국 시간)
- **PATH**: Python/bash 등 실행 파일 경로
- **MAILTO**: cron 에러 메시지 받을 이메일 (생략 가능)

### 절대 경로 사용

Cron은 home 디렉토리에서 실행되므로 `cd` 필수:

```bash
cd /path/to/kospi-swing-scanner  # 절대 경로
.venv/bin/python cli.py ...
```

상대 경로 `.venv/bin/python`은 작동하지 않습니다.

### 가상환경 활용

`source .venv/bin/activate` 대신 직접 호출:

```bash
# ❌ 작동 안 함 (cron에서 source가 먹지 않을 수 있음)
source .venv/bin/activate
python cli.py ...

# ✅ 권장 (명시적)
.venv/bin/python cli.py ...
```

### 로그 관리

#### 로그 디렉토리 생성

```bash
mkdir -p /path/to/kospi-swing-scanner/logs/scan
```

#### Logrotate 설정 (선택)

매월 1일 로그 자동 압축:

```bash
# /etc/logrotate.d/kospi-swing-scanner
/path/to/kospi-swing-scanner/logs/*.log {
    monthly
    rotate 12
    compress
    delaycompress
    notifempty
    create 0640 user group
}
```

#### Python 로깅 (대안)

코드에서 `RotatingFileHandler` 사용:

```python
from logging.handlers import RotatingFileHandler
handler = RotatingFileHandler("logs/scan.log", maxBytes=10*1024*1024, backupCount=5)
```

### Manifest.json 동시 쓰기 회피

여러 전략이 동시에 `scan_results/manifest.json`을 쓰면 충돌합니다.

**해결책:**
1. **시간 분리 권장** (위 예시처럼 5분 간격)
2. 또는 각 전략마다 별도 `--output-dir` 지정:

```bash
.venv/bin/python cli.py \
  --strategy strategy_one_d_v2 \
  --output-dir scan_results_strategy_1_d \
  ...
```

---

## 6. 트러블슈팅

### 수집 실패 시

**증상**: 스캔이 stale cache를 사용 (낡은 데이터)

**확인:**
```bash
# manifest.json에서 수집 시간 확인
cat .cache/manifest.json | jq '.collected_at'

# 로그 확인
tail -50 logs/collect.log
```

**해결:**
- 네트워크 확인 (네이버 금융 접근 가능한지)
- `--lookback-days` 줄여서 빠르게 테스트 (`--lookback-days 7`)
- `--max-universe` 줄여서 수집 범위 축소 (`--max-universe 100`)

### 한글 출력 깨짐

**증상**: 로그에 `\xc3\xa4` 같은 이상한 문자

**해결:**
```crontab
LANG=ko_KR.UTF-8
LC_ALL=ko_KR.UTF-8
```

crontab 맨 위에 추가.

### 네트워크 타임아웃

**증상**: collect.py가 네이버 금융에서 hang

**해결:**
- `--lookback-days 7` (3개월 → 1주로 축소)
- `--max-universe 100` (전체 → 상위 100개로 축소)
- 재시도 간격 조정 (cron 재실행 전 30분 대기)

### Cron Job이 실행되지 않음

**확인:**
```bash
# crontab 문법 검증
crontab -l | grep kospi

# cron 데몬 로그 (macOS)
log stream --predicate 'process == "cron"' --level debug

# cron 데몬 로그 (Linux)
tail -100 /var/log/syslog | grep CRON
```

**흔한 원인:**
- cron daemon 미실행 → `sudo systemctl start cron` (Linux)
- 절대 경로 오류 → `which python` 으로 확인
- 스크립트 권한 부재 → `chmod +x scripts/collect_job.sh`

### 로그 용량 증가

**증상**: 로그 파일이 GB 단위로 증가

**해결:**
- Logrotate 설정 (위 "로그 관리" 섹션)
- 또는 주기적 수동 삭제:

```bash
# 30일 이상 된 로그 삭제
find /path/to/kospi-swing-scanner/logs -type f -name "*.log" -mtime +30 -delete
```

---

## 7. 참고

- **전략 상세**: [`docs/strategy_d_v2_spec.md`](./strategy_d_v2_spec.md)
- **데이터 소스**: [`docs/korean_stock_data_sources_guide.md`](./korean_stock_data_sources_guide.md)
- **CLI 옵션**: `python cli.py --help`
- **수집 옵션**: `python scripts/collect.py --help`

---

**마지막 업데이트**: 2026-05-02
