"""유니버스(ticker 목록, 시총, 종목명) JSON 영속 캐시."""
from __future__ import annotations

import json
from pathlib import Path


class UniverseCache:
    def __init__(self, root: Path | str):
        self.root = Path(root) / "universe"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, market: str, date: str) -> Path:
        return self.root / f"{market}_{date}.json"

    def save(
        self,
        market: str,
        date: str,
        tickers: list[str],
        cap_lookup: dict[str, float],
        name_lookup: dict[str, str],
    ) -> None:
        payload = {
            "market": market,
            "date": date,
            "tickers": tickers,
            "cap_lookup": cap_lookup,
            "name_lookup": name_lookup,
        }
        self._path(market, date).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2)
        )

    def load(self, market: str, date: str) -> dict | None:
        path = self._path(market, date)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def latest(self, market: str) -> dict | None:
        """저장된 파일 중 날짜 최신 것 반환."""
        files = sorted(self.root.glob(f"{market}_*.json"), reverse=True)
        if not files:
            return None
        return json.loads(files[0].read_text())
