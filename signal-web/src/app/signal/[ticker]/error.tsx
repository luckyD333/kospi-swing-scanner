'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ts } from '@/lib/typography';

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function Error({ error, reset }: Props) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  const router = useRouter();

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
      <div style={ts('caption', 'var(--muted)')}>
        시그널 데이터를 불러올 수 없어요
      </div>
      <div style={{ display: 'flex', gap: '12px' }}>
        <button
          onClick={reset}
          style={{
            ...ts('caption', 'var(--ink)'),
            background: 'none',
            border: '1px solid var(--hairline-strong)',
            padding: '12px 28px',
            cursor: 'pointer',
          }}
        >
          다시 시도
        </button>
        <button
          onClick={() => router.push('/')}
          style={{
            ...ts('caption', 'var(--muted)'),
            background: 'none',
            border: '1px solid var(--hairline)',
            padding: '12px 28px',
            cursor: 'pointer',
          }}
        >
          카탈로그로
        </button>
      </div>
    </div>
  );
}
