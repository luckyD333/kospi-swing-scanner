# KOSPI Swing Scanner — ETF 포함 기능 추가 조사 보고서

**일시**: 2026-05-01  
**프로젝트**: `/Users/user/PycharmProjects/kospi-swing-scanner`  
**목표**: ETF 지원을 위한 현재 아키텍처 분석 및 통합 지점 파악

---

## 1. 유니버스 구성 (`core/universe.py`)

### 현재 구조
- **주요 함수**: `build_universe(client, target_date, filt)` (L43-233)
- **입력**: `DataClient`, 기준일, `UniverseFilter` (시총·유동성 범위)
- **출력**: `UniverseResult` (tickers 리스트 + 시총 맵 + 이름 맵)

### 시총 수집 흐름 (Step 6.5-A)

1. **모든 종목 리스트 획득** (L61)
   ```python
   all_tickers = client.get_tickers(filt.market, target_date)
   ```
   - 호출: `DataClient.get_tickers()` → fallback 체인 (네이버 → pykrx → FDR)

2. **1차 필터링 (네이버 추정값 + 20% 버퍼)**
   - non-strict 모드: `client.get_market_cap(filt.market, target_date)` (L120)
   - 범위: `[min×0.8, max×1.2]` (L129-130)

3. **KRX 공식 데이터 보강** (optional)
   - `client.krx_proxy.enrich_with_trade_info(filtered_pre, ...)` (L163-168)
   - 시총 정확값으로 업데이트

4. **최종 필터링**
   - 정확한 범위: `[min, max]` (L206-208)
   - 시총 상위 N 컷오프 (L213-223)

### 데이터 구조
```python
@dataclass
class UniverseFilter:
    min_market_cap_bil: float = 2000.0      # 억 단위
    max_market_cap_bil: float = 30000.0
    min_daily_volume: int = 100_000
    market: str = "KOSPI"                    # ← ETF를 위해 확장 필요
    max_universe_size: int | None = None
```

### ETF 통합 시사점
- `market` 파라미터가 현재 "KOSPI"/"KOSDAQ"만 지원
- **ETF용 新마켓 코드** 필요: "ETF" 또는 "KRX_ETF"
- 시총 필터는 ETF에도 적용 가능 (종목별 순자산)
- 거래량 필터도 동일하게 적용 가능

---

## 2. 데이터 소스 (`core/data_fetch.py` + `core/data_sources/`)

### 데이터 소스 아키텍처

**DailyDataSource 인터페이스** (base.py):
```python
@abstractmethod
def get_tickers(self, market: str, target_date: str) -> list[str]:
    """market: "KOSPI", "KOSDAQ", "KONEX" 등"""
    
@abstractmethod
def get_market_cap(self, market: str, target_date: str) -> pd.DataFrame:
    """선택적. 기본: 빈 DataFrame"""
```

### 각 소스의 ticker 획득 방식

#### 1. **NaverSource** (`naver.py`, L45-226)
```python
def get_tickers(self, market: str, target_date: str) -> list[str]:
    self._crawl_market_sum(market)  # market=KOSPI|KOSDAQ
    return [t for t, info in self._ticker_cache.items() 
            if info["market"] == market]
```

**크롤링 흐름**:
- URL: `https://finance.naver.com/sise/sise_market_sum.naver?sosok={0|1}&page={N}`
- sosok=0: KOSPI, sosok=1: KOSDAQ
- `pd.read_html()` + BeautifulSoup으로 테이블/href 파싱
- 종목명과 시총 캐시에 저장

**ETF 지원**: ❌ 미지원 (신규 URL 필요: `sise_etf_list.naver`)

#### 2. **PykrxSource** (`pykrx.py`, L17-48)
```python
def get_tickers(self, market: str, target_date: str) -> list[str]:
    from pykrx import stock
    return stock.get_market_ticker_list(target_date, market=market)
```

**pykrx ETF 메서드** (현재 미사용):
```python
from pykrx import etf
etf_tickers = etf.get_etf_ticker_list("20260501")
etf_ohlcv = etf.get_etf_ohlcv_by_date(start, end, ticker)
```

**ETF 지원**: ⚠️ 부분 (pykrx 라이브러리는 지원하나 PykrxSource에 미구현)

#### 3. **FDRSource** (`fdr.py`, L17-53)
```python
def get_tickers(self, market: str, target_date: str) -> list[str]:
    import FinanceDataReader as fdr
    df = fdr.StockListing(market)  # market="KOSPI"|"KOSDAQ"|"KONEX"
    return df["Code"].tolist()
```

**ETF 지원**: ❌ 미지원

#### 4. **KRXProxySource** (`krx_proxy.py`, L389-577)
```python
def get_tickers(self, market: str, target_date: str) -> list[str]:
    raise NotImplementedError("KRX Proxy는 전종목 리스트 미제공")

def enrich_with_trade_info(
    self, tickers: list[str], market: str, bas_dd: str, ...
) -> dict[str, dict]:
    """ticker별 시총/종가 보강 (공식 데이터)"""
```

**ETF 지원**: ⚠️ 조건부 (market 파라미터에 "ETF" 추가 가능, 서버 스펙 미확인)

### DataClient 구조 (`data_fetch.py`, L29-152)

```python
class DataClient:
    def __init__(
        self,
        ticker_list_sources: list[DailyDataSource] | None = None,
        ohlcv_sources: list[DailyDataSource] | None = None,
        ...
    ):
        self.ticker_list_sources = ticker_list_sources or [
            naver, PykrxSource(), FDRSource(),  # ← ETF 소스 추가 지점
        ]
```

---

## 3. CLI/Runner의 Market 필터링 (`cli.py` + `core/runner.py`)

### CLI 옵션 (cli.py, L50)

```python
parser.add_argument(
    "--market", default="KOSPI", 
    choices=["KOSPI", "KOSDAQ", "KRX"],  # ← ETF 미포함
)
```

### Runner 구현 (runner.py, L108-119)

```python
univ = build_universe(
    self.client,
    target_date,
    UniverseFilter(
        market=self.config.market,  # ← CLI에서 직접 전달
        ...
    ),
)
```

**호출 흐름**:
```
cli.py --market KOSPI
  ↓
RunnerConfig(market="KOSPI")
  ↓
UniverseFilter(market="KOSPI")
  ↓
DataClient.get_tickers(market="KOSPI")
  ↓
NaverSource.get_tickers(market="KOSPI")
```

### ETF 통합 시 필요 변경

1. CLI: `choices=["KOSPI", "KOSDAQ", "KRX", "ETF"]` 추가
2. Runner: market 문자열 전달 (변경 불필요)
3. 각 소스: market="ETF" 처리 추가

---

## 4. 테스트 패턴 (`tests/`)

### Mock 패턴 1: _StubSource (test_core_data_fetch.py, L18-49)

```python
class _StubSource(DailyDataSource):
    name = "stub"
    
    def __init__(self, df_factory):
        self.calls = []
        self._factory = df_factory
    
    def get_tickers(self, market: str, target_date: str) -> list[str]:
        return ["005930"]  # ← ticker 하드코딩
    
    def get_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        self.calls.append((ticker, start, end))
        return self._factory(ticker, start, end)
```

**테스트 예시**:
```python
def test_cache_hits_avoid_duplicate_fetch():
    stub = _StubSource(_make_df)
    cache = OhlcvCache(_make_client(stub))
    
    df1 = cache.get_or_fetch("005930", "20260101", "20260418")
    df2 = cache.get_or_fetch("005930", "20260101", "20260418")
    
    assert len(stub.calls) == 1  # fetch 1회만
```

### Mock 패턴 2: KRX Proxy (test_krx_proxy_mock.py, L34-80)

```python
MOCK_TRADE_INFO_RESPONSES = {
    "005930": {
        "item": {
            "market": "KOSPI",
            "code": "005930",
            "market_cap": 500_000_000_000_000,  # 원 단위
            "close_price": 70_000,
            "trading_volume": 10_000_000,
        }
    }
}
```

**Mock 방식**: `@patch('requests.get')` → 응답 제어

### ETF 테스트 추가 방안

1. **Stub for ETF**:
   ```python
   class _EtfStubSource(DailyDataSource):
       def get_tickers(self, market: str, target_date: str) -> list[str]:
           if market == "ETF":
               return ["379800", "379850", "152100"]  # ETF tickers
           return []
   ```

2. **Mock KRX Proxy for ETF**:
   ```python
   MOCK_ETF_TRADE_INFO = {
       "379800": {
           "item": {
               "market": "ETF",  # 또는 서버 스펙에 따라
               "code": "379800",
               "name": "KODEX 200",
               "market_cap": 3_000_000_000_000,
           }
       }
   }
   ```

---

## 5. pykrx ETF API 구체

### pykrx 라이브러리 ETF 메서드

```python
from pykrx import etf

# 1. ETF 종목 리스트
etf_tickers = etf.get_etf_ticker_list("20260501")
# → ["379800", "379850", "152100", ...]

# 2. ETF 기본정보
etf_info = etf.get_etf_info("379800")
# → {"코드": "379800", "명": "KODEX 200", "순자산": ..., ...}

# 3. ETF OHLCV
df = etf.get_etf_ohlcv_by_date("20260401", "20260501", "379800")
# → DataFrame(columns=['시가', '고가', '저가', '종가', '거래량', ...])
```

### NaverSource의 ETF 크롤링

**추정 URL 패턴**:
- `https://finance.naver.com/sise/sise_etf_list.naver?page=1`
- KOSPI/KOSDAQ과 동일한 테이블 구조로 크롤링 가능
- 현재 코드에서 URL만 변경하면 재사용 가능

---

## 6. 구현 로드맵

### Phase 1: pykrx ETF 지원 (1주)
**최소 변경, 최대 효과**

1. **신규**: `core/data_sources/etf.py` 생성
   ```python
   class EtfSource(DailyDataSource):
       def get_tickers(self, market: str, target_date: str) -> list[str]:
           if market != "ETF":
               return []
           from pykrx import etf
           return etf.get_etf_ticker_list(target_date)
   ```

2. **수정**: `core/data_fetch.py`
   ```python
   self.ticker_list_sources = [naver, EtfSource(), PykrxSource(), FDRSource()]
   ```

3. **수정**: `cli.py`
   ```python
   choices=["KOSPI", "KOSDAQ", "KRX", "ETF"]
   ```

4. **테스트**: `tests/test_etf_source.py` 추가

### Phase 2: 네이버 ETF 크롤링 (1주)
**더 견고한 fallback 구성**

- NaverSource._crawl_market_sum()에 ETF 분기 추가
- URL: `sise_etf_list.naver`
- 동일한 파싱 로직 재사용

### Phase 3: KRX Proxy ETF (필요시)
**공식 데이터 보강**

- KRX Proxy 서버 스펙 확인: market="ETF" 지원?
- 지원 시: `enrich_with_trade_info(..., market="ETF")` 추가

---

## 7. 핵심 통합 지점

| 항목 | 현재 | ETF 필요사항 |
|------|-----|-----------|
| CLI --market | KOSPI/KOSDAQ/KRX | + "ETF" |
| UniverseFilter.market | 문자열 패턴 | "ETF" 분기 |
| NaverSource.get_tickers() | sosok=0,1 | + ETF URL |
| PykrxSource.get_tickers() | stock API | + etf API |
| EtfSource (신규) | ❌ | 신규 클래스 |
| DataClient.ticker_list_sources | 3개 소스 | + etf 추가 |
| KRXProxySource | KOSPI/KOSDAQ/KONEX | "ETF" 조건부 |
| 테스트 | stock mocks | + ETF mocks |

---

## 8. 결론

**ETF 통합은 아키텍처상 매우 용이함:**

✅ **강점**:
- DailyDataSource 인터페이스 → 새 소스 추가 간단
- market 파라미터 기반 라우팅 → "ETF" 값 추가만으로 동작
- pykrx 라이브러리 자체가 완성된 ETF API 제공
- 시총/거래량 필터 직접 재사용 가능

⚠️ **주의**:
- NaverSource ETF 크롤링: URL/파싱 검증 필요
- KRXProxySource: market="ETF" 지원 여부 사전 확인 필수
- 테스트: ETF mock 데이터 작성

**추천 시작**: PykrxSource의 etf API 호출 (가장 빠르고 검증됨)
