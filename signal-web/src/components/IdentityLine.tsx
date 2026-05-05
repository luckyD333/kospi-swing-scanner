'use client';

import { useState } from 'react';
import { ts } from '@/lib/typography';

interface Props {
  onOpenAbout: () => void;
}

function AboutBtn({ onOpen }: { onOpen: () => void }) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onOpen}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        ...ts('caption-sm', hov ? 'var(--body)' : 'var(--muted)'),
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '0',
        transition: 'color 150ms',
        flexShrink: 0,
      }}
      aria-label="서비스 안내 열기"
    >
      <span style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '16px',
        height: '16px',
        border: `1px solid ${hov ? 'var(--body)' : 'var(--muted)'}`,
        borderRadius: '50%',
        fontSize: '10px',
        lineHeight: 1,
        transition: 'border-color 150ms',
        flexShrink: 0,
      }}>?</span>
      <span style={{ letterSpacing: '0.08em' }}>ABOUT / 가이드</span>
    </button>
  );
}

export default function IdentityLine({ onOpenAbout }: Props) {
  return (
    <div style={{
      height: '52px',
      padding: '0 40px',
      borderTop: '1px solid var(--hairline)',
      borderBottom: '1px solid var(--hairline)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      background: 'var(--canvas)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
        <span style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: 'var(--gain)',
          boxShadow: '0 0 6px var(--gain)',
          flexShrink: 0,
        }} />
        <span style={{
          ...ts('caption-sm', 'var(--muted)'),
          fontFamily: 'var(--f-mono-stack)',
          fontSize: '11px',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          SIGNAL / 알고리즘이 매주 추려낸 매매 후보 명세서 — 추천 아닌 관찰용 데이터
        </span>
      </div>
      <AboutBtn onOpen={onOpenAbout} />
    </div>
  );
}
