"""Load cached public data and run the paper engine. No network calls."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from ymzz_quant.catalog import DATASETS, ROOT, dataset_paths
from ymzz_quant.costs import CostScenario, load_scenarios
from ymzz_quant.data_adapters import load_ohlcv_files, parse_polymarket_prices, parse_pool_trades
from ymzz_quant.engine import RunResult, run_backtest
from ymzz_quant.indicators import rsi_wilder

CONFIG = ROOT / "config" / "scenarios.json"


def load_bars(dataset_key: str, root: Path | None = None):
    root = root or ROOT
    spec = DATASETS[dataset_key]
    loaded = load_ohlcv_files(dataset_paths(dataset_key, root), spec["expected_interval_seconds"])
    meta = {
        **spec,
        "gaps": loaded.gaps,
        "gap_count": len(loaded.gaps),
        "sha256": loaded.sha256,
        "sources": [str(Path(s).relative_to(root)) if str(s).startswith(str(root)) else s for s in loaded.sources],
        "invalid_bars": loaded.invalid_bars,
        "duplicate_timestamps": loaded.duplicate_timestamps,
        "bar_count": len(loaded.bars),
    }
    return loaded.bars, meta


def run_dataset(dataset_key: str, scenario: CostScenario, root: Path | None = None) -> RunResult:
    bars, meta = load_bars(dataset_key, root)
    return run_backtest(
        bars,
        scenario,
        dataset_key,
        meta["expected_interval_seconds"],
        synthetic=False,
        dataset_meta=meta,
    )


def load_named_scenarios(root: Path | None = None) -> dict[str, CostScenario]:
    root = root or ROOT
    return load_scenarios(root / "config" / "scenarios.json", root)


def sensitivity(dataset_key: str, base: CostScenario, root: Path | None = None) -> list[dict]:
    """Fee grid. Pool fee null must not be treated as zero."""
    rows = []
    for chain in (0.002, 0.005, 0.006):
        for pool, status in (
            (None, "unknown_geckoterminal_pool_fee_percentage_null"),
            (0.003, "ASSUMED_because_geckoterminal_pool_fee_percentage_was_null"),
            (0.01, "ASSUMED_stress_1pct_pool_fee_not_verified"),
        ):
            scenario = replace(
                base,
                name=f"sensitivity_chain_{chain}_pool_{pool}",
                chain_cost_sol_per_side=chain,
                pool_fee_rate_per_side=pool,
                pool_fee_status=status,
                require_known_pool_fee=True,
                require_historical_sellability=False,
                require_historical_liquidity=False,
            )
            result = run_dataset(dataset_key, scenario, root)
            rows.append(
                {
                    "chain_cost_sol_per_side": chain,
                    "chain_fee_usd_per_side": scenario.chain_fee_usd_per_side,
                    "pool_fee_rate_per_side": pool,
                    "pool_fee_status": status,
                    "trade_count": result.metrics["trade_count"],
                    "zero_trades": result.metrics["zero_trades"],
                    "final_equity_usd": result.metrics["final_equity_usd"],
                    "total_return": result.metrics["total_return"],
                    "max_drawdown": result.metrics["max_drawdown"],
                    "fees_paid_usd": result.metrics["fees_paid_usd"],
                    "chain_fees_paid_usd": result.metrics["chain_fees_paid_usd"],
                    "signal_blocked_count": result.metrics["signal_blocked_count"],
                }
            )
    return rows


def polymarket_summary(root: Path | None = None) -> dict:
    root = root or ROOT
    path = root / "data" / "cache" / "polymarket_prices_history_page1.json"
    ref_path = root / "data" / "cache" / "polymarket_market_ref.json"
    if not path.exists():
        return {"available": False, "reason": "no polymarket cache"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    points = parse_polymarket_prices(payload)
    ref = json.loads(ref_path.read_text(encoding="utf-8")) if ref_path.exists() else {}
    prices = [p["price"] for p in points]
    closes = prices
    prob_rsi = rsi_wilder(closes, 14) if len(closes) > 20 else []
    return {
        "available": True,
        "pnl_backtest": False,
        "bankroll_merged_with_meme": False,
        "unit": "probability_0_to_1",
        "question": ref.get("question"),
        "condition_id": ref.get("condition_id"),
        "token_id_yes": ref.get("token_id_yes"),
        "selection_bias": ref.get("selection"),
        "fetched_at_utc": ref.get("fetched_at_utc"),
        "fetched_at_kst": ref.get("fetched_at_kst"),
        "points": len(points),
        "start_ts": points[0]["timestamp"] if points else None,
        "end_ts": points[-1]["timestamp"] if points else None,
        "min_price": min(prices) if prices else None,
        "max_price": max(prices) if prices else None,
        "last_price": prices[-1] if prices else None,
        "has_more": (payload.get("pagination") or {}).get("has_more"),
        "prob_rsi_last": next((v for v in reversed(prob_rsi) if v is not None), None) if prob_rsi else None,
        "note": "機率不是代幣美元報酬。此處只檢視，不與 $10 meme 帳戶合併，也不用代幣 RSI 規則下單。",
        "series": points,
    }


def recent_swaps(root: Path | None = None, limit: int = 8) -> dict:
    root = root or ROOT
    path = root / "data" / "cache" / "gt_trades_head_EP2ib6dY.json"
    if not path.exists():
        return {"available": False, "reason": "no public swap cache", "rows": []}
    rows = parse_pool_trades(json.loads(path.read_text(encoding="utf-8")))
    return {
        "available": True,
        "count_in_file": len(rows),
        "rows": rows[:limit],
        "note": "GeckoTerminal 公開池成交。不是錢包損益，沒有把轉帳當成買入，也沒有計算地址報酬。",
    }
