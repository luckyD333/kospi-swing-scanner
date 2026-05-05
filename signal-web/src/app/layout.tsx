import type { Metadata } from 'next';
import { JetBrains_Mono, Inter } from 'next/font/google';
import localFont from 'next/font/local';
import './globals.css';

const jetbrainsMono = JetBrains_Mono({
  weight: '400',
  subsets: ['latin'],
  variable: '--f-mono',
  display: 'swap',
});

// Inter — non-Apple 플랫폼 fallback (Apple 기기에서는 system-ui = SF Pro가 우선)
const inter = Inter({
  subsets: ['latin'],
  variable: '--f-inter',
  display: 'swap',
});

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
      className={`${jetbrainsMono.variable} ${inter.variable} ${pretendard.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
