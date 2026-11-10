"""Validate a research request and run it on the existing engine.

The HTTP service and the tests call execute_research. A request that names a
dataset, interval, or date this cache does not have is rejected. Nothing here
substitutes another series.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ymzz_quant.catalog import DATASETS, ROOT, dataset_paths
from ymzz_quant.costs import CostScenario, load_sol_snapshot
from ymzz_quant.data_adapters import fmt_ts
from ymzz_quant.engine import run_backtest
from ymzz_quant.indicators import rsi_wilder
from ymzz_quant.service import load_bars

KST = ZoneInfo("Asia/Seoul")

FORMULAS = {
    "rsi": {
        "name": "RSI",
        "role": "decision",
        "formula": "Wilder RSI。第一個值是 period 根漲跌的平均，之後均線 = (前值*(period-1)+本根)/period。RS = 平均漲幅/平均跌幅，RSI = 100 - 100/(1+RS)。",
        "orders": "只有 rsi_period 這一條會進場與出場。進場要落在 [rsi_low, rsi_high]。出場是 RSI >= rsi_exit，而且要等下一根已收盤 K 的開盤才成交。",
    },
    "atr_pct": {
        "name": "ATR%",
        "role": "decision",
        "formula": "True range 取 high-low、|high-前收|、|low-前收| 的最大者。Wilder ATR 再除以該根收盤。",
        "orders": "atr_period 進決策。訓練段的 ATR% 分位數形成區間。停損距離是 k_sl * ATR%，停利是 k_tp * ATR%。k_sl * ATR% >= 1 的訊號會被擋下。",
    },
    "relative_volume": {
        "name": "相對成交量",
        "role": "decision",
        "formula": "本根成交量 / 過去 rv_period 根成交量的簡單平均。",
        "orders": "進場還要相對成交量 >= rv_min。",
    },
    "rsi_overlay": {
        "name": "比較用 RSI",
        "role": "display_only",
        "formula": "同一套 Wilder RSI，周期由 rsi_overlay_periods 指定，最多兩條。",
        "orders": "不進訊號。改這兩條的周期不會改成交。",
    },
    "horizontal_levels": {
        "name": "超買超賣水平線",
        "role": "display_only",
        "formula": "圖上的兩條常數：horizontal_oversold 與 horizontal_overbought。",
        "orders": "不進訊號。進場區間用的是 rsi_low / rsi_high，出場用 rsi_exit。水平線可以畫成不同的數字。",
    },
    "hypothetical_margin": {
        "name": "假設保證金",
        "role": "accounting",
        "formula": "抵押 = 名目/倍數，借入 = 名目-抵押。權益 = 現金 + 數量*價格 - 借入。資金費與借款費是假設日利率乘上這根 K 佔一天的比例。",
        "orders": "現貨與 GMGN 交換沒有這個模式。這不是永續合約回測。權益小於等於維持率時，下一根開盤假設平倉。現金不允許補到 0 以上。",
    },
}

FEATURE_MATRIX = [
    {"id": "local_api", "status": "completed", "note": "本機 Python HTTP 服務與前端。沒有部署。"},
    {"id": "config_reaches_engine", "status": "completed", "note": "表單送出的周期、費用、日期、資料集與倍數進引擎，回應會回顯。"},
    {"id": "three_decision_indicators", "status": "completed", "note": "決策只有 RSI、ATR%、相對成交量。比較 RSI 與水平線只畫圖。"},
    {"id": "btc_eth_spot", "status": "completed", "note": "Kraken 公開 OHLC，無金鑰。已快取日線與小時線，未收盤的最後一根已排除。"},
    {"id": "solana_pools", "status": "completed", "note": "沿用 GeckoTerminal 的 WIF、SOL/USDC、BONK、POPCAT 日線。"},
    {"id": "interval_guard", "status": "completed", "note": "沒有的周期或日期會拒絕，不會改去 WIF 日線。"},
    {"id": "leverage_cap", "status": "completed", "note": "紙上 1、1.5、2。大於 2 會拒絕。現貨不能開保證金。"},
    {"id": "hypothetical_margin", "status": "completed", "note": "有抵押、借入、假設費用、強平與破產下限。沒有真實永續資金費資料。"},
    {"id": "polymarket", "status": "completed", "note": "機率圖獨立，不進 $10 損益。"},
    {"id": "wallet_module", "status": "partial", "note": "地址清單與 CSV 欄位檢查可用。沒有鏈上成交解析，轉帳不是交易，也不算損益。"},
    {"id": "streamlit", "status": "partial", "note": "app/dashboard.py 仍是同一行程內的介面，不是這支 HTTP 服務。"},
    {"id": "offline_html", "status": "completed", "note": "下載的 HTML 是該次回應的快照，不會重算。"},
    {"id": "real_perpetual", "status": "missing", "note": "沒有抓永續合約 K 線、標記價或資金費。"},
    {"id": "meme_15m", "status": "missing", "note": "沒有抓 meme 15 分線。要求 15m 會得到錯誤。"},
    {"id": "smart_money", "status": "missing", "note": "聰明錢分類、熱門地址新進資金、歷史可賣性與第一波偵測都沒有實作。"},
    {"id": "stock_app", "status": "missing", "note": "Stock App 身份不明，沒有連接，也沒有用股價資料代替。"},
    {"id": "live_trading", "status": "missing", "note": "沒有錢包連線、私鑰、下單、Telegram 發送或付費部署。"},
]


def architecture() -> dict:
    return {
        "paper_only": True,
        "deployed": False,
        "frontend": {
            "live_page": "frontend/index.html，由這個本機行程在 / 提供",
            "calls": "瀏覽器對同一個行程送 /api/*",
            "streamlit": "app/dashboard.py 在自己的行程裡直接呼叫引擎，不是這支 API，也沒有獨立部署。",
            "static_snapshot": "preview/index.html 與下載的快照只顯示已經算好的結果。",
        },
        "backend": {
            "module": "ymzz_quant.api",
            "engine": "ymzz_quant.engine.run_backtest",
            "bind": "127.0.0.1",
            "start": "PYTHONPATH=src python3 -m ymzz_quant.api",
        },
        "data": {
            "kraken": "公開 OHLC，無 API 金鑰。ccxt 沒有安裝。ccxt 是免費的函式庫，跟有沒有權限用某家付費行情是兩件事。",
            "geckoterminal": "既有的 keyless 池 K 線快取。",
            "polymarket": "既有的機率歷史，獨立面板。",
        },
        "feature_matrix": FEATURE_MATRIX,
    }


def _interval_label(spec: dict) -> str:
    if spec.get("interval_label"):
        return spec["interval_label"]
    return {86400: "1d", 3600: "1h", 900: "15m"}.get(spec["expected_interval_seconds"], str(spec["expected_interval_seconds"]))


def _quote(spec: dict) -> str:
    if spec.get("quote_symbol"):
        return spec["quote_symbol"]
    if " / " in spec.get("symbol", ""):
        return spec["symbol"].split(" / ", 1)[1]
    return spec.get("quote_token") or ""


def describe_datasets() -> dict:
    rows = []
    for key, spec in DATASETS.items():
        bars, meta = load_bars(key)
        paths = dataset_paths(key)
        sidecar = json.loads(Path(str(paths[0]) + ".meta.json").read_text(encoding="utf-8"))
        first = fmt_ts(bars[0].ts)
        last = fmt_ts(bars[-1].ts)
        rows.append(
            {
                "dataset_key": key,
                "symbol": spec["symbol"],
                "marketplace": spec.get("marketplace", "geckoterminal_pool"),
                "network": spec.get("network", spec.get("chain")),
                "quote": _quote(spec),
                "unit": spec.get("unit", "USD mark from GeckoTerminal currency=usd"),
                "pair": spec.get("pair") or spec.get("pool") or spec["symbol"],
                "pool": spec.get("pool"),
                "interval": _interval_label(spec),
                "instrument": spec.get("instrument", "spot_pool_swap"),
                "margin": spec.get("margin", "unsupported_on_gmgn_swap_and_spot_pool"),
                "closed_bars": len(bars),
                "first_open_utc": first["utc"],
                "first_open_kst": first["kst"],
                "last_open_utc": last["utc"],
                "last_open_kst": last["kst"],
                "dropped_unclosed": meta.get("unclosed_bar_count", 0),
                "sha256": meta.get("sha256"),
                "fetched_at_utc": sidecar.get("fetched_at_utc"),
                "fetched_at_kst": sidecar.get("fetched_at_kst"),
                "source_url": sidecar.get("url") or spec.get("source_template"),
                "bias_zh": spec.get("bias_zh"),
                "api_key_used": False,
            }
        )
    return {
        "datasets": rows,
        "substitution": "請求的資料集、周期或日期不在這份清單時，服務會拒絕，不會改用別的檔案。",
        "not_available": ["meme 15m", "kraken 15m", "永續合約資金費"],
    }


def _signal_defaults() -> dict:
    return {
        "rsi_period": 14,
        "atr_period": 14,
        "rv_period": 20,
        "rsi_low": 25.0,
        "rsi_high": 40.0,
        "rsi_exit": 70.0,
        "rv_min": 1.5,
        "k_sl": 1.5,
        "k_tp": 2.0,
        "execution_delay_bars": 1,
        "execution_mode": "manual_tg_next_open",
        "no_reentry": True,
        "initial_cash_usd": 10.0,
        "proposed_per_trade_loss_budget_usd": 0.1,
        "proposed_max_drawdown_usd": 2.0,
        "proposed_max_drawdown_frac": 0.2,
        "slip_bp_buy": 30.0,
        "slip_bp_sell": 30.0,
        "rsi_overlay_periods": [],
        "show_horizontal_levels": True,
        "horizontal_oversold": 30.0,
        "horizontal_overbought": 70.0,
        "leverage": 1.0,
        "instrument_mode": "spot",
        "assumed_borrow_rate_per_day": 0.0,
        "assumed_funding_rate_per_day": 0.0,
        "maintenance_margin_frac": 0.25,
        "liquidation_penalty_frac": 0.0,
        "start_date": None,
        "end_date": None,
    }


def default_config(preset: str = "kraken_btc_spot_assumed_fees") -> dict:
    base = _signal_defaults()
    catalog = {
        "kraken_btc_spot_assumed_fees": ("btc_usd_1d", "Kraken BTC/USD 現貨。費用是研究假設，不是 Kraken 費率表，也不是 GMGN。"),
        "kraken_eth_spot_assumed_fees": ("eth_usd_1d", "Kraken ETH/USD 現貨。費用是研究假設，不是 Kraken 費率表，也不是 GMGN。"),
        "wif_conservative": ("wif_daily", "WIF 保守預設。池費未知，所以不開倉。"),
        "wif_exploratory": ("wif_daily", "WIF 放寬實驗。不是完整風控策略。"),
    }
    if preset not in catalog:
        raise KeyError(preset)
    dataset_key, label = catalog[preset]
    spec = DATASETS[dataset_key]
    cfg = {
        **base,
        "preset": preset,
        "name": preset,
        "label_zh": label,
        "dataset_key": dataset_key,
        "symbol": spec["symbol"],
        "interval": _interval_label(spec),
        "source": spec.get("marketplace", "geckoterminal_pool"),
        "pool": spec.get("pool"),
    }
    if preset.startswith("kraken_"):
        cfg.update(
            fee_rate_per_side=0.002,
            pool_fee_rate_per_side=0.0,
            pool_fee_status="explicit_zero_spot_has_no_pool_fee",
            chain_cost_sol_per_side=0.0,
            wallet_reserve_sol=0.0,
            require_known_pool_fee=True,
            require_historical_sellability=False,
            require_historical_liquidity=False,
            fee_note="0.20% 每邊是研究假設。不是 Kraken 的成交量費率，也不是 GMGN 的 1%。",
        )
    elif preset == "wif_conservative":
        cfg.update(
            fee_rate_per_side=0.01,
            pool_fee_rate_per_side=None,
            pool_fee_status="unknown_geckoterminal_pool_fee_percentage_null",
            chain_cost_sol_per_side=0.005,
            wallet_reserve_sol=0.05,
            require_known_pool_fee=True,
            require_historical_sellability=True,
            require_historical_liquidity=True,
            fee_note="GMGN 文件的每筆 1%。池費維持未知。",
        )
    else:
        cfg.update(
            fee_rate_per_side=0.01,
            pool_fee_rate_per_side=0.003,
            pool_fee_status="ASSUMED_because_geckoterminal_pool_fee_percentage_was_null",
            chain_cost_sol_per_side=0.005,
            wallet_reserve_sol=0.05,
            proposed_per_trade_loss_budget_usd=3.0,
            require_known_pool_fee=True,
            require_historical_sellability=False,
            require_historical_liquidity=False,
            fee_note="GMGN 1%。池費 0.003 是假設。單筆預算 $3，不是 $0.10。",
        )
    return cfg


def _err(errors: list, field: str, message: str) -> None:
    errors.append({"field": field, "message": message})


def _num(body, field, errors, lo, hi, integer=False):
    value = body.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _err(errors, field, "需要數字")
        return None
    if integer and int(value) != value:
        _err(errors, field, "需要整數")
        return None
    number = int(value) if integer else float(value)
    if not lo <= number <= hi:
        _err(errors, field, f"需要介於 {lo} 與 {hi}")
        return None
    return number


def _bool(body, field, errors) -> bool | None:
    value = body.get(field)
    if not isinstance(value, bool):
        _err(errors, field, "需要 true 或 false")
        return None
    return value


def _date(value, field, errors):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        _err(errors, field, "日期要用 YYYY-MM-DD 或留空")
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        _err(errors, field, "日期要用 YYYY-MM-DD")
        return None
    return int(parsed.timestamp())


def normalize(body: dict) -> tuple[dict | None, list[dict]]:
    errors: list[dict] = []
    if not isinstance(body, dict):
        return None, [{"field": "body", "message": "需要 JSON 物件"}]
    dataset_key = body.get("dataset_key")
    spec = DATASETS.get(dataset_key)
    if spec is None:
        _err(errors, "dataset_key", "沒有這個資料集。不會改用其他資料。")
        spec = None
    cfg = {
        "preset": str(body.get("preset") or "custom")[:80],
        "name": str(body.get("name") or "research_request")[:80],
        "label_zh": str(body.get("label_zh") or "自訂研究請求")[:200],
        "dataset_key": dataset_key,
        "fee_note": str(body.get("fee_note") or "")[:300],
    }
    if spec is not None:
        cfg["symbol"] = spec["symbol"]
        cfg["interval"] = _interval_label(spec)
        cfg["source"] = spec.get("marketplace", "geckoterminal_pool")
        cfg["pool"] = spec.get("pool")
        for field, expected in (
            ("symbol", spec["symbol"]),
            ("interval", _interval_label(spec)),
            ("source", spec.get("marketplace", "geckoterminal_pool")),
        ):
            if field in body and body[field] != expected:
                _err(errors, field, f"送出的是 {body[field]}，這份資料實際是 {expected}。沒有改去別的資料。")
        if "pool" in body and body["pool"] != spec.get("pool"):
            _err(errors, "pool", "池子與資料集不一致。沒有改去別的池。")
    for field, lo, hi, integer in (
        ("initial_cash_usd", 0.01, 10, False),
        ("rsi_period", 2, 200, True),
        ("atr_period", 2, 200, True),
        ("rv_period", 2, 200, True),
        ("rsi_low", 0, 100, False),
        ("rsi_high", 0, 100, False),
        ("rsi_exit", 0, 100, False),
        ("rv_min", 0, 100, False),
        ("k_sl", 0.01, 20, False),
        ("k_tp", 0.01, 20, False),
        ("fee_rate_per_side", 0, 0.5, False),
        ("slip_bp_buy", 0, 500, False),
        ("slip_bp_sell", 0, 500, False),
        ("execution_delay_bars", 1, 10, True),
        ("chain_cost_sol_per_side", 0, 1, False),
        ("wallet_reserve_sol", 0, 1, False),
        ("leverage", 0.01, 2, False),
        ("assumed_borrow_rate_per_day", 0, 1, False),
        ("assumed_funding_rate_per_day", 0, 1, False),
        ("maintenance_margin_frac", 0.01, 1, False),
        ("liquidation_penalty_frac", 0, 0.5, False),
        ("horizontal_oversold", 0, 100, False),
        ("horizontal_overbought", 0, 100, False),
        ("proposed_per_trade_loss_budget_usd", 0.01, 10, False),
        ("proposed_max_drawdown_usd", 0.01, 10, False),
        ("proposed_max_drawdown_frac", 0.01, 1, False),
    ):
        cfg[field] = _num(body, field, errors, lo, hi, integer)
    for field in (
        "no_reentry",
        "require_known_pool_fee",
        "require_historical_sellability",
        "require_historical_liquidity",
        "show_horizontal_levels",
    ):
        cfg[field] = _bool(body, field, errors)
    if body.get("historical_sellability_known") is True or body.get("historical_liquidity_known") is True:
        _err(errors, "historical_sellability_known", "這份服務沒有可賣性或流動性的歷史證明，不能把已知設成 true。")
    mode = body.get("instrument_mode")
    if mode not in {"spot", "hypothetical_assumed_margin"}:
        _err(errors, "instrument_mode", "只能是 spot 或 hypothetical_assumed_margin")
    cfg["instrument_mode"] = mode
    execution = body.get("execution_mode")
    if execution not in {"manual_tg_next_open", "resting_stop_research"}:
        _err(errors, "execution_mode", "成交模式不在允許清單")
    cfg["execution_mode"] = execution
    pool_fee = body.get("pool_fee_rate_per_side")
    if pool_fee is None:
        cfg["pool_fee_rate_per_side"] = None
    elif isinstance(pool_fee, bool) or not isinstance(pool_fee, (int, float)) or not 0 <= float(pool_fee) <= 0.5:
        _err(errors, "pool_fee_rate_per_side", "池費要是 null，或 0 到 0.5 的數字")
        cfg["pool_fee_rate_per_side"] = None
    else:
        cfg["pool_fee_rate_per_side"] = float(pool_fee)
    status = body.get("pool_fee_status")
    if not isinstance(status, str) or not status.strip():
        _err(errors, "pool_fee_status", "池費狀態必須寫明")
    else:
        cfg["pool_fee_status"] = status[:180]
    overlays = body.get("rsi_overlay_periods", [])
    if not isinstance(overlays, list) or len(overlays) > 2:
        _err(errors, "rsi_overlay_periods", "比較用 RSI 最多兩條")
        overlays = []
    clean_overlays = []
    for item in overlays:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or int(item) != item or not 2 <= int(item) <= 200:
            _err(errors, "rsi_overlay_periods", "比較用周期要是 2 到 200 的整數")
        else:
            clean_overlays.append(int(item))
    cfg["rsi_overlay_periods"] = clean_overlays
    cfg["start_ts"] = _date(body.get("start_date"), "start_date", errors)
    cfg["end_ts"] = _date(body.get("end_date"), "end_date", errors)
    cfg["start_date"] = body.get("start_date") or None
    cfg["end_date"] = body.get("end_date") or None
    if cfg.get("rsi_low") is not None and cfg.get("rsi_high") is not None and cfg["rsi_low"] >= cfg["rsi_high"]:
        _err(errors, "rsi_low", "進場下限要小於上限")
    equity = cfg.get("initial_cash_usd")
    budget = cfg.get("proposed_per_trade_loss_budget_usd")
    drawdown = cfg.get("proposed_max_drawdown_usd")
    frac = cfg.get("proposed_max_drawdown_frac")
    if equity is not None and budget is not None and budget > equity + 1e-9:
        _err(errors, "proposed_per_trade_loss_budget_usd", "單筆虧損預算不能超過本金")
    if equity is not None and drawdown is not None and drawdown > equity + 1e-9:
        _err(errors, "proposed_max_drawdown_usd", "回撤提案不能超過本金")
    if equity and drawdown is not None and frac is not None and abs(drawdown / equity - frac) > 1e-6:
        _err(errors, "proposed_max_drawdown_frac", "回撤比例必須等於回撤金額除以本金")
    raw_leverage = body.get("leverage")
    if isinstance(raw_leverage, (int, float)) and not isinstance(raw_leverage, bool) and float(raw_leverage) > 2:
        _err(errors, "leverage", "紙上倍數大於 2，已拒絕")
    leverage = cfg.get("leverage")
    if leverage is not None and not any(abs(leverage - item) < 1e-9 for item in (1.0, 1.5, 2.0)):
        _err(errors, "leverage", "紙上倍數只能是 1、1.5 或 2")
    if mode == "spot" and leverage is not None and abs(leverage - 1.0) > 1e-9:
        _err(errors, "leverage", "現貨與 GMGN 交換沒有原生保證金，倍數必須是 1。假設保證金是另一個模式。")
    if mode == "spot" and (
        (cfg.get("assumed_borrow_rate_per_day") or 0) > 0 or (cfg.get("assumed_funding_rate_per_day") or 0) > 0
    ):
        _err(errors, "assumed_borrow_rate_per_day", "現貨模式不套用假設借款或資金費。")
    if errors:
        return None, errors
    return cfg, []


def _window(bars, cfg):
    start = cfg["start_ts"] if cfg["start_ts"] is not None else bars[0].ts
    end_day = cfg["end_ts"]
    if start < bars[0].ts:
        return None, {"field": "start_date", "message": "開始日早於這份已收盤資料。沒有改用其他資料。"}
    if end_day is not None and end_day > bars[-1].ts:
        return None, {"field": "end_date", "message": "結束日晚於最後一根已收盤 K。沒有改用其他資料。"}
    end_limit = bars[-1].ts if end_day is None else end_day + 86400 - 1
    if cfg["start_ts"] is not None and cfg["end_ts"] is not None and cfg["start_ts"] > cfg["end_ts"]:
        return None, {"field": "end_date", "message": "結束日早於開始日"}
    chosen = [bar for bar in bars if start <= bar.ts <= end_limit]
    if len(chosen) < 30:
        return None, {"field": "start_date", "message": f"這個窗口只有 {len(chosen)} 根已收盤 K，少於 30。沒有改用其他資料。"}
    return chosen, None


def _scenario(cfg: dict, sol: dict) -> CostScenario:
    return CostScenario(
        name=cfg["name"],
        label_zh=cfg["label_zh"],
        gmgn_fee_rate_per_side=cfg["fee_rate_per_side"],
        pool_fee_rate_per_side=cfg["pool_fee_rate_per_side"],
        pool_fee_status=cfg["pool_fee_status"],
        chain_cost_sol_per_side=cfg["chain_cost_sol_per_side"],
        chain_cost_note=cfg["fee_note"] or "request",
        slip_bp_buy=cfg["slip_bp_buy"],
        slip_bp_sell=cfg["slip_bp_sell"],
        slip_note="request",
        wallet_reserve_sol=cfg["wallet_reserve_sol"],
        sol_usd=float(sol["sol_usd"]),
        sol_usd_fetched_at_utc=sol["fetched_at_utc"],
        sol_usd_fetched_at_kst=sol["fetched_at_kst"],
        sol_usd_source=sol["source"],
        initial_cash_usd=cfg["initial_cash_usd"],
        proposed_per_trade_loss_budget_usd=cfg["proposed_per_trade_loss_budget_usd"],
        proposed_max_drawdown_frac=cfg["proposed_max_drawdown_frac"],
        proposed_max_drawdown_usd=cfg["proposed_max_drawdown_usd"],
        require_known_pool_fee=cfg["require_known_pool_fee"],
        require_historical_sellability=cfg["require_historical_sellability"],
        require_historical_liquidity=cfg["require_historical_liquidity"],
        historical_sellability_known=False,
        historical_liquidity_known=False,
        execution_mode=cfg["execution_mode"],
        no_reentry=cfg["no_reentry"],
        k_sl=cfg["k_sl"],
        k_tp=cfg["k_tp"],
        rsi_low=cfg["rsi_low"],
        rsi_high=cfg["rsi_high"],
        rsi_exit=cfg["rsi_exit"],
        rv_min=cfg["rv_min"],
        rsi_period=cfg["rsi_period"],
        atr_period=cfg["atr_period"],
        rv_period=cfg["rv_period"],
        execution_delay_bars=cfg["execution_delay_bars"],
        leverage=cfg["leverage"],
        instrument_mode=cfg["instrument_mode"],
        assumed_borrow_rate_per_day=cfg["assumed_borrow_rate_per_day"],
        assumed_funding_rate_per_day=cfg["assumed_funding_rate_per_day"],
        maintenance_margin_frac=cfg["maintenance_margin_frac"],
        liquidation_penalty_frac=cfg["liquidation_penalty_frac"],
        request_controls_are_user_supplied=True,
    )


def _warnings(cfg: dict, spec: dict) -> list[str]:
    notes = [
        "模擬損益。沒有下單，也沒有把報酬乘上倍數來假裝有槓桿。",
        "no_reentry 若打開，第一筆出場後同一市場後面的進場都會被擋下，包含驗證段與留出段。這是可選實驗，不是第一波偵測，也不能證明沒有第二波。",
    ]
    if spec.get("marketplace") == "geckoterminal_pool":
        notes.append(spec.get("bias_zh") or "池子是事先選的，有倖存者偏差。")
    else:
        notes.append("這是 Kraken 現貨，不是 meme 池，也不能拿來填補缺漏的 meme 周期。")
    if cfg["instrument_mode"] == "hypothetical_assumed_margin":
        notes.append("假設保證金模擬。借款費、資金費、維持率與強平罰則都是這次請求裡的假設，不是交易所永續合約回測。")
    if cfg["pool_fee_status"].upper().startswith("ASSUMED"):
        notes.append("池費是假設值。")
    if cfg["chain_cost_sol_per_side"] > 0 and spec.get("marketplace") == "kraken_spot":
        notes.append("這次請求在 Kraken 現貨上填了 SOL 鏈上費。服務照送出的數字計算，沒有偷偷改成 0。")
    notes.append("Stock App 沒有連接。")
    return notes


def _ledger(trades: list[dict]) -> str:
    fields = [
        "status",
        "segment",
        "entry_signal_utc",
        "entry_signal_kst",
        "entry_fill_utc",
        "entry_fill_kst",
        "exit_fill_utc",
        "exit_fill_kst",
        "entry_fill_px",
        "exit_fill_px",
        "qty",
        "realized_pnl",
        "fee_per_side_usd",
        "pool_fees",
        "chain_fees",
        "exit_reason",
        "leverage",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for trade in trades:
        row = {field: trade.get(field) for field in fields}
        row["fee_per_side_usd"] = trade.get("gmgn_fees")
        writer.writerow(row)
    return buffer.getvalue()


def _report(payload: dict) -> str:
    now = datetime.now(KST)
    provenance = payload["provenance"]
    metrics = payload["metrics"]
    lines = [
        f"# 研究請求 {now.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "這是一次本機 API 計算的紀錄，不是已登記的 WIF 研究結論，也沒有部署。",
        "",
        f"- 資料：{provenance['symbol']} · {provenance['marketplace']} · {provenance['network']}",
        f"- 單位：{provenance['unit']} · 報價：{provenance['quote']} · 代號/池：{provenance['pair']}",
        f"- 周期：{provenance['interval']} · 已收盤 {provenance['closed_bars']} 根",
        f"- 覆蓋：{provenance['first_open_utc']} 到 {provenance['last_open_utc']}（開盤時間）",
        f"- 抓取：{provenance['fetched_at_utc']} · sha256 `{provenance['sha256']}`",
        f"- 來源：{provenance['source_url']}",
        f"- 本金 ${metrics['initial_cash_usd']} · 期末 ${metrics['final_equity_usd']:.4f} · 已實現 {metrics['realized_pnl']:.4f}",
        f"- 成交 {metrics['closed_trade_count']} 筆 · 模式 {metrics['instrument_mode']} · 倍數 {metrics['leverage_used']}",
        f"- 決策 RSI{metrics['rsi_period']}、ATR{metrics['atr_period']}%、相對成交量 {metrics['rv_period']}",
        f"- 請求雜湊 `{payload['request_sha256']}`",
        "",
        "## 這次送進引擎的設定",
        "",
        "```json",
        json.dumps(payload["submitted_config"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 說明",
        "",
    ]
    lines.extend(f"- {note}" for note in payload["warnings"])
    lines.extend(["", "## 功能", ""])
    for row in FEATURE_MATRIX:
        lines.append(f"- {row['status']}: {row['id']} — {row['note']}")
    lines.append("")
    return "\n".join(lines)


def execute_research(body: dict, root: Path | None = None) -> dict:
    root = root or ROOT
    cfg, errors = normalize(body)
    if errors:
        return {"ok": False, "errors": errors, "result": None}
    spec = DATASETS[cfg["dataset_key"]]
    bars, meta = load_bars(cfg["dataset_key"], root)
    chosen, window_error = _window(bars, cfg)
    if window_error:
        return {"ok": False, "errors": [window_error], "result": None}
    sol = load_sol_snapshot(root / "data" / "cache" / "coingecko_sol_usd.json")
    scenario = _scenario(cfg, sol)
    try:
        result = run_backtest(
            chosen,
            scenario,
            cfg["dataset_key"],
            spec["expected_interval_seconds"],
            dataset_meta=meta,
        )
    except ValueError as exc:
        return {"ok": False, "errors": [{"field": "engine", "message": str(exc)}], "result": None}
    closes = [bar.close for bar in chosen]
    stamps = [bar.ts for bar in chosen]
    overlays = {
        str(period): rsi_wilder(closes, period, stamps, spec["expected_interval_seconds"])
        for period in cfg["rsi_overlay_periods"]
    }
    paths = dataset_paths(cfg["dataset_key"], root)
    sidecar = json.loads(Path(str(paths[0]) + ".meta.json").read_text(encoding="utf-8"))
    request_blob = json.dumps(cfg, sort_keys=True, default=str).encode()
    public = result.to_dict()
    provenance = {
        "dataset_key": cfg["dataset_key"],
        "symbol": spec["symbol"],
        "marketplace": spec.get("marketplace", "geckoterminal_pool"),
        "network": spec.get("network", spec.get("chain")),
        "quote": _quote(spec),
        "unit": spec.get("unit", "USD mark from GeckoTerminal currency=usd"),
        "pair": spec.get("pair") or spec.get("pool") or spec["symbol"],
        "pool": spec.get("pool"),
        "interval": _interval_label(spec),
        "closed_bars": len(chosen),
        "first_open_utc": chosen[0].iso_utc(),
        "last_open_utc": chosen[-1].iso_utc(),
        "dropped_unclosed": meta.get("unclosed_bar_count", 0),
        "sha256": meta.get("sha256"),
        "fetched_at_utc": sidecar.get("fetched_at_utc"),
        "fetched_at_kst": sidecar.get("fetched_at_kst"),
        "source_url": sidecar.get("url") or spec.get("source_template"),
        "api_key_used": False,
        "partial_bars_included": False,
    }
    payload = {
        "ok": True,
        "errors": [],
        "submitted_config": cfg,
        "request_sha256": hashlib.sha256(request_blob).hexdigest(),
        "config_sha256": result.config_sha256,
        "provenance": provenance,
        "scenario": public["scenario"],
        "metrics": public["metrics"],
        "trades": public["trades"],
        "skips_count": len(public["skips"]),
        "equity_tail": public["equity"][-8:],
        "indicators": {
            "rsi": result.indicators["rsi"],
            "atr_pct": result.indicators["atr_pct"],
            "relative_volume": result.indicators["rv"],
        },
        "display_only": {
            "rsi_overlay_periods": cfg["rsi_overlay_periods"],
            "rsi_overlays": overlays,
            "horizontal_levels": {
                "shown": cfg["show_horizontal_levels"],
                "oversold": cfg["horizontal_oversold"],
                "overbought": cfg["horizontal_overbought"],
            },
            "note": "比較用 RSI 與水平線只供畫圖。決策指標維持三個。",
        },
        "formulas": FORMULAS,
        "warnings": _warnings(cfg, spec),
        "split": public["split"],
        "frozen_atr_band": public["frozen_atr_band"],
        "recomputed": True,
    }
    payload["ledger_csv"] = _ledger(public["trades"])
    payload["report_markdown"] = _report(payload)
    from ymzz_quant.snapshot import render_snapshot

    payload["snapshot_html"] = render_snapshot(payload)
    return payload
