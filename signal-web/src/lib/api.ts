import type { Signal, SignalsResponse } from '@/types/signal';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// signal-api 는 mtime/size invalidation + ETag 로 매 요청 최신 응답 가능.
// Next.js 측 ISR 캐시를 끄고 매 SSR 호출마다 신규 fetch (사용자 의도: 항상 최신).
export async function fetchSignals(): Promise<SignalsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/signals`, {
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`API ${res.status}: /api/signals`);
  return res.json() as Promise<SignalsResponse>;
}

export async function fetchSignal(ticker: string): Promise<Signal> {
  const res = await fetch(`${API_BASE_URL}/api/signals/${ticker}`, {
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`API ${res.status}: /api/signals/${ticker}`);
  return res.json() as Promise<Signal>;
}
