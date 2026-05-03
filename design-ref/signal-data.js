
// Signal — Plausible invented Korean stock data
const SIGNALS_DATA = [
  {
    ticker: "001390", name: "KG케미칼", nameEn: "KG Chemical",
    strategy: "STRATEGY THREE", timeframe: "1H",
    entry: 7070, stop: 6820, target1: 7580, target2: 8100,
    rrRatio: 2.04, rrBand: "SWEET", score: 87,
    currentPrice: 7120, marketCap: "₩4,753억", change: +0.71,
    volume: "2,847,000", atr: 183, rsi: 58, per: 11.2,
    description: "화학 소재 분야 선도 기업. 전략 3의 트렌드 추종 알고리즘이 단기 모멘텀 구간을 포착했다."
  },
  {
    ticker: "005380", name: "현대자동차", nameEn: "Hyundai Motor",
    strategy: "STRATEGY ONE", timeframe: "4H",
    entry: 198500, stop: 192000, target1: 211000, target2: 225000,
    rrRatio: 1.92, rrBand: "SWEET", score: 82,
    currentPrice: 201000, marketCap: "₩42.3조", change: +1.26,
    volume: "891,200", atr: 4320, rsi: 62, per: 8.4,
    description: "글로벌 전기차 전환 가속화 국면에서 기술적 돌파 패턴이 형성되었다."
  },
  {
    ticker: "035420", name: "NAVER", nameEn: "NAVER Corporation",
    strategy: "STRATEGY TWO", timeframe: "1D",
    entry: 187000, stop: 179000, target1: 204000, target2: 218000,
    rrRatio: 2.13, rrBand: "SWEET", score: 91,
    currentPrice: 189500, marketCap: "₩30.8조", change: +1.34,
    volume: "1,203,400", atr: 5840, rsi: 65, per: 22.1,
    description: "AI 검색 전환 수혜주. 전략 2의 중기 모멘텀 스크리너가 기술적 저점 반등 구간을 포착했다."
  },
  {
    ticker: "000660", name: "SK하이닉스", nameEn: "SK Hynix",
    strategy: "STRATEGY THREE", timeframe: "1H",
    entry: 178000, stop: 171000, target1: 192000, target2: 204000,
    rrRatio: 2.00, rrBand: "SWEET", score: 88,
    currentPrice: 180500, marketCap: "₩130.1조", change: +1.40,
    volume: "3,241,000", atr: 4950, rsi: 61, per: 14.7,
    description: "HBM 메모리 수요 급증에 따른 실적 개선 기대감이 반영되고 있다."
  },
  {
    ticker: "068270", name: "셀트리온", nameEn: "Celltrion",
    strategy: "STRATEGY ONE", timeframe: "4H",
    entry: 147500, stop: 141000, target1: 159000, target2: 168000,
    rrRatio: 1.77, rrBand: "UNDER", score: 74,
    currentPrice: 149200, marketCap: "₩19.7조", change: +1.15,
    volume: "678,900", atr: 3820, rsi: 54, per: 31.2,
    description: "바이오시밀러 유럽 수출 확대 모멘텀."
  },
  {
    ticker: "207940", name: "삼성바이오로직스", nameEn: "Samsung Biologics",
    strategy: "STRATEGY TWO", timeframe: "1D",
    entry: 897000, stop: 862000, target1: 965000, target2: 1020000,
    rrRatio: 1.94, rrBand: "SWEET", score: 85,
    currentPrice: 912000, marketCap: "₩60.4조", change: +1.67,
    volume: "124,300", atr: 21400, rsi: 63, per: 52.8,
    description: "글로벌 위탁생산 수주 잔고 역대 최고치 경신."
  },
  {
    ticker: "096770", name: "SK이노베이션", nameEn: "SK Innovation",
    strategy: "STRATEGY THREE", timeframe: "1H",
    entry: 118500, stop: 113000, target1: 128000, target2: 136000,
    rrRatio: 1.73, rrBand: "UNDER", score: 69,
    currentPrice: 120100, marketCap: "₩11.2조", change: +1.35,
    volume: "987,600", atr: 3210, rsi: 52, per: 6.9,
    description: "배터리 분리 이후 사업 재편 가속화."
  },
  {
    ticker: "028260", name: "삼성물산", nameEn: "Samsung C&T",
    strategy: "STRATEGY ONE", timeframe: "4H",
    entry: 141000, stop: 135500, target1: 152000, target2: 160000,
    rrRatio: 2.00, rrBand: "SWEET", score: 83,
    currentPrice: 143500, marketCap: "₩27.1조", change: +1.77,
    volume: "412,700", atr: 3480, rsi: 59, per: 10.1,
    description: "지배구조 개선 기대감과 건설 수주 호조가 동반된 상승 국면."
  },
  {
    ticker: "373220", name: "LG에너지솔루션", nameEn: "LG Energy Solution",
    strategy: "STRATEGY TWO", timeframe: "1D",
    entry: 312000, stop: 299000, target1: 338000, target2: 358000,
    rrRatio: 2.00, rrBand: "SWEET", score: 86,
    currentPrice: 318000, marketCap: "₩72.7조", change: +1.92,
    volume: "567,200", atr: 8920, rsi: 64, per: 35.4,
    description: "전기차 배터리 수요 회복과 북미 IRA 수혜가 동시에 가시화되고 있다."
  },
  {
    ticker: "051910", name: "LG화학", nameEn: "LG Chem",
    strategy: "STRATEGY THREE", timeframe: "1H",
    entry: 287000, stop: 275000, target1: 312000, target2: 332000,
    rrRatio: 2.08, rrBand: "SWEET", score: 89,
    currentPrice: 291000, marketCap: "₩20.4조", change: +1.39,
    volume: "334,800", atr: 7650, rsi: 60, per: 13.8,
    description: "배터리 소재 및 첨단 화학 사업 전환 모멘텀."
  },
  {
    ticker: "012330", name: "현대모비스", nameEn: "Hyundai Mobis",
    strategy: "STRATEGY ONE", timeframe: "4H",
    entry: 241000, stop: 231000, target1: 261000, target2: 276000,
    rrRatio: 2.00, rrBand: "SWEET", score: 80,
    currentPrice: 245000, marketCap: "₩22.8조", change: +1.66,
    volume: "289,400", atr: 6230, rsi: 57, per: 9.7,
    description: "자율주행 부품 수주 본격화와 전기차 전환 부품 매출 증가."
  },
  {
    ticker: "000270", name: "기아", nameEn: "Kia Corporation",
    strategy: "STRATEGY TWO", timeframe: "1D",
    entry: 89500, stop: 85900, target1: 97000, target2: 103000,
    rrRatio: 2.08, rrBand: "SWEET", score: 84,
    currentPrice: 91200, marketCap: "₩37.1조", change: +1.90,
    volume: "1,847,300", atr: 2340, rsi: 66, per: 7.3,
    description: "PBV 시장 선도 포지션 구축. EV9 글로벌 판매 호조로 브랜드 가치 상승이 지속되고 있다."
  }
];

const GENERATED_AT = "2026-05-02 22:15 KST";
const STRATEGIES = ["ALL", "STRATEGY ONE", "STRATEGY TWO", "STRATEGY THREE"];
const TIMEFRAMES = ["ALL", "1H", "4H", "1D"];
