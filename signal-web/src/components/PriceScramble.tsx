'use client';

import { useState, useEffect } from 'react';

function useScramble(target: string, duration = 900): string {
  const [display, setDisplay] = useState(() => target.replace(/./g, '0'));
  useEffect(() => {
    const len = target.length;
    const start = performance.now();
    let raf: number;
    function frame(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const lockedCount = Math.floor(progress * len);
      let result = '';
      for (let i = 0; i < len; i++) {
        if (i < lockedCount) {
          result += target[i];
        } else {
          result += /[0-9]/.test(target[i])
            ? String(Math.floor(Math.random() * 10))
            : target[i];
        }
      }
      setDisplay(result);
      if (progress < 1) raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return display;
}

interface Props {
  priceDisplay: string;
  changeDisplay?: string | null;
  direction?: 'up' | 'down' | 'flat';
  fontSize: string;
}

export default function PriceScramble({ priceDisplay, changeDisplay, direction, fontSize }: Props) {
  const raw = priceDisplay.replace(/[^0-9]/g, '');
  const scrambled = useScramble(raw);

  let display = priceDisplay;
  if (scrambled.length === raw.length) {
    let si = 0;
    display = priceDisplay.split('').map(ch => /[0-9]/.test(ch) ? scrambled[si++] : ch).join('');
  }

  const changeColor =
    direction === 'up' ? 'var(--gain)' :
    direction === 'down' ? 'var(--loss)' :
    'var(--muted)';

  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: '16px', flexWrap: 'wrap' }}>
      <span style={{
        fontFamily: 'var(--f-mono-stack)',
        fontSize,
        fontWeight: 400,
        lineHeight: 1.1,
        letterSpacing: '-0.5px',
        color: 'var(--ink)',
      }}>
        {display}
      </span>
      {changeDisplay != null && (
        <span style={{
          fontFamily: 'var(--f-mono-stack)',
          fontSize: `calc(${fontSize} * 0.55)`,
          fontWeight: 400,
          color: changeColor,
          letterSpacing: '1px',
        }}>
          {changeDisplay}
        </span>
      )}
    </div>
  );
}
