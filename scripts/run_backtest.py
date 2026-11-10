#!/usr/bin/env python3
"""Run the paper backtests on cached public data and write the KST report."""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ymzz_quant.report import render_markdown  # noqa: E402
from ymzz_quant.service import load_named_scenarios, polymarket_summary, recent_swaps, run_dataset, sensitivity  # noqa: E402

KST = ZoneInfo("Asia/Seoul")


def main() -> None:
    scenarios = load_named_scenarios(ROOT)
    keys = ["wif_daily", "sol_usdc_daily", "bonk_daily_appendix", "popcat_daily_appendix"]
    names = ["conservative_no_trade", "exploratory_ohlcv_only"]
    runs = {}
    for key in keys:
        for name in names:
            result = run_dataset(key, scenarios[name], ROOT)
            runs[f"{key}|{name}"] = result
            print(
                f"{key} {name} trades={result.metrics['trade_count']} "
                f"return={result.metrics['total_return']:.6f} equity={result.metrics['final_equity_usd']:.4f}"
            )
    selection = (ROOT / "data/cache/meme_pool_decision.json").read_text(encoding="utf-8")
    criteria = (ROOT / "data/cache/selection_criteria.json").read_text(encoding="utf-8")
    bundle = {
        "runs": runs,
        "sensitivity": sensitivity("wif_daily", scenarios["exploratory_ohlcv_only"], ROOT),
        "polymarket": polymarket_summary(ROOT),
        "swaps": recent_swaps(ROOT),
        "selection_note": "選擇紀錄（報酬計算之前寫下的條件，以及事後沒有用報酬改選）：\n\n```json\n"
        + criteria
        + "\n```\n\n```json\n"
        + selection
        + "\n```",
    }
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).astimezone(KST)
    stamp = now.strftime("%Y-%m-%d_%H%M%S_KST")
    md_path = out_dir / f"{stamp}_backtest.md"
    md_path.write_text(render_markdown(bundle), encoding="utf-8")
    latest = out_dir / "LATEST_backtest.md"
    latest.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    serial = {}
    for key, result in runs.items():
        payload = result.to_dict()
        payload["indicators_omitted"] = True
        serial[key] = payload
    poly = dict(bundle["polymarket"])
    poly.pop("series", None)
    (out_dir / "runs.json").write_text(
        json.dumps(
            {
                "generated_at_kst": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "generated_at_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "runs": serial,
                "sensitivity": bundle["sensitivity"],
                "polymarket": poly,
                "swaps": bundle["swaps"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_trades(out_dir / "wif_exploratory_trades.csv", runs["wif_daily|exploratory_ohlcv_only"].trades)
    _write_trades(out_dir / "wif_conservative_trades.csv", runs["wif_daily|conservative_no_trade"].trades)
    _write_equity(out_dir / "wif_exploratory_equity.csv", runs["wif_daily|exploratory_ohlcv_only"].equity)
    _write_equity(out_dir / "wif_conservative_equity.csv", runs["wif_daily|conservative_no_trade"].equity)
    print("wrote", md_path)


def _write_trades(path: Path, trades: list[dict]) -> None:
    fields = [
        "status",
        "segment",
        "entry_signal_utc",
        "entry_signal_kst",
        "entry_fill_utc",
        "entry_fill_kst",
        "exit_signal_utc",
        "exit_signal_kst",
        "exit_fill_utc",
        "exit_fill_kst",
        "exit_reason",
        "qty",
        "entry_fill_px",
        "exit_fill_px",
        "realized_pnl",
        "unrealized_pnl",
        "gmgn_fees",
        "pool_fees",
        "chain_fees",
        "entry_residual",
        "exit_residual",
        "pool_fee_is_assumed",
        "execution_limitation",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade)


def _write_equity(path: Path, rows: list[dict]) -> None:
    fields = ["utc", "kst", "equity", "cash", "qty", "close", "drawdown", "drawdown_paused", "segment", "unrealized"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
