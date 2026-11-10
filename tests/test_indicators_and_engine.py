"""Deterministic indicator and execution tests. Synthetic prices are not real-market results."""

from __future__ import annotations

import copy

import pytest

from ymzz_quant.costs import CostScenario
from ymzz_quant.data_adapters import Bar
from ymzz_quant.engine import _settle_exit, run_backtest
from ymzz_quant.indicators import atr_percent, relative_volume, rsi_wilder
from ymzz_quant.splits import linear_quantile, split_labels


def test_rsi_hand_calculation_and_no_future_leak():
    closes = [10, 11, 10, 12]
    out = rsi_wilder(closes, period=2)
    assert out[0] is None and out[1] is None
    assert out[2] == pytest.approx(50.0)
    assert out[3] == pytest.approx(100 - 100 / 6)
    longer = closes + [100]
    again = rsi_wilder(longer, period=2)
    assert again[3] == pytest.approx(out[3])
    flat = [5.0] * 20
    rising = flat + [6.0]
    assert rsi_wilder(rising, 14)[-2] == pytest.approx(50.0)
    assert rsi_wilder([1, 2, 3, 4, 5] + [6] * 20, 14)[-1] == pytest.approx(100.0)


def test_atr_and_relative_volume_and_gap_reset():
    highs = [1, 2, 3, 4]
    lows = [0, 0, 1, 2]
    closes = [1, 2, 2.5, 3]
    atr = atr_percent(highs, lows, closes, period=2)
    assert atr[0] is None and atr[1] is None
    assert atr[2] == pytest.approx(0.8)
    volumes = [1, 2, 3, 4]
    rv = relative_volume(volumes, period=3)
    assert rv[1] is None
    assert rv[2] == pytest.approx(1.5)
    assert rv[3] == pytest.approx(4 / 3)
    stamps = [0, 86400, 86400 * 10, 86400 * 11, 86400 * 12]
    closes = [10, 11, 10, 12, 13]
    rsi = rsi_wilder(closes, period=2, timestamps=stamps, expected_seconds=86400)
    assert rsi[2] is None
    assert rsi[4] is not None


def test_train_quantile_ignores_heldout_mutation():
    stamps = [i * 86400 for i in range(40)]
    labels = split_labels(stamps)
    assert labels[0] == "train" and labels[-1] == "heldout"
    assert "validation" in labels
    values = [float(i) for i in range(40)]
    train_vals = [values[i] for i, lab in enumerate(labels) if lab == "train"]
    base = linear_quantile(train_vals, 0.2)
    poisoned = values[:]
    poisoned[-1] = 10_000
    train_poison = [poisoned[i] for i, lab in enumerate(labels) if lab == "train"]
    assert linear_quantile(train_poison, 0.2) == pytest.approx(base)


def _scenario(**overrides) -> CostScenario:
    raw = dict(
        name="toy",
        label_zh="合成測試",
        gmgn_fee_rate_per_side=0.01,
        pool_fee_rate_per_side=0.002,
        pool_fee_status="SYNTHETIC_EXPLICIT",
        chain_cost_sol_per_side=0.0,
        chain_cost_note="synthetic",
        slip_bp_buy=0.0,
        slip_bp_sell=0.0,
        slip_note="synthetic",
        wallet_reserve_sol=0.0,
        sol_usd=100.0,
        sol_usd_fetched_at_utc="n/a",
        sol_usd_fetched_at_kst="n/a",
        sol_usd_source="synthetic",
        initial_cash_usd=10.0,
        proposed_per_trade_loss_budget_usd=10.0,
        proposed_max_drawdown_frac=0.5,
        require_known_pool_fee=True,
        require_historical_sellability=False,
        require_historical_liquidity=False,
        historical_sellability_known=False,
        historical_liquidity_known=False,
        execution_mode="manual_tg_next_open",
        no_reentry=True,
        k_sl=1.5,
        k_tp=2.0,
        rsi_low=25,
        rsi_high=40,
        rsi_exit=70,
        rv_min=1.5,
        min_notional_usd=0.01,
    )
    raw.update(overrides)
    return CostScenario(**raw)


def _flat(n=40, price=100.0, volume=1_000.0):
    start = 1_700_000_000
    return [
        Bar(start + i * 86400, price, price + 1, price - 1, price, volume)
        for i in range(n)
    ]


def test_override_rejected_on_real_run():
    with pytest.raises(ValueError):
        run_backtest(_flat(5), _scenario(), "x", 86400, synthetic=False, synthetic_signal_override=[False] * 5)


def test_next_bar_fill_gap_and_manual_ignores_intrabar_extreme():
    bars = _flat()
    # Signal at 20, fill at 21. Close of 22 is through the stop; open of 23 gaps further.
    bars[22] = Bar(bars[22].ts, 100, 100, 50, 50, 1000)
    bars[23] = Bar(bars[23].ts, 40, 9_999, 1, 40, 1000)
    override = [False] * len(bars)
    override[20] = True
    result = run_backtest(
        bars,
        _scenario(),
        "synthetic",
        86400,
        synthetic=True,
        synthetic_signal_override=override,
    )
    closed = [t for t in result.trades if t["status"] == "CLOSED"]
    assert len(closed) == 1
    trade = closed[0]
    assert trade["entry_fill_index"] == 21
    assert trade["signal_index"] == 20
    assert trade["exit_fill_index"] == 23
    assert trade["exit_reason"] == "stop_on_close_next_open"
    assert trade["exit_fill_px"] == pytest.approx(40.0)
    assert trade["exit_fill_px"] < 90
    assert result.metrics["min_cash"] >= -1e-9
    assert result.metrics["min_equity"] >= -1e-9


def test_resting_same_bar_sl_before_tp_and_not_on_entry_bar():
    bars = _flat()
    bars[21] = Bar(bars[21].ts, 100, 9_999, 1, 100, 1000)
    bars[22] = Bar(bars[22].ts, 100, 130, 80, 100, 1000)
    override = [False] * len(bars)
    override[20] = True
    result = run_backtest(
        bars,
        _scenario(execution_mode="resting_stop_research", rsi_exit=101),
        "synthetic",
        86400,
        synthetic=True,
        synthetic_signal_override=override,
    )
    closed = [t for t in result.trades if t["status"] == "CLOSED"]
    assert len(closed) == 1
    trade = closed[0]
    assert trade["exit_fill_index"] == 22
    assert trade["same_bar_sl"] is True
    assert trade["exit_reason"] == "same_bar_sl_first"
    assert trade["exit_fill_px"] == pytest.approx(97.0)
    assert trade["entry_fill_index"] == 21


def test_resting_gap_fills_at_worse_open():
    bars = _flat()
    bars[22] = Bar(bars[22].ts, 80, 140, 70, 90, 1000)
    override = [False] * len(bars)
    override[20] = True
    result = run_backtest(
        bars,
        _scenario(execution_mode="resting_stop_research", rsi_exit=101),
        "synthetic",
        86400,
        synthetic=True,
        synthetic_signal_override=override,
    )
    trade = [t for t in result.trades if t["status"] == "CLOSED"][0]
    assert trade["exit_reason"] == "gap_through_stop_fill_at_open"
    assert trade["exit_fill_px"] == pytest.approx(80.0)


def test_round_trip_costs_and_chain_conversion_do_not_subtract_deposit_twice():
    bars = _flat()
    bars[22] = Bar(bars[22].ts, 100, 130, 99, 120, 1000)
    bars[23] = Bar(bars[23].ts, 110, 110, 109, 110, 1000)
    override = [False] * len(bars)
    override[20] = True
    scenario = _scenario(
        gmgn_fee_rate_per_side=0.01,
        pool_fee_rate_per_side=0.002,
        chain_cost_sol_per_side=0.002,
        sol_usd=50,
        rsi_exit=101,
        k_tp=2.0,
    )
    assert scenario.chain_fee_usd_per_side == pytest.approx(0.1)
    result = run_backtest(bars, scenario, "synthetic", 86400, synthetic=True, synthetic_signal_override=override)
    trade = [t for t in result.trades if t["status"] == "CLOSED"][0]
    qty = trade["qty"]
    entry_fill = trade["entry_fill_px"]
    exit_fill = trade["exit_fill_px"]
    assert entry_fill == pytest.approx(100)
    assert exit_fill == pytest.approx(110)
    debit = qty * entry_fill * (1 + 0.012) + 0.1
    credit = qty * exit_fill * (1 - 0.012) - 0.1
    assert trade["cost_basis"] == pytest.approx(debit)
    assert trade["exit_net"] == pytest.approx(credit)
    assert trade["realized_pnl"] == pytest.approx(credit - debit)
    assert trade["chain_fees"] == pytest.approx(0.2)
    assert trade["gmgn_fees"] == pytest.approx(qty * entry_fill * 0.01 + qty * exit_fill * 0.01)
    assert result.metrics["final_equity_usd"] == pytest.approx(10 + trade["realized_pnl"])
    assert result.metrics["final_equity_usd"] != pytest.approx(10 + trade["realized_pnl"] - 10)


def test_insufficient_ten_dollars_skips_and_drawdown_pause_and_no_reentry():
    bars = _flat()
    override = [False] * len(bars)
    override[20] = True
    poor = run_backtest(
        bars,
        _scenario(wallet_reserve_sol=0.05, sol_usd=300, chain_cost_sol_per_side=0.0),
        "synthetic",
        86400,
        synthetic=True,
        synthetic_signal_override=override,
    )
    assert poor.metrics["zero_trades"] is True
    assert poor.metrics["trade_count"] == 0
    assert poor.metrics["total_return"] == 0
    assert poor.metrics["win_rate"] is None
    assert poor.metrics["profit_factor"] is None
    assert poor.metrics["final_equity_usd"] == pytest.approx(10)
    assert "insufficient_funds_after_reserve" in poor.skips[0]["reasons"]

    costly = run_backtest(
        bars,
        _scenario(proposed_per_trade_loss_budget_usd=0.05, chain_cost_sol_per_side=0.002, sol_usd=100),
        "synthetic",
        86400,
        synthetic=True,
        synthetic_signal_override=override,
    )
    assert costly.metrics["zero_trades"] is True
    assert "cost_or_stop_exceeds_proposed_budget" in costly.skips[0]["reasons"]

    drop = _flat()
    drop[22] = Bar(drop[22].ts, 100, 100, 40, 40, 1000)
    drop[23] = Bar(drop[23].ts, 40, 40, 39, 40, 1000)
    signals = [False] * len(drop)
    signals[20] = True
    signals[30] = True
    paused = run_backtest(
        drop,
        _scenario(no_reentry=False, proposed_max_drawdown_frac=0.05, rsi_exit=101),
        "synthetic",
        86400,
        synthetic=True,
        synthetic_signal_override=signals,
    )
    assert paused.metrics["closed_trade_count"] == 1
    assert any("drawdown_pause" in s["reasons"] for s in paused.skips)
    assert paused.metrics["min_cash"] >= -1e-9

    again = [False] * len(bars)
    again[20] = True
    again[30] = True
    blocked = run_backtest(
        bars,
        _scenario(no_reentry=True, rsi_exit=0, proposed_max_drawdown_frac=0.5),
        "synthetic",
        86400,
        synthetic=True,
        synthetic_signal_override=again,
    )
    assert blocked.metrics["closed_trade_count"] == 1
    assert any("provisional_no_reentry" in s["reasons"] for s in blocked.skips)
    assert blocked.metrics["min_cash"] >= -1e-9


def test_costs_exceeding_cash_do_not_invent_sale_proceeds():
    bars = _flat(3)
    position = {
        "signal_index": 0,
        "signal_close": 100.0,
        "entry_fill_index": 1,
        "entry_open": 100.0,
        "entry_fill": 100.0,
        "qty": 1.0,
        "cost_basis": 5.0,
        "entry_fees": 0.0,
        "entry_chain": 0.0,
        "entry_gmgn": 0.0,
        "entry_pool": 0.0,
        "sl": 90.0,
        "tp": 110.0,
        "segment": "train",
        "atr_pct": 0.01,
        "dataset_key": "synthetic",
    }
    scenario = _scenario(chain_cost_sol_per_side=0.05, sol_usd=100, gmgn_fee_rate_per_side=0.0, pool_fee_rate_per_side=0.0)
    trade, cash, qty, realized, *_ = _settle_exit(
        bars=bars,
        fill_index=2,
        raw_price=1.0,
        reason="stop_on_close_next_open",
        signal_index=1,
        signal_close=1.0,
        scenario=scenario,
        cash=0.2,
        qty=1.0,
        position=position,
        same_bar_sl=False,
    )
    assert trade["status"] == "COSTS_EXCEED_CASH_MARKED_ZERO"
    assert cash == pytest.approx(0.2)
    assert qty == 0
    assert realized == pytest.approx(-5)
    assert trade["exit_fill_px"] is None


def test_end_of_data_stays_unrealized_and_unknown_pool_fee_blocks():
    bars = _flat()
    override = [False] * len(bars)
    override[20] = True
    held = run_backtest(
        bars,
        _scenario(rsi_exit=101, k_sl=0.01, k_tp=50),
        "synthetic",
        86400,
        synthetic=True,
        synthetic_signal_override=override,
    )
    assert held.metrics["open_trade_count"] == 1
    assert held.metrics["closed_trade_count"] == 0
    open_trade = held.trades[0]
    assert open_trade["status"] == "OPEN_UNREALIZED"
    assert open_trade["exit_fill_px"] is None
    assert held.metrics["unrealized_pnl"] != 0 or held.metrics["fees_paid_usd"] > 0

    blocked = run_backtest(
        bars,
        _scenario(pool_fee_rate_per_side=None, pool_fee_status="unknown"),
        "synthetic",
        86400,
        synthetic=True,
        synthetic_signal_override=override,
    )
    assert blocked.metrics["zero_trades"] is True
    assert "pool_fee_unknown" in blocked.skips[0]["reasons"]
    assert blocked.synthetic is True
