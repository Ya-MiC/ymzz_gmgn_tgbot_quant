"""Causal indicators. A value at index i uses only bars[0..i] inside the current gap segment."""

from __future__ import annotations


def segment_starts(timestamps: list[int] | None, expected_seconds: int | None, factor: float = 1.5) -> list[int]:
    if not timestamps:
        return [0]
    if not expected_seconds:
        return [0]
    limit = expected_seconds * factor
    starts = [0]
    for i in range(1, len(timestamps)):
        if timestamps[i] - timestamps[i - 1] > limit:
            starts.append(i)
    return starts


def _segments(n: int, timestamps, expected_seconds, factor):
    starts = [s for s in segment_starts(timestamps, expected_seconds, factor) if s < n]
    bounds = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else n
        bounds.append((start, end))
    if not bounds and n:
        bounds.append((0, n))
    return bounds


def rsi_wilder(
    closes: list[float],
    period: int = 14,
    timestamps: list[int] | None = None,
    expected_seconds: int | None = None,
    gap_factor: float = 1.5,
) -> list[float | None]:
    if period < 1:
        raise ValueError("period")
    n = len(closes)
    out: list[float | None] = [None] * n
    for start, end in _segments(n, timestamps, expected_seconds, gap_factor):
        if end - start <= period:
            continue
        gains = 0.0
        losses = 0.0
        for i in range(start + 1, start + period + 1):
            delta = closes[i] - closes[i - 1]
            gains += max(delta, 0.0)
            losses += max(-delta, 0.0)
        avg_gain = gains / period
        avg_loss = losses / period
        out[start + period] = _rsi_from_avgs(avg_gain, avg_loss)
        for i in range(start + period + 1, end):
            delta = closes[i] - closes[i - 1]
            gain = max(delta, 0.0)
            loss = max(-delta, 0.0)
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
            out[i] = _rsi_from_avgs(avg_gain, avg_loss)
    return out


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0 and avg_gain == 0.0:
        return 50.0
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr_percent(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
    timestamps: list[int] | None = None,
    expected_seconds: int | None = None,
    gap_factor: float = 1.5,
) -> list[float | None]:
    """Wilder ATR / close. First ATR in a segment uses `period` true ranges starting at the second bar."""
    if period < 1:
        raise ValueError("period")
    n = len(closes)
    out: list[float | None] = [None] * n
    for start, end in _segments(n, timestamps, expected_seconds, gap_factor):
        if end - start <= period:
            continue
        trs: list[float] = []
        for i in range(start + 1, end):
            prev_close = closes[i - 1]
            tr = max(highs[i] - lows[i], abs(highs[i] - prev_close), abs(lows[i] - prev_close))
            trs.append(tr)
        # trs[0] corresponds to bar index start+1. Need `period` TRs → bar index start+period.
        if len(trs) < period:
            continue
        atr = sum(trs[:period]) / period
        idx = start + period
        if closes[idx] > 0:
            out[idx] = atr / closes[idx]
        for j in range(period, len(trs)):
            atr = (atr * (period - 1) + trs[j]) / period
            idx = start + 1 + j
            if closes[idx] > 0:
                out[idx] = atr / closes[idx]
    return out


def relative_volume(
    volumes: list[float],
    period: int = 20,
    timestamps: list[int] | None = None,
    expected_seconds: int | None = None,
    gap_factor: float = 1.5,
) -> list[float | None]:
    n = len(volumes)
    out: list[float | None] = [None] * n
    if period < 1:
        raise ValueError("period")
    for start, end in _segments(n, timestamps, expected_seconds, gap_factor):
        if end - start < period:
            continue
        window = 0.0
        for i in range(start, start + period):
            window += volumes[i]
        for i in range(start + period - 1, end):
            if i > start + period - 1:
                window += volumes[i]
                window -= volumes[i - period]
            sma = window / period
            if sma > 0:
                out[i] = volumes[i] / sma
            else:
                out[i] = None
    return out
