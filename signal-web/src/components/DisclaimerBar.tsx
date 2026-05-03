import { ts } from '@/lib/typography';

export default function DisclaimerBar() {
  return (
    <div style={{
      position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 99,
      height: '30px',
      background: 'rgba(0,0,0,0.97)',
      backdropFilter: 'blur(8px)',
      borderTop: '1px solid var(--hairline)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '0 40px',
    }}>
      <p style={{
        ...ts('caption-sm', 'var(--muted-soft)'),
        letterSpacing: '1.5px',
      }}>
        본 시그널은 알고리즘이 생성한 결과로 투자 권유가 아닙니다. 모든 투자 결정의 책임은 투자자 본인에게 있습니다.
      </p>
    </div>
  );
}
