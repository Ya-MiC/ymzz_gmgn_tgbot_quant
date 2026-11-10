"""Cost scenarios. Unknown pool fees stay unknown; they are never filled with zero."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CostScenario:
    name: str
    label_zh: str
    gmgn_fee_rate_per_side: float
    pool_fee_rate_per_side: float | None
    pool_fee_status: str
    chain_cost_sol_per_side: float
    chain_cost_note: str
    slip_bp_buy: float
    slip_bp_sell: float
    slip_note: str
    wallet_reserve_sol: float
    sol_usd: float
    sol_usd_fetched_at_utc: str
    sol_usd_fetched_at_kst: str
    sol_usd_source: str
    initial_cash_usd: float
    proposed_per_trade_loss_budget_usd: float
    proposed_max_drawdown_frac: float
    require_known_pool_fee: bool
    require_historical_sellability: bool
    require_historical_liquidity: bool
    historical_sellability_known: bool
    historical_liquidity_known: bool
    execution_mode: str
    no_reentry: bool
    k_sl: float
    k_tp: float
    rsi_low: float
    rsi_high: float
    rsi_exit: float
    rv_min: float
    atr_quantile_low: float = 0.20
    atr_quantile_high: float = 0.90
    min_notional_usd: float = 1.0

    @property
    def chain_fee_usd_per_side(self) -> float:
        return self.chain_cost_sol_per_side * self.sol_usd

    @property
    def reserve_usd(self) -> float:
        return self.wallet_reserve_sol * self.sol_usd

    @property
    def pool_fee_is_assumed(self) -> bool:
        return self.pool_fee_status.upper().startswith("ASSUMED")

    @property
    def pool_fee_is_verified(self) -> bool:
        return False

    def to_public_dict(self) -> dict:
        return {
            "name": self.name,
            "label_zh": self.label_zh,
            "gmgn_fee_rate_per_side": self.gmgn_fee_rate_per_side,
            "pool_fee_rate_per_side": self.pool_fee_rate_per_side,
            "pool_fee_status": self.pool_fee_status,
            "pool_fee_is_verified": False,
            "pool_fee_is_assumed": self.pool_fee_is_assumed,
            "chain_cost_sol_per_side": self.chain_cost_sol_per_side,
            "chain_fee_usd_per_side": self.chain_fee_usd_per_side,
            "chain_cost_note": self.chain_cost_note,
            "slip_bp_buy": self.slip_bp_buy,
            "slip_bp_sell": self.slip_bp_sell,
            "slip_note": self.slip_note,
            "wallet_reserve_sol": self.wallet_reserve_sol,
            "reserve_usd_at_snapshot": self.reserve_usd,
            "sol_usd": self.sol_usd,
            "sol_usd_fetched_at_utc": self.sol_usd_fetched_at_utc,
            "sol_usd_fetched_at_kst": self.sol_usd_fetched_at_kst,
            "sol_usd_source": self.sol_usd_source,
            "initial_cash_usd": self.initial_cash_usd,
            "proposed_per_trade_loss_budget_usd": self.proposed_per_trade_loss_budget_usd,
            "proposed_per_trade_loss_budget_is_user_specified": False,
            "proposed_max_drawdown_frac": self.proposed_max_drawdown_frac,
            "proposed_max_drawdown_is_user_specified": False,
            "execution_mode": self.execution_mode,
            "require_known_pool_fee": self.require_known_pool_fee,
            "require_historical_sellability": self.require_historical_sellability,
            "require_historical_liquidity": self.require_historical_liquidity,
            "historical_sellability_known": self.historical_sellability_known,
            "historical_liquidity_known": self.historical_liquidity_known,
            "budget_gate_disabled": False,
            "no_reentry": self.no_reentry,
            "no_reentry_role": "provisional_setting_not_a_fourth_indicator",
            "no_reentry_effect": (
                "After the first exit, every later entry on this pool is blocked for the rest of the run, "
                "including validation and held-out. That suppression is deliberate and provisional. "
                "It is not first-wave detection and it is not a validated out-of-sample strategy."
            ),
            "k_sl": self.k_sl,
            "k_tp": self.k_tp,
            "rsi_low": self.rsi_low,
            "rsi_high": self.rsi_high,
            "rsi_exit": self.rsi_exit,
            "rv_min": self.rv_min,
            "indicators": ["RSI14", "ATR14_pct", "relative_volume_20"],
            "leverage": 1,
            "martingale": False,
            "averaging_down": False,
            "replenishment": False,
        }


def load_sol_snapshot(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    meta_path = Path(str(path) + ".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    usd = payload["solana"]["usd"]
    if not isinstance(usd, (int, float)) or usd <= 0:
        raise ValueError("SOL snapshot missing a positive usd price")
    return {
        "sol_usd": float(usd),
        "fetched_at_utc": meta.get("fetched_at_utc", "unknown"),
        "fetched_at_kst": meta.get("fetched_at_kst", "unknown"),
        "source": meta.get("url", "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"),
        "sha256": meta.get("sha256"),
    }


def scenario_from_dict(name: str, raw: dict, sol: dict) -> CostScenario:
    if raw.get("initial_cash_usd") != 10:
        raise ValueError("v0 initial cash is $10")
    if raw.get("gmgn_fee_rate_per_side") is None:
        raise ValueError("GMGN fee must be explicit")
    return CostScenario(
        name=name,
        label_zh=raw["label_zh"],
        gmgn_fee_rate_per_side=float(raw["gmgn_fee_rate_per_side"]),
        pool_fee_rate_per_side=None if raw.get("pool_fee_rate_per_side") is None else float(raw["pool_fee_rate_per_side"]),
        pool_fee_status=raw["pool_fee_status"],
        chain_cost_sol_per_side=float(raw["chain_cost_sol_per_side"]),
        chain_cost_note=raw["chain_cost_note"],
        slip_bp_buy=float(raw["slip_bp_buy"]),
        slip_bp_sell=float(raw["slip_bp_sell"]),
        slip_note=raw["slip_note"],
        wallet_reserve_sol=float(raw["wallet_reserve_sol"]),
        sol_usd=float(sol["sol_usd"]),
        sol_usd_fetched_at_utc=sol["fetched_at_utc"],
        sol_usd_fetched_at_kst=sol["fetched_at_kst"],
        sol_usd_source=sol["source"],
        initial_cash_usd=float(raw["initial_cash_usd"]),
        proposed_per_trade_loss_budget_usd=float(raw["proposed_per_trade_loss_budget_usd"]),
        proposed_max_drawdown_frac=float(raw["proposed_max_drawdown_frac"]),
        require_known_pool_fee=bool(raw["require_known_pool_fee"]),
        require_historical_sellability=bool(raw["require_historical_sellability"]),
        require_historical_liquidity=bool(raw["require_historical_liquidity"]),
        historical_sellability_known=bool(raw["historical_sellability_known"]),
        historical_liquidity_known=bool(raw["historical_liquidity_known"]),
        execution_mode=raw["execution_mode"],
        no_reentry=bool(raw["no_reentry"]),
        k_sl=float(raw["k_sl"]),
        k_tp=float(raw["k_tp"]),
        rsi_low=float(raw["rsi_low"]),
        rsi_high=float(raw["rsi_high"]),
        rsi_exit=float(raw["rsi_exit"]),
        rv_min=float(raw["rv_min"]),
        atr_quantile_low=float(raw.get("atr_quantile_low", 0.20)),
        atr_quantile_high=float(raw.get("atr_quantile_high", 0.90)),
        min_notional_usd=float(raw.get("min_notional_usd", 1.0)),
    )


def load_scenarios(config_path: Path, root: Path) -> dict[str, CostScenario]:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    sol = load_sol_snapshot(root / raw["sol_usd_snapshot_file"])
    return {name: scenario_from_dict(name, body, sol) for name, body in raw["scenarios"].items()}
