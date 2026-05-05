import { ts } from '@/lib/typography';

export default function Footer() {
  return (
    <footer style={{
      position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 99,
      height: '30px',
      background: 'rgba(0,0,0,0.97)',
      backdropFilter: 'blur(8px)',
      borderTop: '1px solid var(--hairline)',
      display: 'flex', alignItems: 'center',
      padding: '0 40px',
    }}>
      <div style={{ maxWidth: '1280px', width: '100%', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <p style={{ ...ts('caption-sm', 'var(--muted-soft)'), letterSpacing: '1.5px', margin: 0, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
          본 시그널은 알고리즘이 생성한 결과로 투자 권유가 아닙니다. 모든 투자 결정의 책임은 투자자 본인에게 있습니다.
        </p>
        <div style={{ ...ts('wordmark', 'var(--muted-soft)'), flexShrink: 0, paddingLeft: '16px' }}>
          SIG-BORA
        </div>
      </div>
    </footer>
  );
}
