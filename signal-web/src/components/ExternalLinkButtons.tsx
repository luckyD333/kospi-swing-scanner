'use client';

import { useState, type ReactNode } from 'react';

import { naverFinanceUrl, tradingViewUrl } from '@/lib/external-links';

const MARK_SIZE = 22;

/** 네이버 브랜드 마크 — 초록 배지 안의 N */
function NaverMark() {
  return (
    <svg width={MARK_SIZE} height={MARK_SIZE} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect width="24" height="24" rx="5" fill="#03C75A" />
      <path d="M5 5h5.1l3.8 5.7V5H19v14h-5.1l-3.8-5.7V19H5z" fill="#fff" />
    </svg>
  );
}

/** 트레이딩뷰 브랜드 마크 — 파랑 배지 안의 T 와 삼각형 (기하 근사) */
function TradingViewMark() {
  return (
    <svg width={MARK_SIZE} height={MARK_SIZE} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect width="24" height="24" rx="5" fill="#2962FF" />
      <g fill="#fff">
        <path d="M4 6h9v3h-3v9H7V9H4z" />
        <path d="M14 6h6l-3 12z" />
      </g>
    </svg>
  );
}

/**
 * 외부 서비스로 나가는 아이콘 링크.
 * 카드 전체가 클릭 영역이라(TickerCard 루트 div 의 onClick) 클릭 전파를 여기서 끊는다.
 */
function ExternalIconButton({
  href,
  label,
  children,
}: {
  href: string;
  label: string;
  children: ReactNode;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={label}
      title={label}
      onClick={(e) => e.stopPropagation()}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        lineHeight: 0,
        borderRadius: 'var(--radius-sm)',
        opacity: hovered ? 1 : 0.62,
        transition: 'opacity 150ms ease-out',
      }}
    >
      {children}
    </a>
  );
}

export function NaverIconLink({ ticker }: { ticker: string }) {
  return (
    <ExternalIconButton href={naverFinanceUrl(ticker)} label="네이버 금융에서 보기">
      <NaverMark />
    </ExternalIconButton>
  );
}

export function TradingViewIconLink({ ticker }: { ticker: string }) {
  return (
    <ExternalIconButton href={tradingViewUrl(ticker)} label="트레이딩뷰 차트 열기">
      <TradingViewMark />
    </ExternalIconButton>
  );
}
