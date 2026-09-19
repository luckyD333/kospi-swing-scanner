'use client';

import { useState, type ReactNode } from 'react';

import { naverFinanceUrl, tradingViewUrl } from '@/lib/external-links';

const MARK_SIZE = 22;

/**
 * 네이버 브랜드 마크 — 초록 배지 안의 N.
 * 윤곽은 simple-icons(CC0) 가 배포하는 공식 로고 path 를 배지 크기에 맞춰 축소한 것.
 */
function NaverMark() {
  return (
    <svg width={MARK_SIZE} height={MARK_SIZE} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect width="24" height="24" rx="5" fill="#03C75A" />
      <path
        d="M16.273 12.845 7.376 0H0v24h7.726V11.156L16.624 24H24V0h-7.727v12.845Z"
        fill="#fff"
        transform="translate(5.04 5.04) scale(0.58)"
      />
    </svg>
  );
}

/**
 * 트레이딩뷰 브랜드 마크 — 파랑 배지 안의 심볼(원·T·삼각형).
 * 윤곽은 simple-icons(CC0) 가 배포하는 공식 로고 path 를 배지 크기에 맞춰 축소한 것.
 */
function TradingViewMark() {
  return (
    <svg width={MARK_SIZE} height={MARK_SIZE} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect width="24" height="24" rx="5" fill="#2962FF" />
      <path
        d="M15.8654 8.2789c0 1.3541-1.0978 2.4519-2.452 2.4519-1.354 0-2.4519-1.0978-2.4519-2.452 0-1.354 1.0978-2.4518 2.452-2.4518 1.3541 0 2.4519 1.0977 2.4519 2.4519zM9.75 6H0v4.9038h4.8462v7.2692H9.75Zm8.5962 0H24l-5.1058 12.173h-5.6538z"
        fill="#fff"
        transform="translate(3 3) scale(0.75)"
      />
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
