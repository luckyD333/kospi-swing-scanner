import { describe, expect, it } from 'vitest';

import { naverFinanceUrl, tradingViewUrl } from '@/lib/external-links';

describe('외부 서비스 링크 조립', () => {
  it('네이버 금융 URL 은 백엔드와 같은 형식을 쓴다', () => {
    expect(naverFinanceUrl('005930')).toBe(
      'https://finance.naver.com/item/main.naver?code=005930',
    );
  });

  it('트레이딩뷰 URL 은 KOSPI·KOSDAQ 구분 없이 KRX 접두사를 쓴다', () => {
    expect(tradingViewUrl('005930')).toBe(
      'https://kr.tradingview.com/chart/?symbol=KRX%3A005930',
    );
    expect(tradingViewUrl('247540')).toBe(
      'https://kr.tradingview.com/chart/?symbol=KRX%3A247540',
    );
  });
});
