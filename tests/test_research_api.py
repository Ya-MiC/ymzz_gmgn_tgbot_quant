"""Config, market, leverage, and wallet checks. These tests do not open a network."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

import pytest

from ymzz_quant.api import ResearchHandler, ThreadingHTTPServer
from ymzz_quant.catalog import ROOT
from ymzz_quant.costs import CostScenario
from ymzz_quant.data_adapters import Bar
from ymzz_quant.engine import run_backtest
from ymzz_quant.research_config import default_config, execute_research
from ymzz_quant.wallets import add_address, parse_activity_csv


def _request(cfg=None, **overrides):
    body = default_config() if cfg is None else json.loads(json.dumps(cfg))
    body.update(overrides)
    return body


def _use(body, dataset_key):
    from ymzz_quant.catalog import DATASETS
    from ymzz_quant.research_config import _interval_label

    spec = DATASETS[dataset_key]
    body["dataset_key"] = dataset_key
    body["symbol"] = spec["symbol"]
    body["interval"] = _interval_label(spec)
    body["source"] = spec.get("marketplace", "geckoterminal_pool")
    body["pool"] = spec.get("pool")
    return body


def test_rsi_period_reaches_engine_without_claiming_a_better_return():
    slow = execute_research(_request())
    fast = execute_research(_request(rsi_period=19))
    assert slow["ok"] and fast["ok"]
    assert slow["metrics"]["rsi_period"] == 14
    assert fast["metrics"]["rsi_period"] == 19
    assert slow["scenario"]["rsi_period"] == 14
    assert fast["submitted_config"]["rsi_period"] == 19
    assert slow["indicators"]["rsi"] != fast["indicators"]["rsi"]
    assert slow["request_sha256"] != fast["request_sha256"]


def test_overlay_rsi_does_not_change_trades():
    base = execute_research(_request())
    over = execute_research(_request(rsi_overlay_periods=[6, 12]))
    assert over["ok"]
    assert over["trades"] == base["trades"]
    assert over["display_only"]["rsi_overlay_periods"] == [6, 12]
    assert "RSI6" not in over["scenario"]["decision_indicators"]
    assert len(over["scenario"]["decision_indicators"]) == 3


def test_btc_eth_and_pool_are_different_sources():
    btc = execute_research(_request())
    eth = execute_research(_use(_request(), "eth_usd_1d"))
    pool = execute_research(default_config("wif_conservative"))
    assert btc["provenance"]["symbol"] == "BTC/USD"
    assert eth["provenance"]["symbol"] == "ETH/USD"
    assert btc["provenance"]["sha256"] != eth["provenance"]["sha256"]
    assert pool["provenance"]["marketplace"] == "geckoterminal_pool"
    assert pool["provenance"]["symbol"] != btc["provenance"]["symbol"]
    assert btc["provenance"]["closed_bars"] == 720
    assert btc["provenance"]["dropped_unclosed"] == 1
    assert btc["provenance"]["last_open_utc"] == "2026-11-09T00:00:00Z"
    assert btc["provenance"]["api_key_used"] is False


def test_missing_interval_or_date_is_rejected():
    missing = execute_research(_request(interval="15m"))
    assert missing["ok"] is False
    assert missing["result"] is None
    text = json.dumps(missing, ensure_ascii=False)
    assert "WIF" not in text
    early = execute_research(_request(start_date="2019-01-01"))
    assert early["ok"] is False
    assert "沒有改用其他資料" in early["errors"][0]["message"]


def test_equity_budget_and_drawdown_stay_within_ten_dollars():
    too_much_cash = execute_research(_request(initial_cash_usd=11))
    too_much_budget = execute_research(
        _request(initial_cash_usd=3, proposed_per_trade_loss_budget_usd=4, proposed_max_drawdown_usd=2, proposed_max_drawdown_frac=2 / 3)
    )
    mismatched = execute_research(_request(proposed_max_drawdown_usd=4, proposed_max_drawdown_frac=0.2))
    assert too_much_cash["ok"] is False
    assert too_much_budget["ok"] is False
    assert mismatched["ok"] is False


def test_leverage_cap_and_spot_margin_rejection():
    too_high = execute_research(_request(leverage=3))
    assert too_high["ok"] is False
    assert any("2" in item["message"] for item in too_high["errors"])
    spot = execute_research(_request(leverage=2))
    assert spot["ok"] is False
    assert "沒有原生保證金" in spot["errors"][0]["message"]


def test_service_does_not_call_urlopen(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("network lookup")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    result = execute_research(_request())
    assert result["ok"] is True
    assert result["provenance"]["fetched_at_utc"] == "2026-11-10T03:23:59Z"


def _toy(**overrides) -> CostScenario:
    raw = dict(
        name="toy",
        label_zh="合成",
        gmgn_fee_rate_per_side=0.01,
        pool_fee_rate_per_side=0.0,
        pool_fee_status="SYNTHETIC_EXPLICIT",
        chain_cost_sol_per_side=0.0,
        chain_cost_note="synthetic",
        slip_bp_buy=0.0,
        slip_bp_sell=0.0,
        slip_note="synthetic",
        wallet_reserve_sol=0.0,
        sol_usd=1.0,
        sol_usd_fetched_at_utc="n/a",
        sol_usd_fetched_at_kst="n/a",
        sol_usd_source="synthetic",
        initial_cash_usd=10.0,
        proposed_per_trade_loss_budget_usd=10.0,
        proposed_max_drawdown_frac=1.0,
        proposed_max_drawdown_usd=10.0,
        require_known_pool_fee=True,
        require_historical_sellability=False,
        require_historical_liquidity=False,
        historical_sellability_known=False,
        historical_liquidity_known=False,
        execution_mode="manual_tg_next_open",
        no_reentry=False,
        k_sl=0.2,
        k_tp=5.0,
        rsi_low=0.0,
        rsi_high=100.0,
        rsi_exit=101.0,
        rv_min=0.0,
        min_notional_usd=0.01,
        instrument_mode="hypothetical_assumed_margin",
        leverage=2.0,
        maintenance_margin_frac=0.9,
        liquidation_penalty_frac=0.05,
        assumed_borrow_rate_per_day=0.01,
    )
    raw.update(overrides)
    return CostScenario(**raw)


def _path(prices):
    start = 1_700_000_000
    return [Bar(start + i * 86400, price, price + 1, max(price - 1, 0.01), price, 1_000.0) for i, price in enumerate(prices)]


def test_hypothetical_margin_is_not_a_multiplied_return_and_cannot_top_up():
    prices = [100.0] * 40
    bars = _path(prices)
    signal = [False] * len(bars)
    signal[24] = True
    plain = run_backtest(
        bars,
        _toy(instrument_mode="spot", leverage=1.0, assumed_borrow_rate_per_day=0.0, maintenance_margin_frac=0.25, atr_period=2),
        "synthetic",
        86400,
        synthetic=True,
        synthetic_signal_override=signal,
    )
    levered = run_backtest(bars, _toy(atr_period=2), "synthetic", 86400, synthetic=True, synthetic_signal_override=signal)
    assert levered.metrics["leverage_used"] == 2
    assert levered.metrics["hypothetical_margin_is_real_perp"] is False
    assert min(row["cash"] for row in levered.equity) >= -1e-9
    assert levered.metrics["final_equity_usd"] < plain.metrics["final_equity_usd"]
    plain_loss = plain.metrics["initial_cash_usd"] - plain.metrics["final_equity_usd"]
    levered_loss = levered.metrics["initial_cash_usd"] - levered.metrics["final_equity_usd"]
    assert levered_loss != pytest.approx(2 * plain_loss)
    closed = [trade for trade in levered.trades if trade["status"] == "HYPOTHETICAL_LIQUIDATION"]
    assert closed and closed[0]["gmgn_fees"] > 0
    assert closed[0]["exit_reason"] == "hypothetical_liquidation_next_open"


def test_gap_through_hypothetical_margin_floors_at_zero_without_top_up():
    prices = [100.0] * 28 + [1.0, 1.0, 1.0]
    bars = _path(prices)
    signal = [False] * len(bars)
    signal[24] = True
    result = run_backtest(
        bars,
        _toy(atr_period=2, maintenance_margin_frac=0.05, liquidation_penalty_frac=0.0),
        "synthetic",
        86400,
        synthetic=True,
        synthetic_signal_override=signal,
    )
    assert result.trades[0]["status"] == "BANKRUPTCY_FLOOR_NO_TOPUP"
    assert result.metrics["final_equity_usd"] == pytest.approx(0.0)
    assert min(row["cash"] for row in result.equity) == pytest.approx(0.0)


def test_engine_rejects_leverage_above_two_even_if_validation_is_bypassed():
    with pytest.raises(ValueError, match="above 2"):
        run_backtest(_path([100.0] * 5), _toy(leverage=4), "synthetic", 86400, synthetic=True, synthetic_signal_override=[False] * 5)


def test_wallet_csv_does_not_invent_pnl(tmp_path, monkeypatch):
    monkeypatch.setattr("ymzz_quant.wallets.book_path", lambda root: tmp_path / "book.json")
    added = add_address(tmp_path, "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", "sample")
    assert added["ok"] is True
    rejected = add_address(tmp_path, "not an address", "x")
    assert rejected["ok"] is False
    text = "timestamp_utc,kind,base_amount,quote_amount,quote_symbol,tx,note\n2026-01-01T00:00:00Z,transfer,1,2,SOL,sig,move\n"
    parsed = parse_activity_csv(text)
    assert parsed["rows"][0]["is_trade"] is False
    assert parsed["rows"][0]["pnl_usd"] is None
    secret = "timestamp_utc,kind,base_amount,quote_amount,quote_symbol,tx,note\n2026-01-01T00:00:00Z,buy,1,2,SOL,sig,private_key\n"
    assert parse_activity_csv(secret)["ok"] is False


def test_http_round_trip_is_stateless():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ResearchHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        first = _post(port, "/api/backtest", _request())
        second = _post(port, "/api/backtest", _use(_request(rsi_period=19), "eth_usd_1h"))
        denied = _post(port, "/api/backtest", _request(leverage=9))
    finally:
        server.shutdown()
    assert first["provenance"]["symbol"] == "BTC/USD"
    assert second["provenance"]["symbol"] == "ETH/USD"
    assert second["metrics"]["rsi_period"] == 19
    assert second["provenance"]["sha256"] != first["provenance"]["sha256"]
    assert denied["ok"] is False
    assert ROOT.joinpath("frontend/index.html").exists()


def _post(port, path, payload):
    raw = json.dumps(payload).encode()
    connection = HTTPConnection("127.0.0.1", port, timeout=30)
    connection.request("POST", path, body=raw, headers={"Content-Type": "application/json", "Content-Length": str(len(raw))})
    response = connection.getresponse()
    body = json.loads(response.read().decode())
    connection.close()
    return body
