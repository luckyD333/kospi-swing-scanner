export interface PerformanceStats {
  signal_count: number;
  evaluated_count: number;
  win_count: number;
  loss_count: number;
  flat_count: number;
  win_rate_pct: number;
  gross_sum_pct: number;
  net_sum_pct: number;
  avg_gross_return_pct: number;
  avg_net_return_pct: number;
  daily_return_pct: number;
  cumulative_return_pct: number;
  profit_factor: number | null;
}

export interface PerformanceStrategyDefinition {
  label: string;
  source_ids: string[];
}

export interface PerformanceDailyRow {
  evaluation_date: string;
  by_strategy: Record<string, PerformanceStats>;
}

export interface StrategyPerformanceResponse {
  schema_version: string;
  status: 'ready' | 'partial' | 'not_ready';
  updated_at: string | null;
  window: { from: string | null; to: string | null };
  evaluation: {
    timeframe: string;
    basis: string;
    horizon_bars: number;
    cost_pct: number;
  };
  strategies: Record<string, PerformanceStrategyDefinition>;
  daily: PerformanceDailyRow[];
  totals: Record<string, PerformanceStats>;
  archive_summary?: {
    discovered_files: number;
    loaded_files: number;
    failed_files_count: number;
    failed_files: string[];
  };
}
