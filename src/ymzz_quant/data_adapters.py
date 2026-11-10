"""Parsers for public GeckoTerminal OHLCV and Polymarket probability history.

Synthetic rows are not produced here. Missing files raise; callers must not invent candles.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class Bar:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def iso_utc(self) -> str:
        return datetime.fromtimestamp(self.ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def iso_kst(self) -> str:
        return datetime.fromtimestamp(self.ts, KST).strftime("%Y-%m-%dT%H:%M:%S%z")


@dataclass(frozen=True)
class SeriesLoad:
    bars: list[Bar]
    gaps: list[dict]
    duplicate_timestamps: int
    invalid_bars: int
    sources: list[str]
    sha256: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_gt_ohlcv_payload(payload: dict) -> list[Bar]:
    try:
        rows = payload["data"]["attributes"]["ohlcv_list"]
    except (KeyError, TypeError) as exc:
        raise ValueError("GeckoTerminal OHLCV payload missing data.attributes.ohlcv_list") from exc
    bars = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise ValueError("OHLCV row must be [timestamp, open, high, low, close, volume]")
        ts, open_, high, low, close, volume = row[:6]
        bars.append(
            Bar(
                ts=int(ts),
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=float(volume),
            )
        )
    return bars


def parse_polymarket_prices(payload: dict) -> list[dict]:
    if "data" not in payload or "pagination" not in payload:
        raise ValueError("Polymarket prices-history payload missing data/pagination")
    points = []
    for row in payload["data"]:
        price = float(row["price"])
        if price < 0 or price > 1:
            raise ValueError("Polymarket price outside 0..1")
        points.append(
            {
                "timestamp": int(row["timestamp"]),
                "price": price,
                "resolution_seconds": int(row.get("resolution_seconds") or 0),
            }
        )
    return points


def parse_pool_trades(payload: dict) -> list[dict]:
    """Public pool swaps. This is not wallet profit, and transfers are not in this feed."""
    if "data" not in payload:
        raise ValueError("trade payload missing data")
    out = []
    for item in payload["data"]:
        attr = item.get("attributes") or {}
        kind = attr.get("kind")
        if kind not in {"buy", "sell"}:
            raise ValueError(f"unexpected trade kind {kind}")
        out.append(
            {
                "block_timestamp": attr.get("block_timestamp"),
                "tx_hash": attr.get("tx_hash"),
                "kind": kind,
                "volume_in_usd": attr.get("volume_in_usd"),
                "tx_from_address": attr.get("tx_from_address"),
                "is_anomalous": attr.get("is_anomalous"),
                "pnl": None,
                "note": "pool swap scaffold; not a wallet return; transfers are absent",
            }
        )
    return out


def load_ohlcv_files(paths: list[Path], expected_interval: int) -> SeriesLoad:
    if not paths:
        raise FileNotFoundError("no OHLCV files")
    combined: list[Bar] = []
    sources = []
    digest = hashlib.sha256()
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        raw = path.read_bytes()
        digest.update(raw)
        sources.append(str(path))
        combined.extend(parse_gt_ohlcv_payload(json.loads(raw)))
    combined.sort(key=lambda b: b.ts)
    dedup: list[Bar] = []
    duplicates = 0
    invalid = 0
    for bar in combined:
        if dedup and dedup[-1].ts == bar.ts:
            duplicates += 1
            if dedup[-1] != bar:
                raise ValueError(f"conflicting duplicate timestamp {bar.ts}")
            continue
        if not _ohlc_sane(bar):
            invalid += 1
            continue
        dedup.append(bar)
    gaps = []
    limit = expected_interval * 1.5
    for prev, nxt in zip(dedup, dedup[1:]):
        delta = nxt.ts - prev.ts
        if delta > limit:
            gaps.append(
                {
                    "after_ts": prev.ts,
                    "before_ts": nxt.ts,
                    "missing_seconds": delta - expected_interval,
                }
            )
    return SeriesLoad(
        bars=dedup,
        gaps=gaps,
        duplicate_timestamps=duplicates,
        invalid_bars=invalid,
        sources=sources,
        sha256=digest.hexdigest(),
    )


def _ohlc_sane(bar: Bar) -> bool:
    if min(bar.open, bar.high, bar.low, bar.close) <= 0:
        return False
    if bar.volume < 0:
        return False
    if bar.high < bar.low:
        return False
    if bar.high + 1e-12 < max(bar.open, bar.close):
        return False
    if bar.low - 1e-12 > min(bar.open, bar.close):
        return False
    return True


def fmt_ts(ts: int) -> dict:
    utc = datetime.fromtimestamp(ts, timezone.utc)
    kst = utc.astimezone(KST)
    return {
        "ts": ts,
        "utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kst": kst.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
