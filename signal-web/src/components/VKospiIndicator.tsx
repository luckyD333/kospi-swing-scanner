import type { VKospiSnapshot } from '@/types/signal';
import { ts } from '@/lib/typography';

interface Props {
  data: VKospiSnapshot;
  showBorder?: boolean;
}

export default function VKospiIndicator({ data, showBorder = false }: Props) {
  const changeColor = data.change_pct > 0
    ? 'var(--loss)'
    : data.change_pct < 0
      ? 'var(--gain)'
      : 'var(--flat)';
  const signedChange = `${data.change_pct > 0 ? '+' : ''}${data.change_pct.toFixed(2)}%`;
  const tooltip =
    `정보용 · 방향성 지표가 아님 · 매수 판단 미반영 · 기준일 ${data.asof}`;

  return (
    <div
      title={tooltip}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        paddingRight: '20px',
        marginRight: '20px',
        borderRight: showBorder ? '1px solid var(--hairline)' : 'none',
        flexShrink: 0,
      }}
    >
      <span style={ts('caption-sm', 'var(--muted)')}>V-KOSPI</span>
      <span style={ts('caption', 'var(--body-strong)')}>{data.value.toFixed(2)}</span>
      <span style={ts('caption-sm', changeColor)}>{signedChange}</span>
      <span style={ts('caption-sm', 'var(--muted)')}>
        90일 {data.percentile_90d.toFixed(1)}%
      </span>
    </div>
  );
}
