import type { Metadata } from 'next';
import { Saira_Condensed, Cormorant_Garamond, JetBrains_Mono, Noto_Serif_KR } from 'next/font/google';
import localFont from 'next/font/local';
import './globals.css';

const sairaCondensed = Saira_Condensed({
  weight: '400',
  subsets: ['latin'],
  variable: '--f-display',
  display: 'swap',
});

const cormorantGaramond = Cormorant_Garamond({
  weight: '400',
  subsets: ['latin'],
  variable: '--f-body',
  display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({
  weight: '400',
  subsets: ['latin'],
  variable: '--f-mono',
  display: 'swap',
});

// Korean fallback — design.md 'Note on Font Substitutes' 권장 글꼴
const pretendard = localFont({
  src: '../../public/fonts/Pretendard-Regular.woff2',
  variable: '--f-display-ko',
  weight: '400',
  display: 'swap',
});

const notoSerifKr = Noto_Serif_KR({
  weight: '400',
  subsets: ['latin'],
  variable: '--f-body-ko',
  display: 'swap',
});

export const metadata: Metadata = {
  title: "SIGNAL — THIS WEEK'S STOCK SIGNALS",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="ko"
      className={`${sairaCondensed.variable} ${cormorantGaramond.variable} ${jetbrainsMono.variable} ${pretendard.variable} ${notoSerifKr.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
