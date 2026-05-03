'use client';

import { useEffect } from 'react';
import { ts } from '@/lib/typography';

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function Error({ error, reset }: Props) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div style={{
      background: 'var(--canvas)',
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '24px',
    }}>
      <div style={{
        fontFamily: 'var(--f-display-stack)',
        fontSize: 'clamp(48px, 8vw, 96px)',
        fontWeight: 400,
        letterSpacing: '4px',
        color: 'var(--hairline-strong)',
        lineHeight: 1,
      }}>
        SIGNAL
      </div>
      <div style={ts('caption', 'var(--muted)')}>
        서버에 연결할 수 없어요
      </div>
      <button
        onClick={reset}
        style={{
          ...ts('caption', 'var(--ink)'),
          background: 'none',
          border: '1px solid var(--hairline-strong)',
          padding: '12px 28px',
          cursor: 'pointer',
          transition: 'border-color 150ms',
          marginTop: '8px',
        }}
      >
        다시 시도
      </button>
    </div>
  );
}
