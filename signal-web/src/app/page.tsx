import { fetchSignals } from '@/lib/api';
import { adaptSignal } from '@/lib/adapt';
import CatalogClient from '@/components/CatalogClient';

export default async function Page() {
  const data = await fetchSignals();
  const cards = data.signals.map(s => adaptSignal(s, data.generated_at_display));

  return (
    <CatalogClient
      cards={cards}
      marketIndices={data.market_indices}
      generatedAtDisplay={data.generated_at_display}
      targetDateDisplay={data.target_date_display}
      marketRegime={data.market_regime}
      marketBreadth={data.market_breadth}
      marketAxes={data.market_axes}
      fearGreed={data.fear_greed ?? null}
      scanFreshnessWarning={data.scan_freshness_warning}
      generatedAt={data.generated_at}
    />
  );
}
