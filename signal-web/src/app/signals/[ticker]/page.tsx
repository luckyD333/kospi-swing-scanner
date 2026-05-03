import { notFound } from 'next/navigation';
import { fetchSignal, fetchSignals } from '@/lib/api';
import { adaptSignal } from '@/lib/adapt';
import DetailClient from '@/components/DetailClient';

export default async function Page({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;

  const [signal, context] = await Promise.all([
    fetchSignal(ticker).catch(() => null),
    fetchSignals(),
  ]);

  if (!signal) notFound();

  const card = adaptSignal(signal, context.generated_at_display);

  return (
    <DetailClient
      card={card}
      marketIndices={context.market_indices}
      marketRegime={context.market_regime}
    />
  );
}
