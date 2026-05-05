# Cron 예시 — 수집 및 스캔 Job 자동화

KOSPI 스윙 스캐너의 수집(collect) 및 전략 스캔(strategy scan)을 cron으로 자동화하기 위한 예시 모음입니다.

## 1. 개요

### 왜 수집과 스캔을 분리하나

- **수집(collect)**: 네이버 금융에서 OHLCV 데이터를 가져와 `.cache/{tf}/{ticker}.parquet`에 저장
  - 네트워크 의존. 장 마감(15:30 KST) 이후 또는 장중 주기 실행
  - 증분 수집이므로 smart-skip(기본 활성화)으로 재수집 주기 회피
  
- **스캔(scan)**: 수집된 cache를 읽어 지표 계산 및 시그널 감지
  - 오프라인(cache 기반) 실행 가능. 매우 빠름 (수초 내)
  - `data/signals.json` + `data/market_snapshot.json` 갱신

### 의존성 흐름

```
[장중]
  Job C (*/2 9-14): collect_live.py → market_snapshot.json 현재가만 패치 (경량)
  Job D (1,31 9-15): collect.py (1m 포함) → cli.py → signals.json + market_snapshot.json 전체 재빌드

[장 마감 후]
  Job A (16:10): collect.py (1D 1W 1h 30m) → cache 채우기
  Job B (16:40): cli.py --strategy all → signals.json + market_snapshot.json 재빌드
```

수집이 먼저 완료되어야 스캔이 최신 데이터를 사용합니다.

---

## 2. 운영 Crontab (전체)

```crontab
SHELL=/bin/bash
LANG=ko_KR.UTF-8
LC_ALL=ko_KR.UTF-8
TZ=Asia/Seoul
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

# Job A: 장 마감 후 OHLCV 수집 (평일 16:10 KST)
10 16 * * 1-5 cd /opt/apps/kospi-scanner && .venv/bin/python scripts/collect.py --market KOSPI --cache-root .cache --timeframes 1D 1W 1h 30m >> /opt/apps/logs/kospi-scanner/collect.log 2>&1

# Job B: 일봉 신호 스캔 (평일 16:40 KST)
40 16 * * 1-5 cd /opt/apps/kospi-scanner && .venv/bin/python cli.py --strategy all --cache-root .cache --output-dir data --format signals_ui >> /opt/apps/logs/kospi-scanner/signals.log 2>&1

# Job C: 장중 현재가 경량 갱신 (2분 주기, 09:00-14:58 KST)
*/2 9-14 * * 1-5 cd /opt/apps/kospi-scanner && .venv/bin/python scripts/collect_live.py >> /opt/apps/logs/kospi-scanner/live.log 2>&1

# Job D: 장중 30분 주기 수집 + 신호 재스캔 (09:01-15:31 KST)
1,31 9-15 * * 1-5 cd /opt/apps/kospi-scanner && .venv/bin/python scripts/collect.py --market KOSPI --cache-root .cache --timeframes 1D 1h 30m 1m >> /opt/apps/logs/kospi-scanner/collect_intraday.log 2>&1 && .venv/bin/python cli.py --strategy all --cache-root .cache --output-dir data --format signals_ui >> /opt/apps/logs/kospi-scanner/signals_intraday.log 2>&1
```

### Job 실행 시간표

| Job | 스케줄 | 역할 |
|-----|--------|------|
| A | 평일 16:10 | 장 마감 후 전체 OHLCV 수집 (1D 1W 1h 30m) |
| B | 평일 16:40 | 일봉 기준 전략 전체 스캔 → signals.json |
| C | 평일 09:00-14:58, 2분 주기 | 시그널 종목 현재가만 경량 패치 |
| D | 평일 09:01-15:31, 30분 주기 | 1m 분봉 포함 전체 수집 + 전략 재스캔 |

**Job C vs D 역할 분리:**
- Job C: `collect_live.py` — 네트워크 호출 최소화. 시그널 종목의 현재가·등락률만 갱신
- Job D: `collect.py` + `cli.py` — 1m 분봉 수집으로 `minute_close` 설정 → `current_price ≠ entry_price` 보장. 30분 주기로 전략 시그널 전체 재계산

---

## 3. 옵션 설명

### collect.py

| 옵션 | 값 | 설명 |
|------|-----|------|
| `--market` | `KOSPI` \| `KOSDAQ` | 시장 선택. **단일값만 지원** (argparse `choices` 제한) |
| `--cache-root` | `.cache` | 캐시 저장 경로 |
| `--timeframes` | `1D 1W 1h 30m 1m` | 수집할 타임프레임. 장중 수집 시 `1m` 포함 필수 |
| `--lookback-days` | `90` | 과거 몇 일까지 수집할지 (기본: 90) |
| `--no-smart-skip` | flag | smart-skip 비활성화 (기본: 활성화) |
| `--max-universe` | `500` | 시총 상위 N개만 수집 (빠른 수집용) |

**`--market` 주의:** argparse가 단일값만 받으므로 `--market KOSPI --market KOSDAQ`는 마지막 값(KOSDAQ)만 적용됨. 두 시장을 모두 수집하려면 collect.py를 두 번 호출해야 한다.

**smart-skip (기본 활성화) 동작:**
- 1D는 마지막 수집 이후 20시간 이상, 1h는 1시간 이상 경과 후 재수집
- 오늘 날짜 데이터는 smart-skip 무시하고 항상 재수집 (미완료 봉 갱신)
- 비활성화하려면 `--no-smart-skip` 플래그 사용

---

## 4. 신규 전략 추가 시 운영 절차

### Step 1: 전략 코드 작성

`strategies/strategy_four_xxx.py`에 새 전략 클래스를 작성합니다.

```python
# strategies/strategy_four_xxx.py
from core.strategy_base import Strategy, Candidate

class StrategyFourXxx(Strategy):
    name = "strategy_four_xxx"

    def scan(self, ohlcv: dict, ...) -> list[Candidate]:
        pass
```

### Step 2: 전략 등록

`strategies/__init__.py`에 import + registry 한 줄 추가 (기존 전략은 수정 금지):

```python
from .strategy_four_xxx import StrategyFourXxx

REGISTRY: dict[str, Callable[[], Strategy]] = {
    ...
    "strategy_four_xxx": StrategyFourXxx,  # ← 새로 추가 (한 줄)
}
```

### Step 3: 단위 테스트 작성

```bash
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q
```

`--strategy all` 로 Job B·D가 자동으로 신규 전략을 포함하므로 별도 cron entry 추가는 불필요합니다.

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
cd /path/to/kospi-swing-scanner
.venv/bin/python cli.py ...
```

### 가상환경 활용

```bash
# ❌ cron에서 source가 동작하지 않을 수 있음
source .venv/bin/activate && python cli.py ...

# ✅ 권장
.venv/bin/python cli.py ...
```

### 백슬래시(`\`) 줄 연속 이식성

crontab에서 `\` 줄 연속은 cronie(RHEL/CentOS/Fedora)는 지원하지만 Vixie cron(Debian/Ubuntu 전통)은 공식 지원하지 않습니다. 이식성이 필요하면 **한 줄로 작성**하거나 별도 쉘 스크립트로 분리하세요.

```bash
# ✅ 한 줄 — 모든 cron 구현에서 동작
10 16 * * 1-5 cd /opt/apps/kospi-scanner && .venv/bin/python scripts/collect.py --market KOSPI --cache-root .cache >> logs/collect.log 2>&1
```

### 로그 관리

```bash
# 로그 디렉토리 생성
mkdir -p /opt/apps/logs/kospi-scanner

# 30일 이상 된 로그 삭제
find /opt/apps/logs/kospi-scanner -type f -name "*.log" -mtime +30 -delete
```

Logrotate 설정 (선택):

```
# /etc/logrotate.d/kospi-swing-scanner
/opt/apps/logs/kospi-scanner/*.log {
    monthly
    rotate 12
    compress
    delaycompress
    notifempty
    create 0640 user group
}
```

---

## 6. 트러블슈팅

### 수집 실패 시

**증상**: 스캔이 stale cache를 사용 (낡은 데이터)

**확인:**
```bash
cat .cache/manifest.json | jq '.collected_at'
tail -50 /opt/apps/logs/kospi-scanner/collect.log
```

**해결:**
- 네트워크 확인 (네이버 금융 접근 가능한지)
- `--lookback-days 7` 로 범위 축소 후 테스트
- `--max-universe 100` 으로 수집 종목 수 축소

### 현재가 = 진입가 (current_price == entry_price)

**원인**: 1m 분봉 미수집 시 `minute_close`가 설정되지 않아 `current_price`가 일봉 종가(= `entry_price`)로 fallback됨.

**해결**: Job D가 정상 실행 중인지 확인. `--timeframes`에 `1m` 포함 여부 확인.

```bash
ls .cache/1m/ | head -5  # 1m parquet 존재 여부
tail -20 /opt/apps/logs/kospi-scanner/collect_intraday.log
```

### 한글 출력 깨짐

**증상**: 로그에 `\xc3\xa4` 같은 이상한 문자

**해결**: crontab 맨 위에 `LANG=ko_KR.UTF-8` / `LC_ALL=ko_KR.UTF-8` 추가.

### Cron Job이 실행되지 않음

```bash
# crontab 확인
crontab -l

# cron 데몬 로그 (Linux)
tail -100 /var/log/syslog | grep CRON
# 또는
journalctl -u cron --since "1 hour ago"
```

**흔한 원인:**
- cron daemon 미실행 → `sudo systemctl start cron`
- 절대 경로 오류 → `which python` 으로 확인
- 스크립트 권한 부재 → `chmod +x scripts/collect.py`

### 네트워크 타임아웃

**증상**: collect.py가 네이버 금융에서 hang

**해결:**
- `--lookback-days 7` (3개월 → 1주로 축소)
- `--max-universe 100` (전체 → 상위 100개로 축소)

---

## 7. 참고

- **전략 상세**: [`docs/strategy_d_v2_spec.md`](./strategy_d_v2_spec.md)
- **데이터 소스**: [`docs/korean_stock_data_sources_guide.md`](./korean_stock_data_sources_guide.md)
- **CLI 옵션**: `python cli.py --help`
- **수집 옵션**: `python scripts/collect.py --help`

---

**마지막 업데이트**: 2026-05-05
