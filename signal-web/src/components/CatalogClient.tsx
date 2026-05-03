'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import type { MarketIndex } from '@/types/signal';
import type { CardProps } from '@/lib/adapt';
import TopNav from './TopNav';
import FilterBar from './FilterBar';
import TickerCard from './TickerCard';
import DisclaimerBar from './DisclaimerBar';

interface Props {
  cards: CardProps[];
  strategies: string[];
  timeframes: string[];
  marketIndices: Record<string, MarketIndex>;
  generatedAtDisplay: string;
}

export default function CatalogClient({ cards, strategies, timeframes, marketIndices, generatedAtDisplay }: Props) {
  const router = useRouter();
  const [strategy, setStrategy] = useState('ALL');
  const [timeframe, setTimeframe] = useState('ALL');
  const [sortBy, setSortBy] = useState('score');

  const filtered = cards
    .filter(c => strategy === 'ALL' || c.strategyLabel === strategy)
    .filter(c => timeframe === 'ALL' || c.timeframe === timeframe)
    .sort((a, b) => {
      if (sortBy === 'score') return (b.score ?? -Infinity) - (a.score ?? -Infinity);
      if (sortBy === 'rr') return (b.rrRatio ?? -Infinity) - (a.rrRatio ?? -Infinity);
      if (sortBy === 'entry') return b.entry - a.entry;
      return 0;
    });

  return (
    <div style={{ background: 'var(--canvas)', minHeight: '100vh' }}>
      <TopNav
        marketIndices={marketIndices}
        generatedAtDisplay={generatedAtDisplay}
        onHome={() => router.push('/')}
      />

      <FilterBar
        strategies={strategies}
        timeframes={timeframes}
        activeStrategy={strategy}
        activeTimeframe={timeframe}
        sortBy={sortBy}
        onStrategy={setStrategy}
        onTimeframe={setTimeframe}
        onSort={setSortBy}
      />

      {/* 카드 그리드 */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(max(260px, 19%), 1fr))',
        gap: '0',
        background: 'var(--canvas)',
        borderTop: '1px solid var(--hairline)',
        borderLeft: '1px solid var(--hairline)',
      }}>
        {filtered.map((card, i) => (
          <div key={`${card.ticker}-${card.strategyLabel}`} style={{
            background: 'var(--canvas)',
            borderRight: '1px solid var(--hairline)',
            borderBottom: '1px solid var(--hairline)',
          }}>
            <TickerCard
              card={card}
              onClick={() => router.push(`/signal/${card.ticker}`)}
              index={i}
            />
          </div>
        ))}
      </div>

      <div style={{ height: '30px' }} />
      <DisclaimerBar />
    </div>
  );
}
