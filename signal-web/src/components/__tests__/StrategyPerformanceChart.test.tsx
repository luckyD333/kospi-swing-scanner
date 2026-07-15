import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StrategyPerformanceChart from '@/components/StrategyPerformanceChart';
import type {
  PerformanceStats,
  StrategyPerformanceResponse,
} from '@/types/performance';

const stats: PerformanceStats = {
  signal_count: 1,
  evaluated_count: 1,
  win_count: 1,
  loss_count: 0,
  flat_count: 0,
  win_rate_pct: 100,
  gross_sum_pct: 1.55,
  net_sum_pct: 1.25,
  avg_gross_return_pct: 1.55,
  avg_net_return_pct: 1.25,
  daily_return_pct: 1.25,
  cumulative_return_pct: 1.25,
  profit_factor: null,
};

function partialResponse(daily = true): StrategyPerformanceResponse {
  return {
    schema_version: '1.1',
    status: 'partial',
    updated_at: '2026-07-13T16:45:00+09:00',
    window: {
      from: daily ? '2026-07-02' : null,
      to: daily ? '2026-07-02' : null,
    },
    evaluation: {
      timeframe: '1D',
      basis: 'signal_close_to_next_close',
      horizon_bars: 1,
      cost_pct: 0.3,
    },
    strategies: {
      strategy_one_original: {
        label: 'Strategy One · Original',
        source_ids: ['strategy_one_d_v2_r1'],
      },
    },
    daily: daily ? [{
      evaluation_date: '2026-07-02',
      by_strategy: { strategy_one_original: stats },
    }] : [],
    totals: daily ? { strategy_one_original: stats } : {},
    archive_summary: {
      discovered_files: 2,
      loaded_files: 1,
      failed_files_count: 1,
      failed_files: ['signals_2026-07-01.json'],
    },
  };
}

describe('StrategyPerformanceChart', () => {
  it('partial 데이터의 경고와 전체 일별 성과 표를 함께 렌더링한다', () => {
    const html = renderToStaticMarkup(
      createElement(StrategyPerformanceChart, {
        data: partialResponse(),
        loading: false,
        error: null,
      }),
    );

    expect(html).toContain('role="status"');
    expect(html).toContain('1개 archive 파일');
    expect(html).toContain('signals_2026-07-01.json');
    expect(html).toContain('<table');
    expect(html).toContain('2026.07.02');
    expect(html).toContain('+1.25%');
  });

  it('평가 행이 없는 partial 데이터도 경고와 빈 상태를 렌더링한다', () => {
    const html = renderToStaticMarkup(
      createElement(StrategyPerformanceChart, {
        data: partialResponse(false),
        loading: false,
        error: null,
      }),
    );

    expect(html).toContain('role="status"');
    expect(html).toContain('아직 집계된 성과가 없습니다');
  });

  it('archive_summary가 없는 schema 1.0 ready artifact도 표시한다', () => {
    const data = partialResponse();
    data.schema_version = '1.0';
    data.status = 'ready';
    delete data.archive_summary;

    const html = renderToStaticMarkup(
      createElement(StrategyPerformanceChart, {
        data,
        loading: false,
        error: null,
      }),
    );

    expect(html).not.toContain('role="status"');
    expect(html).toContain('일별 누적수익률 표');
  });
});
