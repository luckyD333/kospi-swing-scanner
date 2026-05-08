import { notFound } from 'next/navigation';
import { fetchSignal, fetchSignals } from '@/lib/api';
import { adaptDetailSignal } from '@/lib/adapt';
import DetailClient from '@/components/DetailClient';

export default async function Page({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;

  const [signal, context] = await Promise.all([
    fetchSignal(ticker).catch(() => null),
    fetchSignals(),
  ]);

  if (!signal) notFound();

  const detail = adaptDetailSignal(signal);

  return (
    <DetailClient
      detail={detail}
      marketIndices={context.market_indices}
      targetDateDisplay={context.target_date_display}
      marketRegime={context.market_regime}
      marketBreadth={context.market_breadth}
      marketAxes={context.market_axes}
      fearGreed={context.fear_greed ?? null}
    />
  );
}
