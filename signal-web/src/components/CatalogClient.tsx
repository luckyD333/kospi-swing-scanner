'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import type { MarketIndex, RegimeScore, BreadthScore, AxesScore, FearGreedSnapshot } from '@/types/signal';
import type { CardProps } from '@/lib/adapt';
import TopNav from './TopNav';
import FilterBar from './FilterBar';
import TickerCard from './TickerCard';
import Footer from './Footer';
import AboutOverlay from './AboutOverlay';

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
  const [coinFraction, setCoinFraction] = useState(0.4);
  const [aboutOpen, setAboutOpen] = useState(false);
  const onCloseAbout = useCallback(() => setAboutOpen(false), []);

  useEffect(() => {
    const id = setInterval(() => router.refresh(), 120_000);
    setCoinFraction(Math.random());
    return () => clearInterval(id);
  }, []);

  const filtered = useMemo(() => {
    const sortFn = (a: CardProps, b: CardProps) => {
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
    };

    if (strategy === 'ALL') {
      // ticker별 그룹화 — 대표 카드(최고 rank)에 모든 전략+TF 태그 병합
      const rawCards = cards.filter(c => c.strategyId !== 'all');
      const grouped = new Map<string, CardProps[]>();
      for (const c of rawCards) {
        const arr = grouped.get(c.ticker) ?? [];
        arr.push(c);
        grouped.set(c.ticker, arr);
      }
      return Array.from(grouped.values())
        .filter(group => timeframe === 'ALL' || group.some(c => c.timeframe === timeframe))
        .map(group => {
          const rep = group.reduce((best, c) => {
            const br = best.rank ?? Infinity;
            const cr = c.rank ?? Infinity;
            if (cr < br) return c;
            if (cr === br) return (c.score ?? -Infinity) > (best.score ?? -Infinity) ? c : best;
            return best;
          });
          const tagSet = new Set<string>();
          const allStrategyTags: Array<{ label: string; timeframe: string }> = [];
          for (const c of group) {
            const key = `${c.strategyLabel}|${c.timeframe}`;
            if (!tagSet.has(key)) {
              tagSet.add(key);
              allStrategyTags.push({ label: c.strategyLabel, timeframe: c.timeframe });
            }
          }
          return { ...rep, allStrategyTags };
        })
        .sort(sortFn);
    }
    return cards
      .filter(c => c.strategyId !== 'all' && c.strategyLabel === strategy)
      .filter(c => timeframe === 'ALL' || c.timeframe === timeframe)
      .sort(sortFn);
  }, [cards, strategy, timeframe, sortBy]);

  const navigate = useCallback(
    (ticker: string) => router.push(`/signals/${ticker}`),
    [router]
  );

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
        onOpenAbout={() => setAboutOpen(true)}
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
        {(() => {
          const coinIndex = Math.floor(coinFraction * (filtered.length + 1));

          const coinCell = (
            <div key="__coin__" style={{
              background: 'var(--canvas)',
              borderRight: '1px solid var(--hairline)',
              borderBottom: '1px solid var(--hairline)',
              position: 'relative',
              minHeight: '320px',
              overflow: 'hidden',
            }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`https://picsum.photos/600/800?random=${Math.floor(coinFraction * 1000)}`}
                alt=""
                style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.85, position: 'absolute', top: 0, left: 0 }}
              />
            </div>
          );

          const cardCells = filtered.map((card, i) => (
            <div key={`${card.ticker}-${card.strategyId}`} style={{
              background: 'var(--canvas)',
              borderRight: '1px solid var(--hairline)',
              borderBottom: '1px solid var(--hairline)',
            }}>
              <TickerCard
                card={card}
                onNavigate={navigate}
                index={i}
              />
            </div>
          ));

          if (filtered.length < 13) return cardCells;
          return [
            ...cardCells.slice(0, coinIndex),
            coinCell,
            ...cardCells.slice(coinIndex),
          ];
        })()}
      </div>

      <div style={{ height: '30px' }} />
      <Footer />
      <AboutOverlay open={aboutOpen} onClose={onCloseAbout} />
    </div>
  );
}
