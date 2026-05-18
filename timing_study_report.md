# 전략별 매수/매도 타이밍 최적화 백테스트 결과

- 진입 시간대: ['morning', 'afternoon']
- 보유 기간: [0, 1, 2, 3]일
- 수수료: 0.25%

## 최적 조합 Top 10 (avg_return 기준)

| strategy | entry_window | hold_days | rank_bucket | avg_return | win_rate | profit_factor | sample_n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| strategy_five | morning | 3 | 1 | 12.56 | 0.71 | 6.74 | 900 |
| strategy_five | morning | 2 | 1 | 11.55 | 0.74 | 7.75 | 906 |
| strategy_three | morning | 3 | 1 | 11.38 | 0.72 | 7.29 | 822 |
| strategy_three | morning | 2 | 1 | 10.67 | 0.75 | 8.71 | 835 |
| strategy_five | morning | 1 | 1 | 10.55 | 0.81 | 12.14 | 915 |
| strategy_three | morning | 1 | 1 | 9.99 | 0.79 | 11.85 | 847 |
| strategy_five | morning | 0 | 1 | 9.01 | 0.98 | 5631.56 | 922 |
| strategy_three | morning | 0 | 1 | 8.15 | 0.85 | 19.68 | 855 |
| strategy_five | morning | 3 | 2 | 7.13 | 0.70 | 5.27 | 897 |
| strategy_three | morning | 2 | 2 | 7.12 | 0.76 | 8.74 | 255 |

## 전략별 매트릭스 (avg_return %)

### strategy_five
| entry_window | rank_bucket | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- | --- |
| afternoon | 1 | 1.40 | 2.71 | 3.58 | 4.48 |
| afternoon | 2 | 0.75 | 1.96 | 2.37 | 2.69 |
| afternoon | 3 | 0.47 | 1.55 | 2.34 | 2.57 |
| afternoon | 4 | 0.37 | 1.19 | 1.98 | 2.87 |
| morning | 1 | 9.01 | 10.55 | 11.55 | 12.56 |
| morning | 2 | 5.15 | 6.42 | 6.81 | 7.13 |
| morning | 3 | 3.55 | 4.65 | 5.45 | 5.67 |
| morning | 4 | 2.98 | 3.80 | 4.62 | 5.51 |

### strategy_four
| entry_window | rank_bucket | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- | --- |
| afternoon | 1 | 0.30 | 0.54 | 1.25 | 1.99 |
| afternoon | 3 | -0.05 | 0.06 | -0.23 | 0.89 |
| afternoon | 4 | -0.23 | -0.01 | 0.14 | 0.70 |
| morning | 1 | 2.74 | 3.00 | 3.72 | 4.46 |
| morning | 3 | 0.80 | 0.90 | 0.60 | 1.73 |
| morning | 4 | -0.12 | 0.09 | 0.24 | 0.80 |

### strategy_one
| entry_window | rank_bucket | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- | --- |
| afternoon | 1 | 0.86 | 2.02 | 2.28 | 0.80 |
| morning | 1 | 5.60 | 6.81 | 7.09 | 5.54 |

### strategy_three
| entry_window | rank_bucket | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- | --- |
| afternoon | 1 | 1.23 | 2.82 | 3.40 | 4.00 |
| afternoon | 2 | 0.69 | 1.56 | 2.88 | 2.85 |
| afternoon | 3 | 0.50 | 1.42 | 1.81 | 2.19 |
| afternoon | 4 | 0.32 | 1.21 | 1.87 | 2.48 |
| morning | 1 | 8.15 | 9.99 | 10.67 | 11.38 |
| morning | 2 | 4.88 | 5.79 | 7.12 | 7.11 |
| morning | 3 | 3.81 | 4.78 | 5.14 | 5.54 |
| morning | 4 | 2.79 | 3.74 | 4.48 | 5.16 |

### strategy_two
| entry_window | rank_bucket | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- | --- |
| afternoon | 1 | -0.00 | 1.10 | 2.14 | 3.26 |
| afternoon | 2 | -0.17 | 0.73 | 1.55 | 2.55 |
| afternoon | 3 | -0.21 | 0.33 | 0.87 | 1.36 |
| afternoon | 4 | -0.22 | -0.01 | 0.29 | 0.65 |
| morning | 1 | 1.55 | 2.74 | 3.85 | 5.01 |
| morning | 2 | 0.44 | 1.40 | 2.23 | 3.20 |
| morning | 3 | 0.16 | 0.71 | 1.25 | 1.70 |
| morning | 4 | 0.05 | 0.27 | 0.56 | 0.91 |

## 추천 (rank_bucket=1 기준)

신뢰도 상위 25% 신호(Q1) 기준 최적 조합:

- **strategy_five**: morning 진입, 3일 보유 → avg 12.56%, 승률 71% (n=900)
- **strategy_five**: morning 진입, 2일 보유 → avg 11.55%, 승률 74% (n=906)
- **strategy_three**: morning 진입, 3일 보유 → avg 11.38%, 승률 72% (n=822)
- **strategy_three**: morning 진입, 2일 보유 → avg 10.67%, 승률 75% (n=835)
- **strategy_five**: morning 진입, 1일 보유 → avg 10.55%, 승률 81% (n=915)