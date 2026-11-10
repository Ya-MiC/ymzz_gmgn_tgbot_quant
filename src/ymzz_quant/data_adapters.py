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
    dropped_unclosed: list[dict]


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


def parse_utc_stamp(raw: object) -> int | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return int(datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


def fetched_at_unix(path: Path) -> int | None:
    """Read the sidecar fetch time. Missing or unparsable times do not count as closed."""
    meta_path = Path(str(path) + ".meta.json")
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return parse_utc_stamp(meta.get("fetched_at_utc"))


def bar_is_closed(open_ts: int, interval_seconds: int, fetched_at: int | None) -> bool:
    """A candle timestamp is its open. It is closed only when open + interval <= fetch time.

    The interval is the series resolution (86400 for a UTC day, 3600 for an hour).
    Equality counts as closed: the period has ended. A missing fetch time is not closed.
    """
    if fetched_at is None or interval_seconds <= 0:
        return False
    return open_ts + interval_seconds <= fetched_at


def closed_probability_points(points: list[dict], fetched_at: int | None) -> tuple[list[dict], list[dict]]:
    """Keep probability buckets whose window ended at or before the fetch.

    resolution_seconds == 0 is a terminal live tick, not a closed bucket.
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    for point in points:
        resolution = int(point.get("resolution_seconds") or 0)
        if resolution <= 0:
            dropped.append({**point, "reason": "terminal_tick_not_a_closed_bucket"})
            continue
        if fetched_at is None or point["timestamp"] + resolution > fetched_at:
            dropped.append({**point, "reason": "bucket_open_at_fetch"})
            continue
        kept.append(point)
    return kept, dropped


def load_ohlcv_files(paths: list[Path], expected_interval: int) -> SeriesLoad:
    if not paths:
        raise FileNotFoundError("no OHLCV files")
    closed_by_ts: dict[int, list[tuple[Bar, int, str]]] = {}
    open_by_ts: dict[int, list[tuple[int | None, str]]] = {}
    sources = []
    digest = hashlib.sha256()
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        raw = path.read_bytes()
        digest.update(raw)
        sources.append(str(path))
        fetched = fetched_at_unix(path)
        for bar in parse_gt_ohlcv_payload(json.loads(raw)):
            if bar_is_closed(bar.ts, expected_interval, fetched):
                closed_by_ts.setdefault(bar.ts, []).append((bar, fetched, str(path)))
            else:
                open_by_ts.setdefault(bar.ts, []).append((fetched, str(path)))
    dropped_unclosed = []
    for ts in sorted(open_by_ts):
        if ts in closed_by_ts:
            continue
        fetches = [item[0] for item in open_by_ts[ts] if item[0] is not None]
        open_label = fmt_ts(ts)
        close_label = fmt_ts(ts + expected_interval)
        dropped_unclosed.append(
            {
                "ts": ts,
                "utc": open_label["utc"],
                "kst": open_label["kst"],
                "close_ts": ts + expected_interval,
                "close_utc": close_label["utc"],
                "close_kst": close_label["kst"],
                "fetched_at_unix": min(fetches) if fetches else None,
                "fetched_at_utc": (
                    datetime.fromtimestamp(min(fetches), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if fetches else None
                ),
                "interval_seconds": expected_interval,
                "sources": [item[1] for item in open_by_ts[ts]],
                "reason": "unclosed_at_fetch",
            }
        )
    combined = [closed_by_ts[ts][0][0] for ts in sorted(closed_by_ts)]
    duplicates = 0
    invalid = 0
    dedup: list[Bar] = []
    for ts in sorted(closed_by_ts):
        observations = closed_by_ts[ts]
        first = observations[0][0]
        for extra, _fetched, _source in observations[1:]:
            duplicates += 1
            if extra != first:
                raise ValueError(f"conflicting duplicate timestamp {ts}")
        if not _ohlc_sane(first):
            invalid += 1
            continue
        dedup.append(first)
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
        dropped_unclosed=dropped_unclosed,
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
