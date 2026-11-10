"""Single-position spot backtest. Fills are next-bar opens after a closed signal.

Manual Telegram mode does not use an intrabar stop. A resting-stop path exists
only as a labelled research mode. Nothing here talks to a wallet or a network.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from ymzz_quant.costs import CostScenario
from ymzz_quant.data_adapters import Bar, fmt_ts
from ymzz_quant.indicators import atr_percent, relative_volume, rsi_wilder
from ymzz_quant.margin import account_equity, financing_cost, leverage_allowed, margin_level, posted_and_borrowed
from ymzz_quant.splits import linear_quantile, split_bounds, split_labels


@dataclass
class RunResult:
    dataset_key: str
    scenario: dict
    bars_meta: dict
    split: dict
    frozen_atr_band: dict
    metrics: dict
    benchmarks: dict
    trades: list[dict]
    skips: list[dict]
    equity: list[dict]
    indicators: dict
    config_sha256: str
    synthetic: bool = False

    def to_dict(self) -> dict:
        return {
            "dataset_key": self.dataset_key,
            "scenario": self.scenario,
            "bars_meta": self.bars_meta,
            "split": self.split,
            "frozen_atr_band": self.frozen_atr_band,
            "metrics": self.metrics,
            "benchmarks": self.benchmarks,
            "trades": self.trades,
            "skips": self.skips,
            "equity": self.equity,
            "config_sha256": self.config_sha256,
            "synthetic": self.synthetic,
            "badge": "SIMULATED_PNL_ON_REAL_PRICES" if not self.synthetic else "SYNTHETIC_EXCLUDED_FROM_REAL_METRICS",
        }


def _validate_run_controls(scenario: CostScenario) -> None:
    if not 0 < scenario.initial_cash_usd <= 10 + 1e-9:
        raise ValueError("initial cash must be positive and at most $10")
    if scenario.proposed_per_trade_loss_budget_usd <= 0:
        raise ValueError("loss budget must be positive")
    if scenario.proposed_per_trade_loss_budget_usd > scenario.initial_cash_usd + 1e-9:
        raise ValueError("loss budget cannot exceed equity")
    if scenario.proposed_max_drawdown_usd is not None and scenario.proposed_max_drawdown_usd > scenario.initial_cash_usd + 1e-9:
        raise ValueError("drawdown proposal cannot exceed equity")
    if scenario.proposed_max_drawdown_frac <= 0 or scenario.proposed_max_drawdown_frac > 1:
        raise ValueError("drawdown fraction must be inside (0, 1]")
    if scenario.execution_delay_bars < 1:
        raise ValueError("execution delay must be at least 1 closed bar")
    if min(scenario.rsi_period, scenario.atr_period, scenario.rv_period) < 2:
        raise ValueError("indicator period")
    if scenario.instrument_mode not in {"spot", "hypothetical_assumed_margin"}:
        raise ValueError("instrument_mode")
    if scenario.leverage > 2 + 1e-12 or scenario.leverage <= 0 or not leverage_allowed(scenario.leverage):
        raise ValueError("paper leverage must be 1, 1.5, or 2; values above 2 are rejected")
    if scenario.instrument_mode == "spot" and abs(scenario.leverage - 1.0) > 1e-9:
        raise ValueError(
            "spot and GMGN swap have no native margin; leverage must stay 1. "
            "hypothetical_assumed_margin is a separate assumed scenario, not a real perpetual backtest."
        )


def run_backtest(
    bars: list[Bar],
    scenario: CostScenario,
    dataset_key: str,
    expected_interval: int,
    synthetic: bool = False,
    dataset_meta: dict | None = None,
    synthetic_signal_override: list[bool] | None = None,
) -> RunResult:
    if synthetic_signal_override is not None and not synthetic:
        raise ValueError("synthetic_signal_override is excluded from real-market runs")
    _validate_run_controls(scenario)
    if scenario.execution_mode not in {"manual_tg_next_open", "resting_stop_research"}:
        raise ValueError("execution mode")
    n = len(bars)
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    volumes = [b.volume for b in bars]
    stamps = [b.ts for b in bars]
    rsi = rsi_wilder(closes, scenario.rsi_period, stamps, expected_interval)
    atr = atr_percent(highs, lows, closes, scenario.atr_period, stamps, expected_interval)
    rv = relative_volume(volumes, scenario.rv_period, stamps, expected_interval)
    labels = split_labels(stamps) if stamps else []
    bounds = split_bounds(stamps) if stamps else {}
    train_atr = [atr[i] for i, lab in enumerate(labels) if lab == "train" and atr[i] is not None]
    atr_lo = linear_quantile(train_atr, scenario.atr_quantile_low)
    atr_hi = linear_quantile(train_atr, scenario.atr_quantile_high)
    frozen = {
        "low": atr_lo,
        "high": atr_hi,
        "train_samples": len(train_atr),
        "quantile_low": scenario.atr_quantile_low,
        "quantile_high": scenario.atr_quantile_high,
        "fit_on": "train_only",
    }

    cash = float(scenario.initial_cash_usd)
    qty = 0.0
    position = None
    pending = None
    exited_once = False
    peak = cash
    dd_paused = False
    trades: list[dict] = []
    skips: list[dict] = []
    equity: list[dict] = []
    realized = 0.0
    fees_paid = 0.0
    chain_paid = 0.0
    clamp_events = 0
    financing_paid = 0.0

    def borrowed_now() -> float:
        return float(position["borrowed"]) if position else 0.0

    def mark(i: int) -> float:
        return account_equity(cash, qty, closes[i], borrowed_now())

    def record_equity(i: int) -> None:
        nonlocal peak, dd_paused
        eq = mark(i)
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd >= scenario.proposed_max_drawdown_frac - 1e-15:
            dd_paused = True
        equity.append(
            {
                **fmt_ts(bars[i].ts),
                "equity": eq,
                "cash": cash,
                "qty": qty,
                "close": closes[i],
                "drawdown": dd,
                "drawdown_paused": dd_paused,
                "segment": labels[i],
                "unrealized": (qty * closes[i] - position["cost_basis"]) if position else 0.0,
            }
        )

    for i in range(n):
        if pending and pending["fill_index"] == i:
            if pending["side"] == "buy":
                cash, bought_qty, position, aborted = _execute_buy(
                    i, bars, pending, scenario, cash, dataset_key, labels
                )
                if not aborted:
                    qty = bought_qty
                if aborted:
                    skips.append(aborted)
                    pending = None
                else:
                    fees_paid += position["entry_fees"]
                    chain_paid += position["entry_chain"]
                    pending = None
            else:
                trade, cash, qty, realized_delta, fee_delta, chain_delta, clamped = _execute_sell(
                    bars, i, pending, scenario, cash, qty, position
                )
                fees_paid += fee_delta
                chain_paid += chain_delta
                realized += realized_delta
                if clamped:
                    clamp_events += 1
                trades.append(trade)
                position = None
                qty = 0.0
                exited_once = True
                pending = None

        if (
            scenario.execution_mode == "resting_stop_research"
            and position is not None
            and qty > 0
            and i > position["entry_fill_index"]
        ):
            resting = _resting_exit(i, bars, position, scenario)
            if resting is not None:
                trade, cash, qty, realized_delta, fee_delta, chain_delta, clamped = _settle_exit(
                    bars=bars,
                    fill_index=i,
                    raw_price=resting["raw"],
                    reason=resting["reason"],
                    signal_index=i,
                    signal_close=closes[i - 1] if i else closes[i],
                    scenario=scenario,
                    cash=cash,
                    qty=qty,
                    position=position,
                    same_bar_sl=resting["same_bar_sl"],
                )
                fees_paid += fee_delta
                chain_paid += chain_delta
                realized += realized_delta
                if clamped:
                    clamp_events += 1
                trades.append(trade)
                position = None
                qty = 0.0
                exited_once = True
                pending = None

        if (
            position is not None
            and scenario.instrument_mode == "hypothetical_assumed_margin"
            and i >= position["entry_fill_index"]
        ):
            cost = financing_cost(
                position["borrowed"],
                qty * closes[i],
                scenario.assumed_borrow_rate_per_day,
                scenario.assumed_funding_rate_per_day,
                expected_interval,
            )
            if cost > 0:
                if cash >= cost:
                    cash -= cost
                else:
                    position["borrowed"] += cost - max(cash, 0.0)
                    cash = 0.0
                financing_paid += cost
                position["financing"] = position.get("financing", 0.0) + cost

        record_equity(i)

        if i + scenario.execution_delay_bars >= n:
            continue

        if (
            position is not None
            and pending is None
            and scenario.instrument_mode == "hypothetical_assumed_margin"
            and i > position["entry_fill_index"]
        ):
            level = margin_level(cash, qty, closes[i], position["borrowed"])
            if level is not None and level <= scenario.maintenance_margin_frac + 1e-15:
                pending = {
                    "side": "sell",
                    "fill_index": i + scenario.execution_delay_bars,
                    "signal_index": i,
                    "signal_close": closes[i],
                    "reason": "hypothetical_liquidation_next_open",
                    "same_bar_sl": False,
                    "liquidation": True,
                }

        if position is not None and pending is None and scenario.execution_mode == "manual_tg_next_open":
            reason = _manual_exit_reason(closes[i], position, rsi[i], scenario)
            if reason:
                pending = {
                    "side": "sell",
                    "fill_index": i + scenario.execution_delay_bars,
                    "signal_index": i,
                    "signal_close": closes[i],
                    "reason": reason,
                    "same_bar_sl": False,
                }

        if position is None and pending is None:
            if synthetic_signal_override is not None:
                signal = bool(synthetic_signal_override[i]) and atr[i] is not None
            else:
                signal = _alpha_signal(rsi[i], atr[i], rv[i], scenario, atr_lo, atr_hi)
            if signal:
                blocks = _blocks(
                    scenario,
                    dd_paused=dd_paused,
                    exited_once=exited_once,
                    atr_ready=atr_lo is not None and atr_hi is not None,
                )
                size = _size_notional(scenario, cash, atr[i])
                if size["notional"] < scenario.min_notional_usd and size["reason"] not in blocks:
                    blocks.append(size["reason"])
                if blocks:
                    skips.append(
                        {
                            **fmt_ts(bars[i].ts),
                            "segment": labels[i],
                            "reasons": blocks,
                            "rsi": rsi[i],
                            "atr_pct": atr[i],
                            "rv": rv[i],
                        }
                    )
                else:
                    plan_px = closes[i] * (1 + scenario.slip_bp_buy / 10000)
                    qty_plan = size["notional"] / plan_px
                    pending = {
                        "side": "buy",
                        "fill_index": i + scenario.execution_delay_bars,
                        "signal_index": i,
                        "signal_close": closes[i],
                        "qty": qty_plan,
                        "atr_pct": atr[i],
                        "segment": labels[i],
                        "reason": "alpha_entry",
                    }

    open_unrealized = None
    if position is not None:
        last = n - 1
        mtm = account_equity(cash, qty, closes[last], position["borrowed"]) - cash
        open_unrealized = {
            "status": "OPEN_UNREALIZED",
            "entry_signal_utc": fmt_ts(bars[position["signal_index"]].ts)["utc"],
            "entry_signal_kst": fmt_ts(bars[position["signal_index"]].ts)["kst"],
            "entry_fill_utc": fmt_ts(bars[position["entry_fill_index"]].ts)["utc"],
            "entry_fill_kst": fmt_ts(bars[position["entry_fill_index"]].ts)["kst"],
            "entry_signal_close": position["signal_close"],
            "entry_open": position["entry_open"],
            "entry_fill_px": position["entry_fill"],
            "entry_residual": position["entry_fill"] - position["signal_close"],
            "qty": qty,
            "cost_basis": position["cost_basis"],
            "mark_close": closes[last],
            "mark_value": mtm,
            "unrealized_pnl": mtm - position["cost_basis"],
            "realized_pnl": None,
            "exit_fill_px": None,
            "exit_reason": None,
            "gmgn_fees": position["entry_gmgn"],
            "pool_fees": position["entry_pool"],
            "chain_fees": position["entry_chain"],
            "same_bar_sl": False,
            "note": "資料結束仍持倉。收盤市值是未實現評價，不是成交，也不保證能賣出。",
            "segment": position["segment"],
            "dataset_key": dataset_key,
            "signal_index": position["signal_index"],
            "entry_fill_index": position["entry_fill_index"],
            "exit_fill_index": None,
            "pool_fee_is_assumed": scenario.pool_fee_is_assumed,
            "execution_limitation": "OHLCV 不能證明可賣出；期末市值不是成交價。",
        }
        trades.append(open_unrealized)

    final_equity = equity[-1]["equity"] if equity else cash
    max_dd = max((row["drawdown"] for row in equity), default=0.0)
    closed = [t for t in trades if t.get("status") == "CLOSED"]
    wins = [t for t in closed if t["realized_pnl"] > 0]
    losses = [t for t in closed if t["realized_pnl"] < 0]
    gross_profit = sum(t["realized_pnl"] for t in wins)
    gross_loss = -sum(t["realized_pnl"] for t in losses)
    zero = len(trades) == 0
    if zero:
        total_return = 0.0
        win_rate = None
        profit_factor = None
    else:
        total_return = final_equity / scenario.initial_cash_usd - 1
        win_rate = (len(wins) / len(closed)) if closed else None
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 and closed else None

    metrics = {
        "initial_cash_usd": scenario.initial_cash_usd,
        "final_equity_usd": final_equity,
        "total_return": total_return,
        "realized_pnl": realized,
        "unrealized_pnl": open_unrealized["unrealized_pnl"] if open_unrealized else 0.0,
        "max_drawdown": max_dd,
        "max_drawdown_is_close_marked": True,
        "sample_bars": n,
        "trade_count": len(trades),
        "closed_trade_count": len(closed),
        "open_trade_count": 1 if open_unrealized else 0,
        "signal_blocked_count": len(skips),
        "fees_paid_usd": fees_paid,
        "chain_fees_paid_usd": chain_paid,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "win_rate_defined": win_rate is not None,
        "profit_factor_defined": profit_factor is not None,
        "zero_trades": zero,
        "zero_trade_note": "沒有成交。報酬記為 0，不把空結果說成獲利。" if zero else None,
        "balance_clamp_events": clamp_events,
        "min_cash": min((row["cash"] for row in equity), default=cash),
        "min_equity": min((row["equity"] for row in equity), default=final_equity),
        "leverage_used": scenario.leverage if scenario.instrument_mode == "hypothetical_assumed_margin" else 1.0,
        "instrument_mode": scenario.instrument_mode,
        "assumed_financing_usd": financing_paid,
        "hypothetical_margin_is_real_perp": False,
        "rsi_period": scenario.rsi_period,
        "atr_period": scenario.atr_period,
        "rv_period": scenario.rv_period,
        "execution_delay_bars": scenario.execution_delay_bars,
        "same_bar_sl_first_count": sum(1 for t in closed if t.get("same_bar_sl")),
        "execution_residual_entry_mean": _mean([t["entry_residual"] for t in trades if "entry_residual" in t]),
        "execution_residual_exit_mean": _mean([t["exit_residual"] for t in closed if t.get("exit_residual") is not None]),
        "proposed_controls_not_user_specified": not scenario.request_controls_are_user_supplied,
        "train_trade_count": sum(1 for t in trades if t.get("segment") == "train"),
        "validation_trade_count": sum(1 for t in trades if t.get("segment") == "validation"),
        "heldout_trade_count": sum(1 for t in trades if t.get("segment") == "heldout"),
        "exit_fixed_fee_covered_by_entry_cash": scenario.reserve_usd + 1e-9 >= scenario.chain_fee_usd_per_side,
    }
    benchmarks = {
        "cash": {"final_equity_usd": scenario.initial_cash_usd, "total_return": 0.0, "max_drawdown": 0.0},
        "buy_and_hold": _buy_and_hold(bars, scenario, atr, labels),
    }
    public_scenario = scenario.to_public_dict()
    payload = {
        "scenario": public_scenario,
        "frozen_atr_band": frozen,
        "dataset_key": dataset_key,
        "synthetic": synthetic,
    }
    config_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    last_open = stamps[-1] if stamps else None
    meta = {
        "bars": n,
        "gaps": (dataset_meta or {}).get("gaps", []),
        "start": fmt_ts(stamps[0]) if stamps else None,
        "end": fmt_ts(last_open) if last_open is not None else None,
        "end_close": fmt_ts(last_open + expected_interval) if last_open is not None else None,
        "bar_time_is": "open_of_closed_candle",
        "partial_bars_included": False,
        "unclosed_bar_count": int((dataset_meta or {}).get("unclosed_bar_count") or 0),
        "expected_interval_seconds": expected_interval,
        "sha256": (dataset_meta or {}).get("sha256"),
        "sources": (dataset_meta or {}).get("sources"),
        "dataset": dataset_meta or {},
    }
    return RunResult(
        dataset_key=dataset_key,
        scenario=public_scenario,
        bars_meta=meta,
        split={**bounds, "counts": {name: labels.count(name) for name in ("train", "validation", "heldout")}},
        frozen_atr_band=frozen,
        metrics=metrics,
        benchmarks=benchmarks,
        trades=trades,
        skips=skips,
        equity=equity,
        indicators={"rsi": rsi, "atr_pct": atr, "rv": rv, "segment": labels},
        config_sha256=config_hash,
        synthetic=synthetic,
    )


def _alpha_signal(rsi, atr, rv, scenario: CostScenario, atr_lo, atr_hi) -> bool:
    if rsi is None or atr is None or rv is None or atr_lo is None or atr_hi is None:
        return False
    if not (scenario.rsi_low <= rsi <= scenario.rsi_high):
        return False
    if rv < scenario.rv_min:
        return False
    if not (atr_lo <= atr <= atr_hi):
        return False
    if scenario.k_sl * atr >= 1:
        return False
    return True


def _blocks(scenario: CostScenario, dd_paused: bool, exited_once: bool, atr_ready: bool) -> list[str]:
    reasons = []
    if not atr_ready:
        reasons.append("atr_threshold_unavailable")
    if scenario.require_historical_sellability and not scenario.historical_sellability_known:
        reasons.append("sellability_unknown")
    if scenario.require_historical_liquidity and not scenario.historical_liquidity_known:
        reasons.append("liquidity_history_unknown")
    if scenario.require_known_pool_fee and scenario.pool_fee_rate_per_side is None:
        reasons.append("pool_fee_unknown")
    if dd_paused:
        reasons.append("drawdown_pause")
    if scenario.no_reentry and exited_once:
        reasons.append("provisional_no_reentry")
    return reasons


def _size_notional(scenario: CostScenario, cash: float, atr_pct: float) -> dict:
    pool = scenario.pool_fee_rate_per_side
    if pool is None:
        return {"notional": 0.0, "reason": "pool_fee_unknown"}
    chain = scenario.chain_fee_usd_per_side
    buy_var = scenario.gmgn_fee_rate_per_side + pool
    sell_var = buy_var
    slip = (scenario.slip_bp_buy + scenario.slip_bp_sell) / 10000
    stop = scenario.k_sl * atr_pct
    denom = stop + slip + buy_var + sell_var
    budget = scenario.proposed_per_trade_loss_budget_usd
    if denom <= 0 or budget <= 2 * chain:
        return {"notional": 0.0, "reason": "cost_or_stop_exceeds_proposed_budget"}
    by_budget = (budget - 2 * chain) / denom
    buying = cash - scenario.reserve_usd
    if buying <= chain:
        return {"notional": 0.0, "reason": "insufficient_funds_after_reserve"}
    leverage = scenario.leverage if scenario.instrument_mode == "hypothetical_assumed_margin" else 1.0
    by_cash = (buying - chain) / ((1.0 / leverage) + buy_var)
    notional = min(by_budget, by_cash)
    if notional < scenario.min_notional_usd:
        reason = "cost_or_stop_exceeds_proposed_budget" if by_budget <= by_cash else "insufficient_funds_after_reserve"
        return {"notional": notional, "reason": reason}
    return {"notional": notional, "reason": None}


def _execute_buy(i, bars, pending, scenario: CostScenario, cash, dataset_key, labels):
    if scenario.pool_fee_rate_per_side is None:
        return cash, 0.0, None, {
            **fmt_ts(bars[i].ts),
            "segment": labels[i],
            "reasons": ["pool_fee_unknown"],
            "rsi": None,
            "atr_pct": pending["atr_pct"],
            "rv": None,
        }
    raw = bars[i].open
    fill = raw * (1 + scenario.slip_bp_buy / 10000)
    qty = pending["qty"]
    pool = scenario.pool_fee_rate_per_side
    notional = qty * fill
    gmgn = notional * scenario.gmgn_fee_rate_per_side
    pool_fee = notional * pool
    chain = scenario.chain_fee_usd_per_side
    leverage = scenario.leverage if scenario.instrument_mode == "hypothetical_assumed_margin" else 1.0
    posted, borrowed = posted_and_borrowed(notional, leverage)
    debit = posted + gmgn + pool_fee + chain
    if debit > cash + 1e-9 or cash - debit < scenario.reserve_usd - 1e-6:
        return cash, 0.0, None, {
            **fmt_ts(bars[i].ts),
            "segment": labels[i],
            "reasons": ["fill_aborted_insufficient_cash"],
            "rsi": None,
            "atr_pct": pending["atr_pct"],
            "rv": None,
        }
    cash_before_entry = cash
    cash -= debit
    sl = fill * (1 - scenario.k_sl * pending["atr_pct"])
    tp = fill * (1 + scenario.k_tp * pending["atr_pct"])
    position = {
        "signal_index": pending["signal_index"],
        "signal_close": pending["signal_close"],
        "entry_fill_index": i,
        "entry_open": raw,
        "entry_fill": fill,
        "qty": qty,
        "cost_basis": debit,
        "notional": notional,
        "posted_cash": posted,
        "borrowed": borrowed,
        "leverage": leverage,
        "cash_before_entry": cash_before_entry,
        "financing": 0.0,
        "entry_fees": gmgn + pool_fee,
        "entry_chain": chain,
        "entry_gmgn": gmgn,
        "entry_pool": pool_fee,
        "sl": sl,
        "tp": tp,
        "segment": pending["segment"],
        "atr_pct": pending["atr_pct"],
        "dataset_key": dataset_key,
    }
    return cash, qty, position, None


def _manual_exit_reason(close, position, rsi, scenario: CostScenario):
    """Close-only. The bar high and low are not execution prices in this mode."""
    if close <= position["sl"]:
        return "stop_on_close_next_open"
    if close >= position["tp"]:
        return "take_profit_on_close_next_open"
    if rsi is not None and rsi >= scenario.rsi_exit:
        return "rsi_exit_next_open"
    return None


def _resting_exit(i, bars, position, scenario: CostScenario):
    bar = bars[i]
    sl = position["sl"]
    tp = position["tp"]
    if bar.open <= sl:
        return {"raw": bar.open, "reason": "gap_through_stop_fill_at_open", "same_bar_sl": False}
    hit_sl = bar.low <= sl
    hit_tp = bar.high >= tp
    if hit_sl and hit_tp:
        return {"raw": sl, "reason": "same_bar_sl_first", "same_bar_sl": True}
    if hit_sl:
        return {"raw": sl, "reason": "resting_stop", "same_bar_sl": False}
    if hit_tp:
        return {"raw": tp, "reason": "resting_take_profit", "same_bar_sl": False}
    return None


def _execute_sell(bars, i, pending, scenario, cash, qty, position):
    raw = bars[i].open
    if pending.get("liquidation"):
        raw = raw * (1 - scenario.liquidation_penalty_frac)
    return _settle_exit(
        bars=bars,
        fill_index=i,
        raw_price=raw,
        reason=pending["reason"],
        signal_index=pending["signal_index"],
        signal_close=pending["signal_close"],
        scenario=scenario,
        cash=cash,
        qty=qty,
        position=position,
        same_bar_sl=pending.get("same_bar_sl", False),
    )


def _settle_exit(bars, fill_index, raw_price, reason, signal_index, signal_close, scenario, cash, qty, position, same_bar_sl):
    if scenario.pool_fee_rate_per_side is None:
        raise RuntimeError("refusing to book a sell with a silent zero pool fee")
    fill = raw_price * (1 - scenario.slip_bp_sell / 10000)
    pool = scenario.pool_fee_rate_per_side
    gross = qty * fill
    gmgn = gross * scenario.gmgn_fee_rate_per_side
    pool_fee = gross * pool
    chain = scenario.chain_fee_usd_per_side
    net = gross - gmgn - pool_fee - chain
    borrowed = float(position.get("borrowed") or 0.0)
    clamped = False
    status = "CLOSED"
    note = "OHLCV 不能證明可賣出；成交價是模型，不是保證。"
    if reason == "hypothetical_liquidation_next_open":
        status = "HYPOTHETICAL_LIQUIDATION"
        note = "假設保證金模擬的強制平倉。不是交易所永續合約的真實強平，也沒有補倉。"
    if borrowed == 0 and cash + net < -1e-9:
        # Paying the modeled exit would make cash negative. Do not invent proceeds.
        clamped = True
        status = "COSTS_EXCEED_CASH_MARKED_ZERO"
        net = 0.0
        gmgn = 0.0
        pool_fee = 0.0
        chain = 0.0
        fill_booked = None
        realized = -position["cost_basis"]
        note = "模型出場成本超過持有現金。不記虛構賣出收入，倉位回收價值記 0。這不是可賣性證明。"
    else:
        new_cash = cash + net - borrowed
        if new_cash < -1e-9:
            clamped = True
            status = "BANKRUPTCY_FLOOR_NO_TOPUP"
            note = "假設保證金模擬在還款後現金會小於 0。現金記 0，沒有外部補倉。"
            cash = 0.0
            fill_booked = fill
        else:
            cash = new_cash
            fill_booked = fill
        if position.get("cash_before_entry") is not None:
            realized = cash - position["cash_before_entry"]
        else:
            realized = net - borrowed - position["cost_basis"]
    entry_signal = fmt_ts(bars[position["signal_index"]].ts)
    entry_fill_ts = fmt_ts(bars[position["entry_fill_index"]].ts)
    exit_signal = fmt_ts(bars[signal_index].ts)
    exit_fill_ts = fmt_ts(bars[fill_index].ts)
    trade = {
        "status": status,
        "entry_signal_utc": entry_signal["utc"],
        "entry_signal_kst": entry_signal["kst"],
        "entry_fill_utc": entry_fill_ts["utc"],
        "entry_fill_kst": entry_fill_ts["kst"],
        "exit_signal_utc": exit_signal["utc"],
        "exit_signal_kst": exit_signal["kst"],
        "exit_fill_utc": exit_fill_ts["utc"],
        "exit_fill_kst": exit_fill_ts["kst"],
        "exit_reason": reason,
        "exit_signal_close": signal_close,
        "exit_raw_price": raw_price,
        "exit_fill_px": fill_booked,
        "qty": qty,
        "entry_signal_close": position["signal_close"],
        "entry_open": position["entry_open"],
        "entry_fill_px": position["entry_fill"],
        "entry_residual": position["entry_fill"] - position["signal_close"],
        "exit_residual": None if fill_booked is None else signal_close - fill_booked,
        "cost_basis": position["cost_basis"],
        "exit_net": net,
        "realized_pnl": realized,
        "gmgn_fees": position["entry_gmgn"] + gmgn,
        "pool_fees": position["entry_pool"] + pool_fee,
        "chain_fees": position["entry_chain"] + chain,
        "same_bar_sl": same_bar_sl,
        "segment": position["segment"],
        "balance_clamped": clamped,
        "pool_fee_is_assumed": scenario.pool_fee_is_assumed,
        "execution_limitation": note,
        "signal_index": position["signal_index"],
        "entry_fill_index": position["entry_fill_index"],
        "exit_signal_index": signal_index,
        "exit_fill_index": fill_index,
        "dataset_key": position["dataset_key"],
    }
    return trade, cash, 0.0, realized, gmgn + pool_fee, chain, clamped


def _buy_and_hold(bars: list[Bar], scenario: CostScenario, atr, labels) -> dict:
    if scenario.pool_fee_rate_per_side is None or len(bars) < 3:
        return {"status": "skipped", "reason": "pool_fee_unknown_or_short_series", "final_equity_usd": None}
    # First index where ATR exists, fill on the following open, hold to the last close.
    entry_signal = next((i for i, v in enumerate(atr) if v is not None and i < len(bars) - 1), None)
    if entry_signal is None:
        return {"status": "skipped", "reason": "no_warmup_complete", "final_equity_usd": None}
    del labels
    pool = scenario.pool_fee_rate_per_side
    chain = scenario.chain_fee_usd_per_side
    buy_var = scenario.gmgn_fee_rate_per_side + pool
    buying = scenario.initial_cash_usd - scenario.reserve_usd
    if buying <= chain:
        return {"status": "skipped", "reason": "insufficient_funds_after_reserve", "final_equity_usd": scenario.initial_cash_usd}
    notional = (buying - chain) / (1 + buy_var)
    fill_i = entry_signal + 1
    raw = bars[fill_i].open
    fill = raw * (1 + scenario.slip_bp_buy / 10000)
    qty = notional / (bars[entry_signal].close * (1 + scenario.slip_bp_buy / 10000))
    debit = qty * fill * (1 + buy_var) + chain
    cash = scenario.initial_cash_usd
    if debit > cash or cash - debit < scenario.reserve_usd - 1e-6:
        qty = max(0.0, (cash - scenario.reserve_usd - chain) / (fill * (1 + buy_var)))
        debit = qty * fill * (1 + buy_var) + chain
    if qty <= 0 or debit > cash:
        return {"status": "skipped", "reason": "insufficient_funds_after_reserve", "final_equity_usd": cash}
    cash -= debit
    final = cash + qty * bars[-1].close
    peak = scenario.initial_cash_usd
    max_dd = 0.0
    eq = scenario.initial_cash_usd
    for i in range(len(bars)):
        if i < fill_i:
            eq = scenario.initial_cash_usd
        else:
            eq = cash + qty * bars[i].close
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)
    return {
        "status": "marked_unrealized_at_end",
        "note": "買入後持有到最後收盤。期末是未實現市值，未扣賣出費用，不是成交。",
        "final_equity_usd": final,
        "total_return": final / scenario.initial_cash_usd - 1,
        "max_drawdown": max_dd,
        "entry_fill_ts": bars[fill_i].ts,
        "fees_ignored_on_exit": True,
    }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)
