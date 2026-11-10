"""Chronological split of the actual fetched window. Fractions are pre-registered, not fit to returns."""

from __future__ import annotations


def split_labels(timestamps: list[int], train_frac: float = 0.5, val_frac: float = 0.25) -> list[str]:
    if not timestamps:
        return []
    if train_frac <= 0 or val_frac <= 0 or train_frac + val_frac >= 1:
        raise ValueError("split fractions")
    t0 = timestamps[0]
    t1 = timestamps[-1]
    span = t1 - t0
    train_end = t0 + span * train_frac
    val_end = t0 + span * (train_frac + val_frac)
    labels = []
    for ts in timestamps:
        if ts < train_end:
            labels.append("train")
        elif ts < val_end:
            labels.append("validation")
        else:
            labels.append("heldout")
    if labels:
        labels[-1] = "heldout"
    return labels


def split_bounds(timestamps: list[int], train_frac: float = 0.5, val_frac: float = 0.25) -> dict:
    t0 = timestamps[0]
    t1 = timestamps[-1]
    span = t1 - t0
    return {
        "start_ts": t0,
        "end_ts": t1,
        "train_end_exclusive_ts": t0 + span * train_frac,
        "validation_end_exclusive_ts": t0 + span * (train_frac + val_frac),
        "train_frac": train_frac,
        "val_frac": val_frac,
        "heldout_frac": 1 - train_frac - val_frac,
        "rule": "50/25/25 of the actual fetched timestamp span; not chosen from returns",
    }


def linear_quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if q < 0 or q > 1:
        raise ValueError("q")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    weight = pos - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight
