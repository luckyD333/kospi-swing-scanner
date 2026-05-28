import type { CardProps } from '@/lib/adapt';

export type AssetGroup = 'ALL' | '주식' | 'ETF';

export const DEFAULT_ASSET_GROUP: AssetGroup = 'ALL';

export const ASSET_GROUPS: AssetGroup[] = [DEFAULT_ASSET_GROUP, '주식', 'ETF'];

export const isEtfCard = (card: CardProps): boolean =>
  card.pool === 'ETN_ETF' || card.productType === 'ETF' || card.productType === 'ETN';

export function filterCardsByAssetGroup(cards: CardProps[], assetGroup: AssetGroup): CardProps[] {
  if (assetGroup === 'ALL') return cards;
  return cards.filter((card) => assetGroup === 'ETF' ? isEtfCard(card) : !isEtfCard(card));
}
