#!/usr/bin/env python3
"""Fetch keyless Kraken spot OHLC for BTC/USD and ETH/USD.

ccxt is not used. ccxt is a free MIT library; this script calls Kraken's
documented public OHLC endpoint directly. That endpoint does not require an
API key. A free library and permission to use a provider are different things.
No strategy returns are computed here.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
KST = ZoneInfo("Asia/Seoul")
UA = "ymzz-quant-research/0.1 (paper backtest; keyless Kraken public OHLC)"

REQUESTS = (
    ("XBTUSD", 1440, "kraken_ohlc_XBTUSD_1440.json"),
    ("ETHUSD", 1440, "kraken_ohlc_ETHUSD_1440.json"),
    ("XBTUSD", 60, "kraken_ohlc_XBTUSD_60.json"),
    ("ETHUSD", 60, "kraken_ohlc_ETHUSD_60.json"),
)


def fetch(pair: str, interval: int) -> tuple[bytes, str, datetime]:
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}"
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
        fetched = datetime.now(timezone.utc)
        if response.status != 200:
            raise RuntimeError(f"{url} -> {response.status}")
    return body, url, fetched


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for pair, interval, name in REQUESTS:
        body, url, fetched = fetch(pair, interval)
        payload = json.loads(body)
        if payload.get("error"):
            raise RuntimeError(f"{pair} {interval} {payload['error']}")
        path = CACHE / name
        path.write_bytes(body)
        meta = {
            "url": url,
            "pair": pair,
            "interval_minutes": interval,
            "fetched_at_utc": fetched.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fetched_at_kst": fetched.astimezone(KST).strftime("%Y-%m-%dT%H:%M:%S%z"),
            "sha256": hashlib.sha256(body).hexdigest(),
            "provider": "kraken_public_rest",
            "api_key_used": False,
            "library": None,
            "note": "Raw response. The daily candle that is still open at fetched_at is dropped by the loader, not here.",
        }
        Path(str(path) + ".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(name, meta["sha256"], meta["fetched_at_utc"])
        time.sleep(1.0)


if __name__ == "__main__":
    main()
