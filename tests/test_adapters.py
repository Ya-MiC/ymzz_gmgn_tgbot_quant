"""Public payload parsers and the real cached history. No fabricated prices."""

from __future__ import annotations

import json
from pathlib import Path

from ymzz_quant.catalog import ROOT
from ymzz_quant.data_adapters import load_ohlcv_files, parse_gt_ohlcv_payload, parse_polymarket_prices, parse_pool_trades
from ymzz_quant.service import load_bars, load_named_scenarios, run_dataset
from ymzz_quant.tg_adapter import LiveSendDisabled, PaperReportAdapter

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
    assert meta["bar_count"] == 364
    assert meta["gap_count"] == 0
    assert meta["duplicate_timestamps"] == 1
    assert bars[0].ts < bars[-1].ts
    assert all(b.high >= b.low and b.close > 0 for b in bars)
    sol_bars, sol_meta = load_bars("sol_usdc_daily")
    assert sol_meta["bar_count"] == 184
    assert sol_bars[0].ts < sol_bars[-1].ts
    poly = json.loads((ROOT / "data/cache/polymarket_prices_history_page1.json").read_text())
    points = parse_polymarket_prices(poly)
    assert len(points) == 912
    assert all(0 <= p["price"] <= 1 for p in points)
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
    assert len(merged.bars) == 364


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
