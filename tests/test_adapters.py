"""Public payload parsers and the real cached history. No fabricated prices."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ymzz_quant.catalog import ROOT
from ymzz_quant.data_adapters import (
    bar_is_closed,
    load_ohlcv_files,
    parse_gt_ohlcv_payload,
    parse_polymarket_prices,
    parse_pool_trades,
)
from ymzz_quant.indicators import rsi_wilder
from ymzz_quant.service import load_bars, load_named_scenarios, polymarket_summary, run_dataset
from ymzz_quant.tg_adapter import LiveSendDisabled, PaperReportAdapter


def _unix(stamp: str) -> int:
    return int(datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


def _write_ohlcv(directory: Path, name: str, rows: list, fetched_at: str | None) -> Path:
    path = directory / name
    path.write_text(json.dumps({"data": {"attributes": {"ohlcv_list": rows}}}), encoding="utf-8")
    if fetched_at is not None:
        Path(str(path) + ".meta.json").write_text(json.dumps({"fetched_at_utc": fetched_at}), encoding="utf-8")
    return path

FIXTURE_OHLCV = {
    "data": {
        "attributes": {
            "ohlcv_list": [
                [1700000000, 2, 3, 1, 2.5, 10],
                [1700086400, 2.5, 2.6, 2.4, 2.55, 11],
            ]
        }
    }
}


def test_parsers_accept_public_shapes():
    bars = parse_gt_ohlcv_payload(FIXTURE_OHLCV)
    assert [b.ts for b in bars] == [1700000000, 1700086400]
    points = parse_polymarket_prices(
        {"data": [{"timestamp": 10, "price": 0.25, "resolution_seconds": 43200}], "pagination": {"has_more": False}}
    )
    assert points[0]["price"] == 0.25
    trades = parse_pool_trades(
        {
            "data": [
                {
                    "attributes": {
                        "block_timestamp": "2026-11-10T00:00:00Z",
                        "tx_hash": "abc",
                        "kind": "buy",
                        "volume_in_usd": "1.5",
                        "tx_from_address": "SoLExample",
                        "is_anomalous": False,
                    }
                }
            ]
        }
    )
    assert trades[0]["pnl"] is None
    assert trades[0]["kind"] == "buy"


def test_real_cache_coverage_and_conservative_zero_trades():
    bars, meta = load_bars("wif_daily")
    assert meta["partial_bars_included"] is False
    assert meta["bar_count"] == 363
    assert meta["unclosed_bar_count"] == 1
    assert meta["gap_count"] == 0
    assert meta["duplicate_timestamps"] == 1
    assert bars[0].iso_utc() == "2025-11-12T00:00:00Z"
    assert bars[-1].iso_utc() == "2026-11-09T00:00:00Z"
    assert bars[-1].iso_kst() == "2026-11-09T09:00:00+0900"
    dropped = meta["dropped_unclosed"][0]
    assert dropped["utc"] == "2026-11-10T00:00:00Z"
    assert dropped["kst"] == "2026-11-10T09:00:00+0900"
    assert dropped["close_utc"] == "2026-11-11T00:00:00Z"
    assert dropped["close_kst"] == "2026-11-11T09:00:00+0900"
    assert dropped["reason"] == "unclosed_at_fetch"
    assert dropped["close_ts"] > dropped["fetched_at_unix"]
    assert dropped["ts"] not in {bar.ts for bar in bars}
    assert all(b.high >= b.low and b.close > 0 for b in bars)
    sol_bars, sol_meta = load_bars("sol_usdc_daily")
    assert sol_meta["bar_count"] == 183
    assert sol_meta["unclosed_bar_count"] == 1
    assert sol_bars[-1].iso_utc() == "2026-11-09T00:00:00Z"
    for key in ("bonk_daily_appendix", "popcat_daily_appendix"):
        other, other_meta = load_bars(key)
        assert other_meta["unclosed_bar_count"] == 1
        assert other[-1].iso_utc() == "2026-11-09T00:00:00Z"
        assert other_meta["dropped_unclosed"][0]["utc"] == "2026-11-10T00:00:00Z"
    poly = json.loads((ROOT / "data/cache/polymarket_prices_history_page1.json").read_text())
    points = parse_polymarket_prices(poly)
    assert len(points) == 912
    assert all(0 <= p["price"] <= 1 for p in points)
    summary = polymarket_summary()
    assert summary["raw_points"] == 912
    assert summary["points"] == 911
    assert summary["unclosed_point_count"] == 1
    assert summary["dropped_unclosed"][0]["reason"] == "terminal_tick_not_a_closed_bucket"
    assert summary["series"][-1]["resolution_seconds"] == 43200
    swaps = parse_pool_trades(json.loads((ROOT / "data/cache/gt_trades_head_EP2ib6dY.json").read_text()))
    assert swaps and all(row["pnl"] is None for row in swaps)
    scenarios = load_named_scenarios()
    result = run_dataset("wif_daily", scenarios["conservative_no_trade"])
    assert result.synthetic is False
    assert result.metrics["zero_trades"] is True
    assert result.metrics["trade_count"] == 0
    assert result.metrics["total_return"] == 0
    assert result.metrics["final_equity_usd"] == 10
    assert result.metrics["win_rate"] is None
    assert result.metrics["profit_factor"] is None
    merged = load_ohlcv_files(
        [
            ROOT / "data/cache/gt_ohlcv_day_before_EP2ib6dY.json",
            ROOT / "data/cache/gt_ohlcv_day_EP2ib6dY.json",
        ],
        86400,
    )
    assert len(merged.bars) == 363
    assert merged.dropped_unclosed[0]["utc"] == "2026-11-10T00:00:00Z"


def test_unclosed_bars_dropped_per_resolution(tmp_path: Path):
    day = 86400
    hour = 3600
    open_day = _unix("2026-11-09T00:00:00Z")
    next_day = _unix("2026-11-10T00:00:00Z")
    daily = _write_ohlcv(
        tmp_path,
        "day.json",
        [
            [next_day, 9, 9, 9, 9, 1],
            [open_day, 1, 1.2, 0.8, 1.1, 2],
        ],
        "2026-11-10T02:27:01Z",
    )
    loaded = load_ohlcv_files([daily], day)
    assert [bar.ts for bar in loaded.bars] == [open_day]
    assert loaded.dropped_unclosed[0]["reason"] == "unclosed_at_fetch"
    assert loaded.dropped_unclosed[0]["interval_seconds"] == day

    hour_closed = _unix("2026-11-10T01:00:00Z")
    hour_open = _unix("2026-11-10T02:00:00Z")
    hourly = _write_ohlcv(
        tmp_path,
        "hour.json",
        [
            [hour_open, 4, 4, 4, 4, 1],
            [hour_closed, 3, 3, 3, 3, 1],
        ],
        "2026-11-10T02:27:01Z",
    )
    hourly_load = load_ohlcv_files([hourly], hour)
    assert [bar.ts for bar in hourly_load.bars] == [hour_closed]
    assert hourly_load.dropped_unclosed[0]["ts"] == hour_open
    assert hourly_load.dropped_unclosed[0]["interval_seconds"] == hour

    exact = _write_ohlcv(
        tmp_path,
        "exact.json",
        [[hour_closed, 3, 3, 3, 3, 1]],
        "2026-11-10T02:00:00Z",
    )
    assert bar_is_closed(hour_closed, hour, _unix("2026-11-10T02:00:00Z")) is True
    assert [bar.ts for bar in load_ohlcv_files([exact], hour).bars] == [hour_closed]
    early = _write_ohlcv(
        tmp_path,
        "early.json",
        [[hour_closed, 3, 3, 3, 3, 1]],
        "2026-11-10T01:59:59Z",
    )
    assert load_ohlcv_files([early], hour).bars == []

    missing_meta = _write_ohlcv(tmp_path, "nometa.json", [[open_day, 1, 1, 1, 1, 1]], None)
    assert load_ohlcv_files([missing_meta], day).bars == []

    closed_later = _write_ohlcv(
        tmp_path,
        "later.json",
        [[next_day, 2, 2, 2, 2, 1]],
        "2026-11-11T00:00:00Z",
    )
    kept = load_ohlcv_files([daily, closed_later], day)
    assert next_day in {bar.ts for bar in kept.bars}
    assert kept.dropped_unclosed == []

    poisoned = _write_ohlcv(
        tmp_path,
        "poison.json",
        [
            [open_day, 1, 1.2, 0.8, 1.1, 2],
            [next_day, 1, 1, 1, 1_000_000, 1],
        ],
        "2026-11-10T02:27:01Z",
    )
    plain = _write_ohlcv(
        tmp_path,
        "plain.json",
        [[open_day, 1, 1.2, 0.8, 1.1, 2]],
        "2026-11-11T00:00:00Z",
    )
    poisoned_load = load_ohlcv_files([poisoned], day)
    plain_load = load_ohlcv_files([plain], day)
    assert rsi_wilder([bar.close for bar in poisoned_load.bars], 14) == rsi_wilder(
        [bar.close for bar in plain_load.bars], 14
    )


def test_paper_adapter_does_not_send_or_trade():
    bot = PaperReportAdapter(owner_ids=[7], paper_report="紙上")
    start = bot.handle_update({"message": {"text": "/start", "from": {"id": 7}}})
    assert start["sent"] is False and start["executed_order"] is False
    assert "不會授予" in start["reply"]
    denied = bot.handle_update({"message": {"text": "/report", "from": {"id": 9}}})
    assert denied["ok"] is False and denied["sent"] is False
    allowed = bot.handle_update({"message": {"text": "/report", "from": {"id": 7}}})
    assert allowed["sent"] is False and allowed["reply"] == "紙上"
    try:
        bot.send_message(7, "hi")
        raised = False
    except LiveSendDisabled:
        raised = True
    assert raised
    source = Path(ROOT / "src/ymzz_quant/tg_adapter.py").read_text(encoding="utf-8")
    assert "api.telegram.org" not in source
    assert "sendTransaction" not in source
