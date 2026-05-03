// id에서 영어 서수를 추출해 "전략 N" 형식으로 단축
// strategy_two_cross_sectional_momentum → 전략 2
// strategy_four_pullback_ma             → 전략 4 (라벨이 STRATEGY_FOUR_PULLBACK_MA처럼 길어도 무관)

const NUMBER_WORD_TO_DIGIT: Record<string, string> = {
  one: '1',
  two: '2',
  three: '3',
  four: '4',
  five: '5',
  six: '6',
  seven: '7',
  eight: '8',
  nine: '9',
};

export function formatStrategyLabel(id: string, fallback: string): string {
  const m = id.match(/^strategy_([a-z]+)/i);
  const word = m?.[1]?.toLowerCase();
  if (word && NUMBER_WORD_TO_DIGIT[word]) {
    return `전략 ${NUMBER_WORD_TO_DIGIT[word]}`;
  }
  return fallback;
}
