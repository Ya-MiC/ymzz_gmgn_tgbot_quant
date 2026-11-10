"""Datasets actually fetched for this run. Paths are public cache files, not invented series."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATASETS = {
    "wif_daily": {
        "role": "selected_survivor_meme",
        "role_zh": "選定的倖存 meme 池（探索，不是全市場）",
        "symbol": "$WIF / SOL",
        "chain": "solana",
        "dex": "raydium",
        "pool": "EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx",
        "base_token": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "quote_token": "So11111111111111111111111111111111111111112",
        "files": [
            "data/cache/gt_ohlcv_day_before_EP2ib6dY.json",
            "data/cache/gt_ohlcv_day_EP2ib6dY.json",
        ],
        "expected_interval_seconds": 86400,
        "interval_label": "1d",
        "source_template": "https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/day?aggregate=1&limit=1000&currency=usd",
        "bias": "Survivor and selected-pool bias. Chosen by exact ticker, pool age before 2026-05-01, then longest coverage, then higher reserve. Not chosen by return. Dead pools absent from search are missing.",
        "bias_zh": "倖存者與選定池偏差。先對名稱、池齡、覆蓋長度與儲備排序，沒有用報酬挑選。已經消失的池不會出現在搜尋裡。",
    },
    "sol_usdc_daily": {
        "role": "plumbing_baseline_not_meme",
        "role_zh": "主流 SOL/USDC 管線基準，不可當成 meme 績效",
        "symbol": "SOL / USDC",
        "chain": "solana",
        "dex": "orca",
        "pool": "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE",
        "base_token": "So11111111111111111111111111111111111111112",
        "quote_token": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "files": ["data/cache/gt_ohlcv_day_Czfq3xZZ.json"],
        "expected_interval_seconds": 86400,
        "interval_label": "1d",
        "source_template": "https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/day?aggregate=1&limit=1000&currency=usd",
        "bias": "Deep major pair. Plumbing only.",
        "bias_zh": "深度主流交易對，只做管線基準，不能當成 meme 績效。",
    },
    "bonk_daily_appendix": {
        "role": "predeclared_appendix_not_used_for_selection",
        "role_zh": "附錄：同一規則的 BONK 池，沒有用來挑選主池",
        "symbol": "Bonk / SOL",
        "chain": "solana",
        "dex": "unspecified_in_selection_file",
        "pool": "5zpyutJu9ee6jFymDGoK7F6S5Kczqtc9FomP3ueKuyA9",
        "base_token": None,
        "quote_token": "So11111111111111111111111111111111111111112",
        "files": ["data/cache/gt_ohlcv_day_5zpyutJu.json"],
        "expected_interval_seconds": 86400,
        "interval_label": "1d",
        "source_template": "https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/day?aggregate=1&limit=1000&currency=usd",
        "bias": "Same survivor search. Not the reserve tie-break winner. First page only.",
        "bias_zh": "同一個預先宣告的搜尋，不是儲備數最高的那一池。只有第一頁日線。",
    },
    "popcat_daily_appendix": {
        "role": "predeclared_appendix_not_used_for_selection",
        "role_zh": "附錄：同一規則的 POPCAT/SOL 池，沒有用來挑選主池",
        "symbol": "POPCAT / SOL",
        "chain": "solana",
        "dex": "unspecified_in_selection_file",
        "pool": "FRhB8L7Y9Qq41qZXYLtC2nw8An1RJfLLxRF2x9RwLLMo",
        "base_token": None,
        "quote_token": "So11111111111111111111111111111111111111112",
        "files": ["data/cache/gt_ohlcv_day_FRhB8L7Y.json"],
        "expected_interval_seconds": 86400,
        "interval_label": "1d",
        "source_template": "https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/day?aggregate=1&limit=1000&currency=usd",
        "bias": "Mature POPCAT/SOL. A newer POPCAT/USDC pool was rejected for age, not for return.",
        "bias_zh": "較早建立的 POPCAT/SOL。另一個較新的 POPCAT/USDC 因池齡被排除，不是因為報酬。",
    },
}


def dataset_paths(key: str, root: Path | None = None) -> list[Path]:
    root = root or ROOT
    spec = DATASETS[key]
    return [root / rel for rel in spec["files"]]
