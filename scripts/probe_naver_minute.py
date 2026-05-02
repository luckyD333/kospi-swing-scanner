"""
네이버 siseJson minute timeframe 지원 실증 (research probe).

Plan: .claude/plans/active/2026-04-30-incremental-checkpoint-multi-timeframe.md (Task 2)

목적:
  - api.finance.naver.com/siseJson.naver?timeframe=X 가 어떤 X 를 지원하는지 확인
  - "minute"·"1m"·"30m"·"1h" 응답 포맷이 어떤지 (rows·cols·sample)
  - 결과로 plan 의 30m/1h scope 확정 여부 결정

사용:
  .venv/bin/python scripts/probe_naver_minute.py
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import requests

URL = "https://api.finance.naver.com/siseJson.naver"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def probe(timeframe: str, ticker: str = "005930"):
    end = date.today().strftime("%Y%m%d")
    start = (date.today() - timedelta(days=3)).strftime("%Y%m%d")
    try:
        r = requests.get(
            URL,
            params={
                "symbol": ticker,
                "requestType": 1,
                "startTime": start,
                "endTime": end,
                "timeframe": timeframe,
            },
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        return {"error": f"HTTP {type(e).__name__}: {e}"}

    text = r.text.strip().replace("'", '"')
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        return {"error": f"JSON decode: {e}", "raw_head": text[:200]}

    if not isinstance(raw, list) or len(raw) < 2:
        return {"empty": True, "raw_head": text[:200]}

    return {
        "rows": len(raw) - 1,
        "cols": raw[0],
        "sample": raw[1] if len(raw) > 1 else None,
    }


if __name__ == "__main__":
    for tf in ["day", "minute", "1m", "30m", "1h"]:
        result = probe(tf)
        if "error" in result:
            print(f"[{tf}] ERROR: {result['error']}")
        elif result.get("empty"):
            print(f"[{tf}] UNSUPPORTED (empty/invalid). raw head: {result.get('raw_head')!r}")
        else:
            print(
                f"[{tf}] OK rows={result['rows']} "
                f"cols={result['cols']} sample={result['sample']}"
            )
