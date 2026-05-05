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
  'display-md':  '-0.01em',
  'display-sm':  '-0.01em',
  'title-md':    '0',
  'ticker-sm':   '0px',
  'numeric-lg':  '0px',
  'numeric-md':  '0px',
  caption:       '-0.01em',
  'caption-sm':  '-0.01em',
  button:        '0',
  'nav-link':    '-0.01em',
  wordmark:      '0.1em',
  'body-md':     undefined,
};

const UPPER: Record<TypoToken, boolean> = {
  'display-md':  false,
  'display-sm':  false,
  'title-md':    false,
  'ticker-sm':   false,
  'numeric-lg':  false,
  'numeric-md':  false,
  caption:       false,
  'caption-sm':  false,
  button:        false,
  'nav-link':    false,
  wordmark:      false,
  'body-md':     false,
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
