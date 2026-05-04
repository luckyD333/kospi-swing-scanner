'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import type { MarketIndex, RegimeScore, BreadthScore, AxesScore, FearGreedSnapshot } from '@/types/signal';
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
  targetDateDisplay?: string;
  marketRegime?: Record<string, RegimeScore> | null;
  marketBreadth?: Record<string, BreadthScore> | null;
  marketAxes?: Record<string, AxesScore> | null;
  fearGreed?: FearGreedSnapshot | null;
}

export default function CatalogClient({ cards, strategies, timeframes, marketIndices, generatedAtDisplay, targetDateDisplay, marketRegime, marketBreadth, marketAxes, fearGreed }: Props) {
  const router = useRouter();
  const [strategy, setStrategy] = useState('ALL');
  const [timeframe, setTimeframe] = useState('ALL');
  const [sortBy, setSortBy] = useState('rank');

  useEffect(() => {
    const id = setInterval(() => router.refresh(), 120_000);
    return () => clearInterval(id);
  }, []);

  // 'ALL' 탭은 서버 dedup 결과 (strategy.id === 'all') 만 노출.
  // 'all' entry 가 없는 환경 (legacy) 에서는 모든 카드 표시 fallback.
  const hasAllEntry = cards.some(c => c.strategyId === 'all');
  const filtered = cards
    .filter(c => {
      if (strategy === 'ALL') {
        return hasAllEntry ? c.strategyId === 'all' : true;
      }
      // 다른 strategy 탭은 raw 전략 entry 만 (ALL 통합 entry 제외)
      return c.strategyId !== 'all' && c.strategyLabel === strategy;
    })
    .filter(c => timeframe === 'ALL' || c.timeframe === timeframe)
    .sort((a, b) => {
      if (sortBy === 'rank') {
        const ar = a.rank ?? Infinity;
        const br = b.rank ?? Infinity;
        if (ar !== br) return ar - br;
        return (b.score ?? -Infinity) - (a.score ?? -Infinity);
      }
      if (sortBy === 'rsi') return (a.rsi ?? Infinity) - (b.rsi ?? Infinity);
      if (sortBy === 'per') {
        const ap = a.per != null && a.per > 0 ? a.per : Infinity;
        const bp = b.per != null && b.per > 0 ? b.per : Infinity;
        return ap - bp;
      }
      if (sortBy === 'price') return a.entry - b.entry;
      return 0;
    });

  return (
    <div style={{ background: 'var(--canvas)', minHeight: '100vh' }}>
      <TopNav
        marketIndices={marketIndices}
        generatedAtDisplay={generatedAtDisplay}
        targetDateDisplay={targetDateDisplay}
        marketRegime={marketRegime}
        marketBreadth={marketBreadth}
        marketAxes={marketAxes}
        fearGreed={fearGreed}
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
          <div key={`${card.ticker}-${card.strategyId}`} style={{
            background: 'var(--canvas)',
            borderRight: '1px solid var(--hairline)',
            borderBottom: '1px solid var(--hairline)',
          }}>
            <TickerCard
              card={card}
              onClick={() => router.push(`/signals/${card.ticker}`)}
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
