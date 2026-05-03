import { fetchSignals } from '@/lib/api';
import { adaptSignal } from '@/lib/adapt';
import CatalogClient from '@/components/CatalogClient';

export default async function Page() {
  const data = await fetchSignals();
  const cards = data.signals.map(s => adaptSignal(s, data.generated_at_display));
  const strategyLabels = Array.from(new Set(cards.map(c => c.strategyLabel))).sort();
  const strategies = ['ALL', ...strategyLabels];
  const timeframes = data.filters.timeframes;

  return (
    <CatalogClient
      cards={cards}
      strategies={strategies}
      timeframes={timeframes}
      marketIndices={data.market_indices}
      generatedAtDisplay={data.generated_at_display}
    />
  );
}
