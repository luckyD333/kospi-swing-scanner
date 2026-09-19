/** 종목코드로 네이버 금융 종목 페이지 URL 을 만든다. */
export function naverFinanceUrl(ticker: string): string {
  return `https://finance.naver.com/item/main.naver?code=${ticker}`;
}

/**
 * 종목코드로 트레이딩뷰 차트 URL 을 만든다.
 * 트레이딩뷰는 KOSPI·KOSDAQ 을 하나의 KRX 심볼 공간으로 묶어 취급하므로
 * 시장 구분 없이 코드만 있으면 된다.
 */
export function tradingViewUrl(ticker: string): string {
  return `https://kr.tradingview.com/chart/?symbol=${encodeURIComponent(`KRX:${ticker}`)}`;
}
