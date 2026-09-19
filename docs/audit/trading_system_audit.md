# Trading System Audit — KOSPI Swing Scanner

- **감사일**: 2026-06-11
- **감사 범위**: 5개 전략, backtest_engine, HMM market regime, ensemble 가중치, 데이터·캐시, 운영
- **감사 방법**: 4개 병렬 감사 에이전트 (엔진/전략/HMM·앙상블/데이터·운영) + 핵심 주장 전수 직접 코드 재검증. 모든 발견은 직접 검증 통과한 것만 채택, 검증 실패 주장은 §11 기각 목록에 기록.
- **제약**: 투자 조언 아님. 성과 개선 튜닝 제안 없음. 알고리즘 정확성·데이터 누수·체결 현실성·운영 리스크만 평가.

---

## 1. Executive Judgment

## **CONDITIONAL PASS**

- **운영 스캔 파이프라인 (시그널 생성)**: 통과. 운영 시그널 산출 경로에 lookahead 없음 — Donchian 채널 당일 제외(검증), incomplete bar 가드 존재, HMM은 마지막 시점 score만 소비(smoothed posterior == filtered posterior at T), holding 집계는 leakage-free SMA proxy 사용.
- **백테스트 절대 수치**: 보류 조건부. S1 엔진은 same-bar close 진입, WF 히스토리는 survivor bias, 슬리피지 미모델 — 절대 성과(Sharpe/수익률)는 낙관 편향. **상대 비교(파라미터 A vs B, 전략 간 비교)는 동일 편향 공유로 대체로 유효**하나 stop 의존 파라미터를 N-bar scorer로 비교한 경우는 무효.
- Critical 0건 (에이전트 제기 4건 중 2건 직접 검증으로 기각, 2건 HIGH로 강등), High 4건, Medium 7건.

---

## 2. Top 10 Findings

### F1. [HIGH] BacktestEngine(S1)이 시그널 봉 close에 same-bar 진입

- **파일**: `backtest_engine/strategy.py:267` (`entry_price = float(current["close"])`), `backtest_engine/engine.py:200-242` (`entry_time=t`)
- **증거**: `check_entry(df, idx)`가 idx 봉의 close/RSI/BB로 조건 판정 후 그 봉 close를 entry_price로 반환, 엔진이 같은 시점 t에 포지션 생성.
- **왜곡**: 실제는 장 마감 후 시그널 → 익일 진입. same-bar 진입은 시그널 확정 전 가격에 산 셈 — S1 백테스트 수익률 +0.5~2%p/년 낙관 추정.
- **참고**: S2~S5의 WF 검증 경로(`scan_adapter.py:126,292`)는 **T+1 open 진입**으로 올바름. 이 결함은 `BacktestEngine` 기반 S1 결과에만 해당.
- **수정**: `BacktestConfig.next_bar_entry=True` 옵션 추가, T+1 open 체결 후 기존 결과와 delta 보고.
- **방지 테스트**: same-bar vs next-bar gap 정량 테스트 (§9 제안 T-1).
- **후속 조치 (2026-06-12)**: `next_bar_entry` 구현 완료 + T-1 테스트 3종
  (`backtest_engine/tests/test_audit_next_bar_entry.py`). 측정 delta
  (`scripts/audit_f1_entry_timing.py`, .cache_wf 341종목 2025-05-19~2026-05-19, 기본 config):
  수익률 -0.022%p (-1.290→-1.312%), Sharpe -0.103 (-0.307→-0.411), 승률 -4.17%p (24 trades 중 1건 반전).
  "+0.5~2%p/년 낙관" 추정 대비 포트폴리오 수준 영향 미미 — 단 24 trades 소표본·생존편향(F2) 데이터 한정.
  이후 S1 WF/백테스트는 `next_bar_entry=True` 사용 권장.

### F2. [HIGH] Survivor bias — 현재 universe로 과거 1년 백테스트

- **파일**: `scripts/collect_wf_history.py:63-69` (`manifest.get("tickers")` = 현재 상장 목록), `core/universe.py`
- **증거**: WF 히스토리 수집이 `.cache/manifest.json`(현 시점) universe 기반. 기간 내 상장폐지·거래정지 종목 부재, 신규상장 종목은 과거 구간 데이터 결측으로 자연 제외.
- **왜곡**: 백테스트 universe = 생존 종목만 → 성과 상방 편향. 1년 윈도우라 수십%p 수준은 아니나, 하락 후 상폐된 종목이 빠지므로 특히 mean reversion(S1)·pullback(S4)의 꼬리 리스크 과소평가.
- **수정**: (a) 과거 시점 universe 스냅샷 보관 시작 (이후 WF부터 사용), (b) 기존 결과에는 "생존 편향 포함, 최근 1년 한정" 해석 한계 명시.
- **방지 테스트**: 과거 universe 스냅샷 도입 후 현재 universe와 차집합 > 0 검증.

### F3. [HIGH] HMM `predict_proba(X)` smoothing — 과거 시점 라벨에 미래 관측 포함

- **파일**: `core/decision/market_regime.py:238-248` (`m.fit(X)` 전체 기간 → `model.predict_proba(X)`)
- **증거**: forward-backward smoothing의 시점 t posterior는 `P(X[t+1:T]|state)`를 포함. `history[]`의 모든 과거 score와 `windows`(3d/7d/30d/90d 평균)가 오염.
- **운영 영향 없음 (중요)**: 운영이 소비하는 `current_score`는 마지막 시점 — 마지막 시점의 smoothed posterior는 filtered posterior와 동일하므로 **운영 시그널에는 lookahead 없음**. 또한 `optimize_full.py`/`wf_validate_*`/`wf_strategy_compare.py`에 regime 소비 없음을 grep으로 확인, holding 집계(`aggregate_holding_recommendations.py:6`)는 HMM이 아닌 20D SMA slope proxy 사용 — **백테스트 오염 경로 현재 없음**.
- **잔존 리스크**: (a) `history`/`windows`는 "당시에 알 수 있었던 값"이 아님 — UI 표시·사후 분석에 쓰면 hindsight, (b) 향후 누군가 history 라벨로 regime별 성과를 집계하면 즉시 leakage 도입.
- **수정**: ① history 백필을 expanding-window fit으로 교체(시점 t는 X[:t+1]만) 또는 ② "history는 smoothed, 시점별 의사결정에 사용 금지" 정책을 docstring + 코드 주석으로 고정.
- **방지 테스트**: §9 제안 T-2 (미래 데이터 append 시 과거 라벨 변동률 측정).

### F4. [HIGH] N-bar PnL scorer(stop/target 무시)가 S2~S5 entry-param WF에 사용

- **파일**: `backtest_engine/scan_adapter.py:109-131` (`make_scan_pnl_scorer`), `scripts/wf_validate_s2_to_s5.py:288`
- **증거**: T+1 open 진입 → 고정 N봉 후 close 청산. `Candidate.stop_loss`/`target_2` 미평가. (설계 의도는 docstring에 명시된 인지된 한계 — `wf_validate_s3_exits.py:187`과 holding 집계는 bartracker scorer 사용.)
- **왜곡**: stop/target 분포에 영향을 주는 파라미터(예: atr_stop_mult, 변동성 필터)를 N-bar scorer로 비교하면 손절 미반영 — 고변동 파라미터가 과대평가될 수 있음. 2026-05-14 WF로 채택된 12개 파라미터 중 청산 의존 항목 재검토 필요.
- **수정**: WF 정책화 — 진입 전용 파라미터만 pnl scorer 허용, stop/target 의존 파라미터는 bartracker 필수. 각 WF 스크립트 출력에 사용 scorer 명시.
- **기존 방지 테스트 있음**: `test_target_reached_yields_higher_pnl_than_pnl_scorer` (scorer 간 차이 자체는 이미 검증됨).

### F5. [MEDIUM] 비용 모델: 단일 0.30% 왕복 — 슬리피지·스프레드·시장충격 미분리

- **파일**: `backtest_engine/engine.py:32` (`commission_pct=0.0030`, 매수/매도 각 0.15%), `scan_adapter.py:31,158`
- **2026년 실제 세제 (WebSearch 확인)**: KOSPI 매도 = 거래세 0.05% + 농특세 0.15% = **0.20%**, KOSDAQ 매도 = **0.20%** (2026-01 양도분부터 환원 인상). 위탁수수료 ~0.015%×2.
- **평가**: 모델 0.30% vs 세금+수수료 ≈ 0.23% → 슬리피지·스프레드 여유분 0.07%뿐. 코스닥 소형주·저유동 ETF의 스프레드(0.1~0.5%)와 시장충격 미반영. "paper trading 실측 기반" 주석 있으나 실측 데이터 출처 미문서화.
- **왜곡**: 회전율 높은 전략(S2 주 1-2회 리밸런스)일수록 과소. 거래 12회/년 기준 ~1%p/년 수준의 낙관.
- **수정**: 수수료/매도세/슬리피지 3분해 + 슬리피지 0.1~0.3% 민감도 표 산출. 유동성 대비 주문 규모(% of ADV) 가드 추가.
- **후속 조치 (2026-06-12)**: 민감도 표 산출 완료 (`scripts/audit_f5_f6_cost_sensitivity.py`,
  BarTracker 청산, 9 OOS 윈도우 2025-05~2026-05, default config, top_n=5, holding 3봉).
  수익률 = per-trade pnl 단순 합 (복리·포지션 사이징 미반영). 비용 = 세금·수수료 0.23% + 슬리피지.

  | 전략 (trades) | 현행 0.30% | slip0.1 (0.33%) | slip0.2 (0.43%) | slip0.3 (0.53%) |
  |---|---|---|---|---|
  | S1 (12) | +33.1% | +32.7% | +31.5% | +30.3% |
  | S2 (893) | +199.8% | +173.0% | +83.7% | **-5.6%** |
  | S3 (769) | +277.8% | +254.8% | +177.9% | +101.0% |
  | S4 (895) | -48.2% | -75.0% | -164.5% | -254.0% |
  | S5 (71) | -64.8% | -67.0% | -74.1% | -81.2% |

  S1·S3 은 slip 0.3% 에서도 양(+) 유지. S2 는 mean +0.22%/trade 고회전이라 비용 민감 최대 —
  slip 0.3% 에서 음전. S4·S5 는 현행 비용에서 이미 음수 (단 F6 갭 제한 시 S4 양전 — 아래 참조).
  % of ADV 가드는 미구현 (잔여 항목).

### F6. [MEDIUM] 상한가·VI 체결 모델 부재 (돌파 전략 낙관)

- **파일**: `scan_adapter.py:126,292` (T+1 open 무조건 체결 가정), `strategies/strategy_three_trend_following.py:170-172` (전일 +30% 후보 제외 가드는 존재)
- **왜곡**: S3/S5 돌파 시그널은 급등일에 몰림 → T+1 갭상승·점상한가 시 open 체결 불가능한데 모델은 체결 가정. 상승 추격 체결가 과소(유리) 편향. PR-E 가드(+30% 제외, +20% 페널티)가 극단은 차단하나 10~29% 갭은 미반영.
- **수정**: T+1 open이 전일 close 대비 +N% 이상이면 체결 skip 또는 체결가 페널티 옵션을 scorer에 추가해 민감도 측정.
- **후속 조치 (2026-06-12)**: 갭상승 체결 skip 민감도 측정 완료 (F5 와 동일 스크립트, 비용 0.30% 고정).

  | 전략 | 갭 무제한 | 갭>+3% skip | 갭>+10% skip |
  |---|---|---|---|
  | S1 | +33.1% (12) | +33.1% (12) | +33.1% (12) |
  | S2 | +199.8% (893) | +581.9% (703) | +321.9% (869) |
  | S3 | +277.8% (769) | +378.5% (662) | +394.9% (756) |
  | S4 | -48.2% (895) | **+65.1%** (735) | +75.5% (869) |
  | S5 | -64.8% (71) | -51.4% (64) | -45.6% (70) |

  **편향 방향은 추정과 반대**: 갭상승 추격 trade 가 순손실 집단이라, 무조건 체결 가정은
  백테스트를 낙관이 아니라 보수 쪽으로 끌었음 — 실제로 체결 불가(점상한가 등)였다면 성과는
  오히려 개선. 부수 발견: 갭>+3% 진입 제한이 S2/S3/S4 에 일관된 개선 (S4 양전) — 운영 반영
  전 별도 WF 검증 필요 (단일 데이터셋·생존편향(F2) 주의, 2026-05-14 단일 그리드 교훈).
- **WF 검증 (2026-06-12)**: `scripts/wf_validate_gap_filter.py`, 9윈도우, per-trade 전 기간
  수집 + threshold grid {0.01, 0.03, 0.05, 0.10, 무제한}.
  - threshold train-best 선택(CPO)은 5전략 전부 **FAIL** — CV 0.50~1.03 unstable,
    S2 decay 0.617·S4 2.265. threshold 재튜닝은 금지 (2026-05-14 교훈 재확인).
  - 단 두 가지는 견고: (1) 45개 train 선택 중 "무제한" 이 best 인 윈도우 **0회** — 필터
    존재 자체는 전 윈도우 일관. (2) 고정 +3% 의 윈도우별 OOS 개선: S2 **7/9** (+207→+587%),
    S4 **6/9** (-50→+62% 양전), S3 4/9 (+268→+368%, 시점 의존), S5 3/9 (음수 유지),
    S1 영향 없음 (갭상승 진입 0건).
  - **권고**: 튜닝 없는 고정 +3% 를 S2·S4 한정 채택 후보로 (S3·S5 보류). trade_plan 의
    limit 진입 필드(populate_limit_fields) 로 지정가 진입하는 운영 흐름에서는 갭상승 추격이
    이미 차단되므로, 본 필터는 백테스트-운영 체결 방식 괴리의 정량화이기도 함 — scorer
    레벨 옵션 반영이 우선, 전략 코드 변경은 별도 결정.
  - scorer 옵션 구현 완료 (2026-06-12): `ScanPnlConfig`/`ScanBarConfig.max_entry_gap_pct`
    (기본 None=기존 동작). 이후 WF 는 운영 체결 방식 근사 시 0.03 고정값 사용.

### F7. [MEDIUM] regime 가중치 매트릭스가 hand-set 미검증 휴리스틱

- **파일**: `weights.yml:87-109`, git `c0d6a59`/`2871fa3` (2026-05-19)
- **증거**: BULL/NEUTRAL/BEAR × 5전략 배수(1.4/0.3/0.0 등)가 백테스트 산출이 아닌 수기 작성 (커밋 메시지·주석 확인). **hindsight 최적화는 아님** (이중 과최적화 아님 — §11 기각 참조). 그러나 검증도 안 됨.
- **왜곡**: BEAR에서 bull_flag 0.0 차단 같은 강한 결정이 근거 없이 적용 — 좋을 수도 나쁠 수도 있는데 측정한 적 없음.
- **수정**: regime별 전략 성과를 leakage-free 라벨(SMA proxy 또는 expanding HMM)로 분리 집계해 매트릭스 calibrate, weights.yml에 `metadata:` (산출 기간/방법/OOS 성과) 블록 추가.
- **2026-07-15 변경**: `fng_modifier`는 runtime 점수·차단·보유기간 추천에서 제거하고 구형 설정 라운드트립 호환만 유지. F&G는 정보용 표시로 한정.

### F8. [MEDIUM] HMM 일일 재fit으로 history 점수 불안정 (train/serve drift)

- **파일**: `core/decision/market_regime.py:227-244` (5-seed 재학습, `scripts/collect.py` 매일 호출)
- **증거**: label semantic은 `argmax(state mean return)`(line 245-246)으로 고정되어 라벨 반전은 방지되나, 매일 모델 자체가 달라져 같은 과거 날짜 score가 매일 변동. `windows` 7d/30d 평균도 함께 흔들림.
- **왜곡**: "어제 BULL이었다"는 진술이 오늘 재계산에서 바뀔 수 있음 — regime 기반 가중치의 일관성 저하, 사후 분석 재현 불가.
- **수정**: 일별 current_score를 append-only 저널로 누적(과거 점수 불변), history 백필은 참고용으로 격리.

### F9. [MEDIUM] `latest_business_day()` 공휴일 미고려 — 캘린더 이원화

- **파일**: `core/dates.py:13-32` (docstring 자인: "한국 공휴일은 미고려"), `core/decision/signal_status.py`는 XKRX 캘린더 사용
- **왜곡**: 공휴일 다음 날 두 함수의 "최근 영업일" 판정 불일치 → stale 판정·수집 기준일 오류 가능 (설·추석 연휴 직후).
- **수정**: `latest_business_day()`에 XKRX 캘린더 적용해 단일화.

### F10. [MEDIUM] 캐시 staleness가 manifest 단위 — per-ticker 부분 실패 미감지

- **파일**: `core/cache/freshness.py` (manifest `collected_at`만 검사), `core/cache/ohlcv_disk.py` (`read()` 무검증)
- **왜곡**: 수집 중 일부 ticker만 실패하면 manifest는 fresh인데 해당 ticker parquet은 stale — 신선도 혼합 universe로 스캔. cross-sectional 랭킹(S2)에서 stale ticker가 상대 순위 왜곡.
- **수정**: parquet별 마지막 봉 날짜를 manifest target_date와 대조하는 per-ticker 검증을 스캔 진입 시 수행.

**기타 (LOW)**: ① S2 lookback 15→20일은 Jegadeesh-Titman(3~12개월)과 다른 단기 구간 — 한국 시장 단기 반전 성향상 edge 근거는 자체 WF뿐, t-test 미실시 (needs confirmation). long-only 확인(공매도 없음 — 한국 개인계좌 제약과 정합). ② S5 파라미터는 2026-05-14 단일 90일 그리드 과적합 → 2026-05-19 9-window WF로 이미 롤백된 이력 — 자기 교정 작동 중이나 stability score 상시화 권장. 패턴 객관성 점수 **65/100** (규칙 자체는 정량적·객관적, 파라미터 출처가 감점 요인; 에이전트 제안 45점은 기각된 미완성-bar 주장 포함이라 상향 조정). ③ WF lookback buffer 60일 > 전략 최대 lookback(30봉) — 안전 확인.

---

## 3. Backtest Engine 감사

- **체결 관행 (이원화)**:
  - `BacktestEngine`(S1 전용): 시그널 봉 close 진입 (F1, same-bar). 청산은 GAP_DOWN(open)→STOP(min(stop, open))→TARGET(target가)→TIME(close) 우선순위 — STOP에 `min(stop_loss, open)` 적용은 보수적으로 올바름.
  - `scan_adapter`(S2~S5 WF): T+1 open 진입 — 올바름. `_build_ctx`가 `df.index <= target_date` 슬라이스로 look-ahead 차단 (기존 테스트 `test_scorer_look_ahead_slice` 커버).
  - `_track_position` 우선순위: GAP_DOWN(open≤stop, open 체결=슬리피지 반영) → STOP 우선 tie-break → TARGET → TIME. 보수적 설계 적절 (기존 테스트 커버).
- **회계**: 단일 cash 풀, 진입 시 net_cost 차감·청산 시 net_proceeds 가산, equity = cash + Σ(close×shares). 내부 일관성 문제 없음. 단 같은 종목 중복 보유는 엔진 수준 차단(`ticker in positions`)이나 **전략 간 동일 종목 중복은 앙상블 차원에서 추적 없음** (S1과 S4가 같은 종목 시그널 시 노출 2배 — UI는 표시하나 리스크 합산 없음).
- **Sharpe 연환산**: trade-level `mean/std × sqrt(252/avg_bars)` — overlapping trade·포트폴리오 효과 무시. 절대값 해석 불가, 동일 scorer 내 상대 비교용으로만 유효.
- **walk_forward.py**: train/test 경계 깨끗 (test_start = train_end+1). lookback buffer 60일은 전략 lookback(최대 30봉) 대비 충분.
- **음성 대조 테스트 부재**: random/flat/단조 데이터에서 거짓 edge 검출 테스트 없음 → 본 감사에서 2건 추가 (§8).

## 4. 데이터·캐시 감사

- **수정주가**: `core/data_sources/naver.py` 주석은 "siseJson (수정주가)" 명시하나 검증 로직·테스트 없음. 네이버 siseJson 일봉이 분할 조정을 제공하는 것은 통설이나 배당 조정 여부 불명 — **needs confirmation** (오프라인 검증 불가, §10 제안 테스트).
- **타임존**: KST 고정 일관. 공휴일 캘린더 이원화는 F9.
- **수집 실패 vs 무시그널**: manifest collected_at + freshness 체크 + signal_status STALE 마킹으로 구분 가능 (2026-05-08 세션에서 보강됨).
- **리샘플링**: 1m→30m/1h은 pandas resample — 장 시작 09:00 경계 정렬은 기존 테스트(test_ohlcv_cache_disk 등) 커버 범위.
- **Universe**: 시총·유동성 필터 + ETN 제외 + 저변동 ETF 필터(7e1a4c8) 존재. 과거 universe 재구성 부재는 F2.

## 5. 전략별 감사

| 전략 | Lookahead | Same-bar fill | 핵심 리스크 | 비고 |
|---|---|---|---|---|
| S1 평균회귀 | 없음 (StrategyD 재사용, 지표 과거 기준) | **엔진 백테스트만 해당 (F1)** | 하락장 칼날잡기 — entry_gate regime 차단으로 부분 방어 | 쌍바닥/장악형 정의는 detectors.py에 정량 규칙 |
| S2 모멘텀 | 없음 (`close[-1] vs close[-1-lookback]`, 가드 적용) | WF는 T+1 open | 15~20일 lookback 학술 근거 약함 (LOW), long-only 확인 | over-extension 가드(rsi_max 80) registry 활성 |
| S3 추세추종 | **없음 — `high.iloc[-(lookback+1):-1]` 당일 제외 직접 검증** | WF는 T+1 open | 상한가/VI 체결 (F6) | +30% 제외·+20% 페널티 가드 존재 |
| S4 눌림목 | 없음 (MA 과거 봉 기준 + incomplete bar 가드) | WF는 T+1 open | S1과 반등 노출 부분 중복 — 앙상블 중복 추적 없음 | 반복 진입 제한은 freshness·gate 의존 |
| S5 Bull Flag | 없음 (pole/flag 과거 봉, 돌파만 당일 close) | WF는 T+1 open | 파라미터 출처 (LOW — 롤백 이력 있음), 상한가 (F6) | 객관성 65/100 |

- **incomplete bar 가드 매트릭스**: S2~S7 1D 경로는 `resolve_close_index` 적용 확인. S1 은 2026-09-19 에 `scan()` 에 가드를 배선해 해결 (단일 클래스라 `_d_v2`/`_w_v2`/`_1h_v2` 및 r1/r2 변형 9개 등록 이름 전체에 적용). 같은 날 주봉 경로 결함이 새로 드러나 함께 해결 — `W-FRI` 라벨이 월~목에 미래 날짜라 `is_today_bar_complete` 가 진행 중인 주봉을 확정으로 오판했다 (`core/cache/incomplete_bar.py` 에 미래 라벨 분기 추가). 1h cron 경로 검증은 여전히 미완.
- **scan vs backtest 이중 구현**: S1은 `strategies/strategy_one_d_v2.py:31`이 `backtest_engine.StrategyD`를 import해 재사용 — divergence 없음. S2~S5는 backtest_engine에 별도 구현이 없고 WF가 `strategy.scan()` 자체를 호출 — 정의상 divergence 불가. **에이전트의 divergence CRITICAL 주장은 기각** (§11).

## 6. HMM Market Regime 감사

- F3/F8 참조. 요약: **fit은 전체 기간 1회 + predict_proba 소급** — 운영 current_score는 안전(시점 T의 smoothing=filtering), history/windows는 오염. label switching은 `argmax(state mean)` 매핑으로 의미론 고정. 입력 feature(등가중 수익률, 20일 rolling std, expanding percentile)에 미래 정보 없음 — `_expanding_percentile_score`는 명시적 no-lookahead 설계 (본 감사에서 회귀 테스트 추가).
- HMM 제거 대비 부가가치(단순 MA 필터 대비) 측정 이력 없음 — needs confirmation. holding 집계가 이미 SMA slope proxy를 쓰는 점을 고려하면 비교 실험 비용 낮음.
- score = HMM posterior 45% + market health(expanding percentile) 55% — 절반 이상은 leakage-free 성분.

## 7. Ensemble 가중치 감사

- **계보**: weights.yml priorities(5-factor) ← `--interview` / 수기; `strategy_weights_by_regime` ← 수기 휴리스틱 (c0d6a59, 2871fa3). 구형 `fng_modifier`는 runtime 미적용. **optimize_full.py / wf_validate_* / wf_strategy_compare.py 어디에도 regime 소비 없음 (grep 확인)** → regime 라벨 in-sample 순환 오염 없음.
- 5전략 알파 원천: S1(반등) vs S4(추세 내 반등)는 부분 중복, S2/S3/S5는 모두 상방 추세 노출 — BULL에서 동반 이익·급락 시 동반 손실 가능성. **전략 간 일별 PnL 상관·동시 drawdown·공동 보유 측정 이력 없음** — needs confirmation (per-trade 기록은 `emit_per_trade`로 수집 가능, §10 권장 분석).
- 상위 5개 거래 제외 시 성과 변화 — 측정 이력 없음, needs confirmation.

## 8. Metrics·테스트 커버리지 평가

기존 1146+ 테스트는 시그널 로직·가드·API 조인에 강함. 백테스트 신뢰성 차원 갭:

| 항목 | 상태 | 비고 |
|---|---|---|
| look-ahead slice (scan_adapter) | ○ | `test_scorer_look_ahead_slice` |
| T+1 entry/exit 가격 | ○ | `test_scorer_entry_exit_prices` |
| commission 적용 | ○ | `test_scorer_commission_applied` |
| stop 우선 tie-break | ○ | `test_tie_break_stop_priority` |
| scorer 간 차이 (pnl vs bartracker) | ○ | `test_target_reached_yields_higher_pnl...` |
| incomplete bar 가드 | ○ | `test_incomplete_bar_guard` 외 4파일 |
| stale 시그널/캐시 (manifest 수준) | ○ | freshness/signal_status 테스트군 |
| **Donchian 당일 제외 회귀** | ✕→**본 감사 추가** | `tests/test_audit_donchian_no_lookahead.py` |
| **expanding percentile no-lookahead** | ✕→**본 감사 추가** | `tests/test_audit_expanding_percentile.py` |
| **음성 대조 (단조 상승/flat → 0 시그널)** | ✕→**본 감사 추가** | `backtest_engine/tests/test_audit_negative_controls.py` |
| same-bar vs next-bar 진입 gap | ✕ | 엔진 옵션 필요 — 제안 (§9 T-1) |
| HMM smoothing 라벨 변동 측정 | ✕ | 제안 (T-2) |
| survivor-bias universe | ✕ | 과거 스냅샷 인프라 필요 — 제안 (T-3) |
| 수정주가 분할 검증 | ✕ | 네트워크 필요 — 제안 (T-4, 수동) |
| MDD/CAGR/Sortino 공식 단위 검증 | ✕ | 제안 (T-5) |
| per-ticker 캐시 staleness | ✕ | 제안 (T-6) |
| 전략 간 PnL 상관·중복 보유 | ✕ | 제안 (T-7, 분석 스크립트) |

## 9. 추가/제안 테스트

**본 감사에서 추가 (3파일, 결정론·무네트워크)**:
1. `tests/test_audit_donchian_no_lookahead.py` — S3 채널이 당일 high를 포함하면 돌파가 정의상 불가능해지는 합성 케이스로 당일 제외 회귀 검증 + `metadata.channel_high == 과거 max` 확인.
2. `tests/test_audit_expanding_percentile.py` — `_expanding_percentile_score`에 미래 행 append 시 과거 출력 불변 검증.
3. `backtest_engine/tests/test_audit_negative_controls.py` — 단조 상승·무변동 flat 가격에서 StrategyD가 0 trade (쌍바닥 거짓 발화 없음) 검증.

**제안 (전제 조건 필요)**:
- T-1 `test_same_bar_vs_next_bar_entry_gap` — `next_bar_entry` 옵션 구현 후.
- T-2 `test_hmm_history_label_drift` — 미래 90일 append 시 초기 30일 score 변동률 > 0 임을 측정·로그 (현 구조 문서화).
- T-3 `test_universe_includes_delisted` — 과거 universe 스냅샷 도입 후.
- T-4 수정주가 수동 검증 — 액면분할 사례(예: 삼성전자 2018 50:1) 네이버 vs KRX 대조, 1회성 스크립트.
- T-5 `test_metrics_formulas` — BacktestResult의 MDD/CAGR/Sharpe를 손계산 fixture와 대조.
- T-6 `test_per_ticker_cache_staleness` — per-ticker 검증 구현 후.
- T-7 전략 간 일별 PnL 상관 분석 — `emit_per_trade` 기록을 5전략 × 동일 기간 수집해 상관행렬·동시 DD 산출 (테스트보다 분석 스크립트).

## 10. 미검증 항목 (needs confirmation)

| 항목 | 사유 |
|---|---|
| 네이버 siseJson 배당·증자 조정 여부 | 외부 네트워크 호출 금지 환경 — T-4로 수동 검증 필요 |
| S2 15~20일 모멘텀의 한국 시장 통계적 유의성 | 장기 히스토리 데이터셋 부재 (1년 WF만 존재) |
| 5전략 일별 PnL 상관·동시 drawdown | per-trade 기록 미축적 — T-7 |
| 상위 5개 거래 제외 시 성과 민감도 | 동일 (per-trade 기록 필요) |
| HMM vs 단순 MA 필터 부가가치 | 비교 실험 미실시 |
| paper trading 실측 0.30% 비용 가정의 출처 | 실측 로그 미문서화 |
| 2026-05-14 채택 12개 파라미터 중 stop 의존 항목의 bartracker 재검증 | F4 후속 — `.omc` 메모리상 2026-05-28 paper trading 비교 후 6개 롤백 예정이던 건과 함께 재확인 필요 |

## 11. 기각된 에이전트 주장 (false positives — 직접 검증으로 배제)

1. **"`df.iloc[:-1]` 후 rolling 계산이 지표를 왜곡" (전략 에이전트 CRITICAL#1·#2·#3)**: 기각. backward-looking rolling은 미래 행 절단에 불변 — `trim 후 rolling(...).iloc[-1] ≡ 원본 rolling(...).iloc[-2]` (동일 윈도우 [t-19..t]). 수학적 동치.
2. **"regime 라벨 → 가중치 → 같은 기간 백테스트 순환 오염 (이중 최적화)" (HMM 에이전트 CRITICAL#2)**: 기각. `optimize_full.py`/`optimize_market_separate.py`/`wf_validate_*`/`wf_strategy_compare.py`에 regime 소비 없음(grep 0건), holding 집계는 SMA proxy 사용, regime 매트릭스는 수기 작성(git 확인). 단 **향후 위험**으로 F3에 흡수.
3. **"비용 -50% 과소 (실제 0.615%)" (엔진 에이전트)**: 수치 기각. 인용 세율(거래세 0.21% + 농특세 0.105%)이 부정확 — 2026년 실제는 KOSPI 0.20%(0.05+0.15)/KOSDAQ 0.20% 매도 단일. 슬리피지 미모델 지적만 유효 → F5로 조정.
4. **"S1 scan vs backtest 쌍바닥 로직 divergence" (전략 에이전트 HIGH#7)**: 기각. `strategies/strategy_one_d_v2.py:31`이 `backtest_engine.StrategyD`를 직접 import — 단일 구현.
5. **"당일 미완성 close로 시그널 확정" (전략 에이전트 HIGH#4)**: 대부분 완화됨 — cron이 장 마감 후(16:10/16:40) 실행 + `resolve_close_index` 가드가 15:30 이전 수집 봉을 차단. 잔존 리스크는 F1(엔진 체결)로 흡수.

## 12. 실행 명령·결과

```
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q
# → 1171 passed, 7 skipped in 25.80s (신규 감사 테스트 6건 포함, 기존 회귀 무영향)

.venv/bin/ruff check . --exclude .venv
# → All checks passed!

# 신규 감사 테스트 단독 실행
.venv/bin/python -m pytest tests/test_audit_donchian_no_lookahead.py \
  tests/test_audit_expanding_percentile.py \
  backtest_engine/tests/test_audit_negative_controls.py -v
# → 6 passed in 2.89s

# F1 후속 (2026-06-12): S1 진입 타이밍 delta 측정
.venv/bin/python scripts/audit_f1_entry_timing.py --cache-root .cache_wf
# → trades 24/24 동일, return -1.290%→-1.312% (-0.022%p), sharpe -0.307→-0.411 (-0.103),
#   win_rate 45.83%→41.67% (-4.17%p), mdd -3.775%→-2.868% (+0.907%p)

# F5/F6 후속 (2026-06-12): 비용·갭상승 체결 민감도 표
.venv/bin/python scripts/audit_f5_f6_cost_sensitivity.py --cache-root .cache_wf
# → 표는 F5/F6 후속 조치 참조. S1/S3 slip0.3% 에도 양(+), S2 음전(-5.6%),
#   S4/S5 현행 비용에서도 음수. 갭>+3% skip 은 S2/S3/S4 일관 개선 (S4 양전)

# F6 갭 필터 WF 검증 (2026-06-12)
.venv/bin/python scripts/wf_validate_gap_filter.py --cache-root .cache_wf
# → threshold CPO 전 전략 FAIL (unstable). 고정 +3% 는 S2 7/9·S4 6/9 윈도우 OOS 개선,
#   "무제한" 이 train best 인 윈도우 0/45 — 상세는 F6 후속 조치 참조
```

검증 근거 수집에 사용한 주요 명령: `grep "make_scan_pnl_scorer|make_scan_bartracker_scorer" scripts/` (WF scorer 사용처), `grep -l regime scripts/optimize_*.py scripts/wf_*.py` (0건 — regime 순환 오염 기각 근거), `git log -- weights.yml` (가중치 수기 작성 확인), WebSearch (2026 증권거래세·농특세율).

## 13. 라이브 트레이딩 전 최소 조건

1. **F1**: `next_bar_entry` 구현 → S1 백테스트 재실행, same-bar 대비 delta를 수치로 공표. delta가 전략 edge보다 크면 S1 재평가. — ✅ 완료 (2026-06-12, F1 후속 조치 참조). delta 미미(수익률 -0.022%p)로 진입 타이밍은 S1 재평가 사유 아님. 단 측정 구간에서 S1 기본 config 자체가 음수 수익(-1.29%)인 점은 별도 모니터링 필요.
2. **F4**: stop/target 의존 파라미터의 WF 결과를 bartracker로 전수 재검증. scorer 선택 정책 문서화.
3. **F5/F6**: 슬리피지 0.1/0.2/0.3% 및 갭상승 체결 제한 시나리오에서 5전략 성과가 양(+)으로 유지되는지 민감도 표 작성. — ✅ 완료 (2026-06-12, F5/F6 후속 조치 참조). 양(+) 유지: S1·S3. S2 는 slip 0.3% 에서 음전 (고회전 비용 민감). S4·S5 는 현행 비용에서도 음수 — §13-1 의 S1 모니터링과 함께 전략 라인업 재평가 입력. 갭 제한은 성과를 해치지 않음 (편향 방향 보수 — F6 후속 참조).
4. **F2**: 신규 WF부터 universe 스냅샷 적용. 기존 수치 인용 시 생존 편향 주석 의무화.
5. **F3**: HMM history 소비 금지 정책 코드화 (docstring + 리뷰 체크리스트).
6. **T-7**: 전략 간 일별 PnL 상관 측정 — 상관 > 0.7 쌍이 있으면 "분산"이 아니라 동일 베팅 중복으로 간주하고 포지션 한도 통합.
7. paper trading 실측 슬리피지·체결률 로그 축적 → 0.30% 가정 검증 또는 교체.

## 14. 후속 수동 리뷰 대상

- `backtest_engine/detectors.py` — 쌍바닥/장악형 정량 규칙의 경계 케이스 (이번 감사는 구조 수준)
- `core/decision/regret_scorer.py` — `reward_pct_t2` 명칭이 미래값을 암시하나 실제는 trade_plan target 기반으로 추정, 명칭 정리 겸 확인
- `scripts/optimize_full.py` — train/val/OOS 날짜 경계 명시성
- `signal-web` stale 경고 UI — 코드 수준 미감사 (API 계약만 확인)
