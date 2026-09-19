'use client';

import { useMemo, useState } from 'react';
import type {
  PerformanceDailyRow,
  PerformanceStats,
  StrategyPerformanceResponse,
} from '@/types/performance';
import { ts } from '@/lib/typography';

interface Props {
  data: StrategyPerformanceResponse | null;
  loading: boolean;
  error: string | null;
}

const STRATEGY_ORDER = [
  'strategy_one_original',
  'strategy_one_improved',
  'strategy_two',
  'strategy_three',
  'strategy_four',
  'strategy_five',
  'strategy_six',
  'strategy_seven',
] as const;

const STRATEGY_COLORS: Record<string, string> = {
  strategy_one_original: 'var(--accent)',
  strategy_one_improved: 'var(--gain)',
  strategy_two: '#c084fc',
  strategy_three: '#fb923c',
  strategy_four: '#38bdf8',
  strategy_five: '#facc15',
  strategy_six: '#34d399',
  strategy_seven: '#f59e0b',
};

const FALLBACK_LABELS: Record<string, string> = {
  strategy_one_original: 'Strategy One · Original',
  strategy_one_improved: 'Strategy One · Improved',
  strategy_two: 'Strategy Two',
  strategy_three: 'Strategy Three',
  strategy_four: 'Strategy Four',
  strategy_five: 'Strategy Five',
  strategy_six: 'Strategy Six',
  strategy_seven: 'Strategy Seven',
};

function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return value.replaceAll('-', '.');
}

function EmptyState({ children }: { children: string }) {
  return (
    <div style={{
      border: '1px solid var(--hairline)',
      padding: '36px 24px',
      color: 'var(--muted)',
      textAlign: 'center',
      ...ts('body-md'),
    }}>
      {children}
    </div>
  );
}

function PartialWarning({ data }: { data: StrategyPerformanceResponse }) {
  if (data.status !== 'partial') return null;
  const summary = data.archive_summary;
  const failedCount = summary?.failed_files_count ?? 0;
  const failedFiles = summary?.failed_files ?? [];
  return (
    <aside
      role="status"
      style={{
        border: '1px solid var(--hairline)',
        borderLeft: '3px solid var(--warning)',
        padding: '14px 16px',
        marginBottom: '14px',
        color: 'var(--body-strong)',
        ...ts('body-md'),
      }}
    >
      <strong>성과가 일부만 집계되었습니다.</strong>{' '}
      {failedCount > 0
        ? `${failedCount}개 archive 파일을 읽지 못했습니다.`
        : '일부 archive 파일을 읽지 못했습니다.'}
      {failedFiles.length > 0 && (
        <details style={{ marginTop: '8px' }}>
          <summary style={{ cursor: 'pointer' }}>실패 파일 보기</summary>
          <ul style={{ margin: '8px 0 0', paddingLeft: '20px' }}>
            {failedFiles.map(filename => <li key={filename}>{filename}</li>)}
          </ul>
        </details>
      )}
    </aside>
  );
}

function MetricCard({
  strategyKey,
  label,
  stats,
}: {
  strategyKey: string;
  label: string;
  stats: PerformanceStats;
}) {
  const color = STRATEGY_COLORS[strategyKey] ?? 'var(--accent)';
  return (
    <div style={{
      minWidth: 0,
      padding: '22px 20px 20px',
      background: 'var(--canvas)',
      borderTop: `2px solid ${color}`,
      borderRight: '1px solid var(--hairline)',
      borderBottom: '1px solid var(--hairline)',
    }}>
      <div style={{ ...ts('caption-sm', 'var(--muted)'), marginBottom: '12px' }}>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px', marginBottom: '14px' }}>
        <strong style={{ ...ts('display-sm', color), fontWeight: 500 }}>
          {formatPct(stats.cumulative_return_pct)}
        </strong>
        <span style={ts('caption-sm', 'var(--muted)')}>누적</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px' }}>
        <div>
          <div style={ts('caption-sm', 'var(--muted-soft)')}>승률</div>
          <div style={ts('caption', 'var(--body-strong)')}>{stats.win_rate_pct.toFixed(1)}%</div>
        </div>
        <div>
          <div style={ts('caption-sm', 'var(--muted-soft)')}>평균 손익</div>
          <div style={ts('caption', stats.avg_net_return_pct >= 0 ? 'var(--gain)' : 'var(--loss)')}>
            {formatPct(stats.avg_net_return_pct)}
          </div>
        </div>
        <div>
          <div style={ts('caption-sm', 'var(--muted-soft)')}>평가 건수</div>
          <div style={ts('caption', 'var(--body-strong)')}>{stats.evaluated_count}</div>
        </div>
        <div>
          <div style={ts('caption-sm', 'var(--muted-soft)')}>승 / 패</div>
          <div style={ts('caption', 'var(--body-strong)')}>{stats.win_count} / {stats.loss_count}</div>
        </div>
      </div>
    </div>
  );
}

export default function StrategyPerformanceChart({ data, loading, error }: Props) {
  const [activeKeys, setActiveKeys] = useState<Set<string>>(
    new Set(STRATEGY_ORDER),
  );
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const keys = useMemo(() => {
    if (!data) return [...STRATEGY_ORDER];
    return STRATEGY_ORDER.filter(key => data.strategies[key] || data.totals[key]);
  }, [data]);

  if (loading) return <EmptyState>최근 6개월 성과를 불러오는 중입니다.</EmptyState>;
  if (error) return <EmptyState>성과 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.</EmptyState>;
  if (!data || data.status === 'not_ready') {
    return <EmptyState>아직 집계된 성과가 없습니다. 장 마감 후 첫 집계를 실행해주세요.</EmptyState>;
  }
  if (data.daily.length === 0) {
    return (
      <div>
        <PartialWarning data={data} />
        <EmptyState>아직 집계된 성과가 없습니다. 장 마감 후 첫 집계를 실행해주세요.</EmptyState>
      </div>
    );
  }

  const rows: PerformanceDailyRow[] = data.daily;
  const visibleKeys = keys.filter(key => activeKeys.has(key));
  const width = 820;
  const height = 300;
  const padding = { top: 24, right: 18, bottom: 34, left: 52 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const values = visibleKeys.flatMap(key => rows.map(row => (
    row.by_strategy[key]?.cumulative_return_pct ?? 0
  )));
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(0, ...values);
  const range = Math.max(maxValue - minValue, 1);
  const yMin = minValue - range * 0.08;
  const yMax = maxValue + range * 0.08;
  const xFor = (index: number) => padding.left + (
    rows.length === 1 ? chartWidth / 2 : (index / (rows.length - 1)) * chartWidth
  );
  const yFor = (value: number) => padding.top + ((yMax - value) / (yMax - yMin)) * chartHeight;
  const zeroY = yFor(0);
  const hoverRow = hoverIndex == null ? null : rows[hoverIndex];

  const toggle = (key: string) => {
    setActiveKeys(previous => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div>
      <PartialWarning data={data} />
      <div style={{
        border: '1px solid var(--hairline)',
        background: 'rgba(255,255,255,0.015)',
        padding: '18px 18px 12px',
        overflowX: 'auto',
      }}>
        <div style={{ position: 'relative', minWidth: '680px' }}>
          <svg
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label="전략별 최근 6개월 누적수익률 차트"
            style={{ display: 'block', width: '100%', height: 'auto' }}
          >
            <line x1={padding.left} x2={width - padding.right} y1={zeroY} y2={zeroY} stroke="var(--hairline)" strokeDasharray="4 5" />
            <text x={padding.left - 10} y={zeroY + 4} textAnchor="end" fill="var(--muted-soft)" fontSize="10">0%</text>
            <text x={padding.left - 10} y={yFor(maxValue) + 4} textAnchor="end" fill="var(--muted-soft)" fontSize="10">{formatPct(maxValue)}</text>
            <text x={padding.left - 10} y={yFor(minValue) + 4} textAnchor="end" fill="var(--muted-soft)" fontSize="10">{formatPct(minValue)}</text>
            {visibleKeys.map(key => {
              const points = rows.map((row, index) => (
                `${xFor(index)},${yFor(row.by_strategy[key]?.cumulative_return_pct ?? 0)}`
              )).join(' ');
              return (
                <polyline
                  key={key}
                  points={points}
                  fill="none"
                  stroke={STRATEGY_COLORS[key]}
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              );
            })}
            {rows.map((row, index) => (
              <g key={row.evaluation_date} onMouseEnter={() => setHoverIndex(index)}>
                <line
                  x1={xFor(index)} x2={xFor(index)}
                  y1={padding.top} y2={height - padding.bottom}
                  stroke={hoverIndex === index ? 'var(--hairline)' : 'transparent'}
                />
                {visibleKeys.map(key => (
                  <circle
                    key={key}
                    cx={xFor(index)}
                    cy={yFor(row.by_strategy[key]?.cumulative_return_pct ?? 0)}
                    r={hoverIndex === index ? 4 : 2}
                    fill={STRATEGY_COLORS[key]}
                  />
                ))}
              </g>
            ))}
            <text x={padding.left} y={height - 8} fill="var(--muted-soft)" fontSize="10">{formatDate(rows[0].evaluation_date)}</text>
            <text x={width - padding.right} y={height - 8} textAnchor="end" fill="var(--muted-soft)" fontSize="10">{formatDate(rows[rows.length - 1].evaluation_date)}</text>
          </svg>
          {hoverRow && (
            <div style={{
              position: 'absolute',
              top: 8,
              right: 12,
              background: 'rgba(0,0,0,0.9)',
              border: '1px solid var(--hairline)',
              padding: '8px 10px',
              pointerEvents: 'none',
            }}>
              <div style={ts('caption-sm', 'var(--muted)')}>{formatDate(hoverRow.evaluation_date)}</div>
              {visibleKeys.map(key => (
                <div key={key} style={{ display: 'flex', gap: '10px', justifyContent: 'space-between', marginTop: '3px' }}>
                  <span style={ts('caption-sm', STRATEGY_COLORS[key])}>{data.strategies[key]?.label ?? FALLBACK_LABELS[key]}</span>
                  <span style={ts('caption-sm', 'var(--body-strong)')}>
                    {formatPct(hoverRow.by_strategy[key]?.cumulative_return_pct)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', margin: '14px 0 18px' }}>
        {keys.map(key => {
          const active = activeKeys.has(key);
          return (
            <button
              key={key}
              type="button"
              aria-pressed={active}
              onClick={() => toggle(key)}
              style={{
                ...ts('caption-sm', active ? STRATEGY_COLORS[key] : 'var(--muted-soft)'),
                border: `1px solid ${active ? STRATEGY_COLORS[key] : 'var(--hairline)'}`,
                background: 'transparent',
                borderRadius: 'var(--radius-pill)',
                padding: '5px 9px',
                cursor: 'pointer',
                opacity: active ? 1 : 0.65,
              }}
            >
              {data.strategies[key]?.label ?? FALLBACK_LABELS[key]}
            </button>
          );
        })}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', background: 'var(--hairline)', gap: '1px' }}>
        {keys.map(key => (
          <MetricCard
            key={key}
            strategyKey={key}
            label={data.strategies[key]?.label ?? FALLBACK_LABELS[key]}
            stats={data.totals[key]}
          />
        ))}
      </div>

      <details style={{ marginTop: '16px' }}>
        <summary style={{ ...ts('caption', 'var(--body-strong)'), cursor: 'pointer' }}>
          일별 누적수익률 표
        </summary>
        <div style={{ overflowX: 'auto', marginTop: '10px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', ...ts('caption-sm') }}>
            <caption style={{ textAlign: 'left', color: 'var(--muted)', marginBottom: '8px' }}>
              날짜별 전략 누적수익률
            </caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left', padding: '7px 8px', borderBottom: '1px solid var(--hairline)' }}>평가일</th>
                {keys.map(key => (
                  <th key={key} scope="col" style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid var(--hairline)' }}>
                    {data.strategies[key]?.label ?? FALLBACK_LABELS[key]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.evaluation_date}>
                  <th scope="row" style={{ textAlign: 'left', padding: '7px 8px', borderBottom: '1px solid var(--hairline)' }}>
                    {formatDate(row.evaluation_date)}
                  </th>
                  {keys.map(key => (
                    <td key={key} style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid var(--hairline)' }}>
                      {formatPct(row.by_strategy[key]?.cumulative_return_pct)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <p style={{ ...ts('caption-sm', 'var(--muted-soft)'), lineHeight: 1.6, margin: '16px 0 0' }}>
        최근 {formatDate(data.window.from)} ~ {formatDate(data.window.to)} · 1D signal 종가에서 다음 거래일 종가까지 · 비용 {data.evaluation.cost_pct.toFixed(2)}% 차감 · 실제 체결 PnL과는 별도입니다.
      </p>
    </div>
  );
}
