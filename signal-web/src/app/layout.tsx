import type { Metadata } from 'next';
import { JetBrains_Mono } from 'next/font/google';
import localFont from 'next/font/local';
import './globals.css';

const jetbrainsMono = JetBrains_Mono({
  weight: '400',
  subsets: ['latin'],
  variable: '--f-mono',
  display: 'swap',
});

// --f-display 는 시스템 폰트(-apple-system/system-ui) fallback으로 해소.
// --f-display-ko: Pretendard (한글)
const pretendard = localFont({
  src: '../../public/fonts/Pretendard-Regular.woff2',
  variable: '--f-display-ko',
  weight: '400',
  display: 'swap',
});

export const metadata: Metadata = {
  title: "Signal — This Week's Stock Signals",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="ko"
      className={`${jetbrainsMono.variable} ${pretendard.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
