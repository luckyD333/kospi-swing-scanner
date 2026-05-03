import type { Signal, SignalsResponse } from '@/types/signal';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function fetchSignals(): Promise<SignalsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/signals`, {
    next: { revalidate: 300 },
  });
  if (!res.ok) throw new Error(`API ${res.status}: /api/signals`);
  return res.json() as Promise<SignalsResponse>;
}

export async function fetchSignal(ticker: string): Promise<Signal> {
  const res = await fetch(`${API_BASE_URL}/api/signals/${ticker}`, {
    next: { revalidate: 300 },
  });
  if (!res.ok) throw new Error(`API ${res.status}: /api/signals/${ticker}`);
  return res.json() as Promise<Signal>;
}
