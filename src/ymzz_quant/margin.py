"""Hypothetical margin accounting.

Spot and GMGN-style swaps do not use this module. It is not a perpetual
exchange backtest: borrow, funding, maintenance, and liquidation penalty are
caller-supplied assumptions. Equity is cash plus mark minus borrowed funds.
It is not an unlevered return multiplied by leverage.
"""

from __future__ import annotations

ALLOWED_LEVERAGE = (1.0, 1.5, 2.0)


def leverage_allowed(value: float) -> bool:
    return any(abs(float(value) - item) < 1e-9 for item in ALLOWED_LEVERAGE)


def posted_and_borrowed(notional: float, leverage: float) -> tuple[float, float]:
    if leverage <= 0:
        raise ValueError("leverage")
    posted = notional / leverage
    return posted, notional - posted


def account_equity(cash: float, qty: float, price: float, borrowed: float) -> float:
    return cash + qty * price - borrowed


def margin_level(cash: float, qty: float, price: float, borrowed: float) -> float | None:
    position_value = qty * price
    if position_value <= 0:
        return None
    return account_equity(cash, qty, price, borrowed) / position_value


def financing_cost(
    borrowed: float,
    position_value: float,
    borrow_rate_per_day: float,
    funding_rate_per_day: float,
    interval_seconds: int,
) -> float:
    day_frac = interval_seconds / 86400.0
    return borrowed * borrow_rate_per_day * day_frac + position_value * funding_rate_per_day * day_frac
