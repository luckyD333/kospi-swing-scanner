import { fetchSignals } from '@/lib/api';
import { adaptSignal } from '@/lib/adapt';
import CatalogClient from '@/components/CatalogClient';

export default async function Page() {
  const data = await fetchSignals();
  const cards = data.signals.map(s => adaptSignal(s, data.generated_at_display));
  // 'all' 통합 entry 의 strategyLabel ('ALL') 은 prepend 와 중복되므로 제외.
  const strategyLabels = Array.from(
    new Set(cards.filter(c => c.strategyId !== 'all').map(c => c.strategyLabel)),
  ).sort();
  const strategies = ['ALL', ...strategyLabels];
  const timeframes = data.filters.timeframes;

  return (
    <CatalogClient
      cards={cards}
      strategies={strategies}
      timeframes={timeframes}
      marketIndices={data.market_indices}
      generatedAtDisplay={data.generated_at_display}
      targetDateDisplay={data.target_date_display}
      marketRegime={data.market_regime}
      marketBreadth={data.market_breadth}
      marketAxes={data.market_axes}
      fearGreed={data.fear_greed ?? null}
    />
  );
}
