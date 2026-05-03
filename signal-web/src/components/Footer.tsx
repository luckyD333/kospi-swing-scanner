import { ts } from '@/lib/typography';

export default function Footer() {
  return (
    <footer style={{
      background: 'var(--canvas)',
      borderTop: '1px solid var(--hairline)',
      padding: '20px 40px',
      marginBottom: '30px',
    }}>
      <div style={{ maxWidth: '1280px', margin: '0 auto', display: 'flex', justifyContent: 'flex-end' }}>
        <div style={ts('wordmark', 'var(--muted-soft)')}>
          SIGNAL
        </div>
      </div>
    </footer>
  );
}
