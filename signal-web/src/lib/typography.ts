import type { CSSProperties } from 'react';

// design.md typography 12종 토큰 — globals.css의 --ts-* 변수와 1:1 매핑
export type TypoToken =
  | 'display-md'
  | 'display-sm'
  | 'title-md'
  | 'ticker-sm'
  | 'numeric-lg'
  | 'numeric-md'
  | 'caption'
  | 'caption-sm'
  | 'button'
  | 'nav-link'
  | 'wordmark'
  | 'body-md';

const TRACK: Record<TypoToken, string | undefined> = {
  'display-md': '2px',
  'display-sm': '1.5px',
  'title-md': '1px',
  'ticker-sm': '0px',
  'numeric-lg': '0px',
  'numeric-md': '0px',
  caption: '2px',
  'caption-sm': '2px',
  button: '2.5px',
  'nav-link': '2px',
  wordmark: '6px',
  'body-md': undefined,
};

const UPPER: Record<TypoToken, boolean> = {
  'display-md': true,
  'display-sm': true,
  'title-md': false,
  'ticker-sm': false,
  'numeric-lg': false,
  'numeric-md': false,
  caption: true,
  'caption-sm': true,
  button: true,
  'nav-link': true,
  wordmark: true,
  'body-md': false,
};

// font shorthand는 letter-spacing/text-transform/color를 포함하지 않으므로 별도 부여
export function ts(token: TypoToken, color: string = 'var(--ink)'): CSSProperties {
  return {
    font: `var(--ts-${token})`,
    letterSpacing: TRACK[token],
    textTransform: UPPER[token] ? 'uppercase' : 'none',
    color,
  };
}
