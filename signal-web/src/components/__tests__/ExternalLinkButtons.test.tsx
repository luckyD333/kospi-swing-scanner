import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { NaverIconLink, TradingViewIconLink } from '@/components/ExternalLinkButtons';

describe('외부 서비스 아이콘 버튼', () => {
  it('네이버 버튼은 새 탭으로 열리고 종목 페이지를 가리킨다', () => {
    const html = renderToStaticMarkup(createElement(NaverIconLink, { ticker: '005930' }));
    expect(html).toContain('href="https://finance.naver.com/item/main.naver?code=005930"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain('aria-label="네이버 금융에서 보기"');
  });

  it('트레이딩뷰 버튼은 스크린리더용 이름을 가진다', () => {
    const html = renderToStaticMarkup(createElement(TradingViewIconLink, { ticker: '247540' }));
    expect(html).toContain('symbol=KRX%3A247540');
    expect(html).toContain('aria-label="트레이딩뷰 차트 열기"');
  });
});
