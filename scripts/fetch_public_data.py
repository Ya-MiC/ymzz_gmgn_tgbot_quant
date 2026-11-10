#!/usr/bin/env python3
"""Fetch keyless public history for this research run.

GeckoTerminal calls are serialized with a conservative gap (default 13s,
about 4.6/min) because published keyless limits conflict (about 5/min vs
about 10/min). Responses are stored exactly as returned, plus a sidecar meta
file. This script does not compute strategy returns.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
KST = ZoneInfo("Asia/Seoul")
GT = "https://api.geckoterminal.com/api/v2"
MIN_INTERVAL_S = 13.0
UA = "ymzz-quant-research/0.1 (paper backtest; attribution: Powered by CoinGecko)"

# Selection is declared before any OHLCV is read. Ranking uses reserve only.
# These names are survivors that still trade; that bias is intentional and labelled.
PREDECLARED_MEME_QUERIES = ("bonk", "wif", "popcat")
MIN_DAILY_BARS = 60
MIN_SPAN_DAYS = 21
# Maturity cutoff is the day before the keyless window we expect to measure.
# Pools created inside that window are not "mature multi-week history" candidates.
MATURE_BEFORE = "2026-05-01T00:00:00Z"
EXACT_NAME = {
    "bonk": re.compile(r"(?i)^bonk / (sol|wsol|usdc|usdt)$"),
    "wif": re.compile(r"(?i)^\$?wif / (sol|wsol|usdc|usdt)$"),
    "popcat": re.compile(r"(?i)^popcat / (sol|wsol|usdc|usdt)$"),
}
MAJOR_POOL = "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE"

_last_gt = 0.0


def now_stamps() -> dict:
    utc = datetime.now(timezone.utc)
    kst = utc.astimezone(KST)
    return {
        "fetched_at_utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fetched_at_kst": kst.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def http_get(url: str, headers: dict | None = None, timeout: int = 60) -> tuple[int, dict, bytes]:
    hdrs = {"Accept": "application/json", "User-Agent": UA}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        info = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status, info, body


def gt_get(url: str) -> tuple[int, bytes]:
    global _last_gt
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_gt)
    if _last_gt and wait > 0:
        time.sleep(wait)
    delay = MIN_INTERVAL_S
    last_err = None
    for attempt in range(5):
        try:
            status, hdrs, body = http_get(
                url,
                headers={"Accept": "application/json;version=20230203"},
            )
            _last_gt = time.monotonic()
            if status == 429 or status == 503:
                retry = float(hdrs.get("retry-after") or delay)
                time.sleep(max(retry, delay))
                delay *= 2
                continue
            return status, body
        except urllib.error.HTTPError as exc:
            _last_gt = time.monotonic()
            err_body = exc.read()
            last_err = exc
            print(f"HTTP {exc.code} {url} body={err_body[:300]!r}")
            if exc.code in (429, 503):
                retry = float(exc.headers.get("Retry-After") or delay)
                time.sleep(max(retry, delay))
                delay *= 2
                continue
            raise RuntimeError(f"GeckoTerminal HTTP {exc.code} for {url}: {err_body[:300]!r}") from exc
        except urllib.error.URLError as exc:
            _last_gt = time.monotonic()
            last_err = exc
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"GeckoTerminal failed for {url}: {last_err}")


def save_raw(name: str, url: str, body: bytes, extra: dict | None = None) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    path.write_bytes(body)
    meta = {
        "url": url,
        "bytes": len(body),
        "sha256": sha256(body),
        "file": str(path.relative_to(ROOT)),
        **now_stamps(),
    }
    if extra:
        meta.update(extra)
    (CACHE / (name + ".meta.json")).write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"saved {name} {len(body)} {meta['sha256'][:12]} {meta['fetched_at_utc']}")
    return path


def pool_address_from_id(pool_id: str) -> str:
    # "solana_<address>"
    if "_" in pool_id:
        return pool_id.split("_", 1)[1]
    return pool_id


def summarize_pool(item: dict) -> dict:
    attr = item.get("attributes") or {}
    base = (attr.get("base_token") or {}) if isinstance(attr.get("base_token"), dict) else {}
    # search payload nests tokens under relationships sometimes; keep both
    rel = item.get("relationships") or {}
    return {
        "id": item.get("id"),
        "name": attr.get("name"),
        "address": attr.get("address") or pool_address_from_id(item.get("id") or ""),
        "reserve_in_usd": _float(attr.get("reserve_in_usd")),
        "pool_created_at": attr.get("pool_created_at"),
        "base_token_symbol": (attr.get("base_token_symbol") or base.get("symbol")),
        "quote_token_symbol": attr.get("quote_token_symbol"),
        "base_token_address": attr.get("base_token_address") or base.get("address"),
        "quote_token_address": attr.get("quote_token_address"),
        "dex": ((rel.get("dex") or {}).get("data") or {}).get("id"),
        "price_change_percentage": None,  # deliberately not copied; not a selection input
    }


def _float(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def ohlcv_stats(body: bytes) -> dict:
    payload = json.loads(body)
    rows = (((payload.get("data") or {}).get("attributes") or {}).get("ohlcv_list")) or []
    if not rows:
        return {"bars": 0}
    # API returns newest first. Do not compute returns here beyond span.
    stamps = [int(r[0]) for r in rows]
    return {
        "bars": len(rows),
        "newest_ts": max(stamps),
        "oldest_ts": min(stamps),
        "newest_utc": datetime.fromtimestamp(max(stamps), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "oldest_utc": datetime.fromtimestamp(min(stamps), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "span_days": round((max(stamps) - min(stamps)) / 86400, 3),
    }


def fetch_ohlcv(address: str, timeframe: str, limit: int = 1000, aggregate: int = 1) -> bytes:
    url = (
        f"{GT}/networks/solana/pools/{address}/ohlcv/{timeframe}"
        f"?aggregate={aggregate}&limit={limit}&currency=usd&include_empty_intervals=false"
    )
    status, body = gt_get(url)
    if status != 200:
        raise RuntimeError(f"ohlcv {address} status {status}")
    save_raw(
        f"gt_ohlcv_{timeframe}_{address[:8]}.json",
        url,
        body,
        {"status": status, "pool": address, "timeframe": timeframe, "aggregate": aggregate},
    )
    return body


def main() -> None:
    criteria = {
        "declared_before_ohlcv": True,
        "purpose": "exploratory survivor pool, not a point-in-time universe and not meme-market performance",
        "queries": list(PREDECLARED_MEME_QUERIES),
        "why_these_names": (
            "BONK, WIF, and POPCAT are widely known Solana meme tokens that began trading "
            "well before this keyless window. They are selected because a multi-week history "
            "is plausible, not because of any return. Pools that already died and left the "
            "search index cannot appear. This is survivorship plus selected-pool bias."
        ),
        "rank": "highest reserve_in_usd only; price_change_percentage is ignored and not stored",
        "exact_name": "base name must match BONK, $WIF/WIF, or POPCAT versus SOL/WSOL/USDC/USDT; fuzzy search hits are rejected",
        "mature_pool_created_before": MATURE_BEFORE,
        "quote_allow": ["SOL", "WSOL", "USDC", "USDT"],
        "exclude_pool": MAJOR_POOL,
        "qualify": {"min_daily_bars": MIN_DAILY_BARS, "min_span_days": MIN_SPAN_DAYS},
        "among_qualified": "longest span_days, tie-break higher reserve_in_usd",
        "major_pair_role": "plumbing baseline only; must not be reported as meme performance",
        **now_stamps(),
    }
    (CACHE / "selection_criteria.json").write_text(
        json.dumps(criteria, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("wrote selection criteria before OHLCV")

    # SOL/USD snapshot from CoinGecko keyless (separate host, not GT-limited).
    sol_url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
    status, _, body = http_get(sol_url)
    save_raw("coingecko_sol_usd.json", sol_url, body, {"status": status})

    major_url = f"{GT}/networks/solana/pools/{MAJOR_POOL}"
    status, body = gt_get(major_url)
    save_raw("gt_pool_sol_usdc.json", major_url, body, {"status": status, "role": "plumbing_baseline"})
    fetch_ohlcv(MAJOR_POOL, "day", limit=1000, aggregate=1)

    candidates = []
    for query in PREDECLARED_MEME_QUERIES:
        url = f"{GT}/search/pools?query={query}&network=solana"
        status, body = gt_get(url)
        save_raw(f"gt_search_{query}.json", url, body, {"status": status, "query": query})
        top = top_exact_candidate(query, json.loads(body))
        if top is None:
            print("no exact mature candidate for", query)
            continue
        candidates.append(top)
        print("top", query, top["name"], top["address"], top["reserve_in_usd"])

    chosen = qualify_and_write(candidates, fetch_missing=True)
    finish_after_choice(chosen)


def top_exact_candidate(query: str, payload: dict) -> dict | None:
    pools = []
    rejected = []
    for item in payload.get("data") or []:
        row = summarize_pool(item)
        row["query"] = query
        name = row.get("name") or ""
        created = row.get("pool_created_at") or ""
        if not EXACT_NAME[query].match(name.strip()):
            rejected.append({"name": name, "reason": "fuzzy_or_different_ticker"})
            continue
        if created and created >= MATURE_BEFORE:
            rejected.append({"name": name, "address": row["address"], "reason": "created_inside_or_after_window", "pool_created_at": created})
            continue
        if row["reserve_in_usd"] is None:
            rejected.append({"name": name, "reason": "missing_reserve"})
            continue
        pools.append(row)
    pools.sort(key=lambda r: r["reserve_in_usd"], reverse=True)
    if not pools:
        return None
    top = pools[0]
    top["search_rank_by_reserve"] = 1
    top["exact_match_count"] = len(pools)
    top["rejected_examples"] = rejected[:8]
    return top


def qualify_and_write(candidates: list[dict], fetch_missing: bool) -> dict | None:
    qualified = []
    for top in candidates:
        path = CACHE / f"gt_ohlcv_day_{top['address'][:8]}.json"
        if path.exists() and not fetch_missing:
            body = path.read_bytes()
        elif path.exists() and top["address"].startswith("EP2ib6dY"):
            body = path.read_bytes()
            print("reuse cached", path.name)
        else:
            body = fetch_ohlcv(top["address"], "day", limit=1000, aggregate=1)
        stats = ohlcv_stats(body)
        top["daily"] = stats
        print("stats", top["name"], stats)
        if stats.get("bars", 0) >= MIN_DAILY_BARS and stats.get("span_days", 0) >= MIN_SPAN_DAYS:
            qualified.append(top)
    qualified.sort(key=lambda r: (r["daily"]["span_days"], r["reserve_in_usd"]), reverse=True)
    chosen = qualified[0] if qualified else None
    decision = {
        "criteria_file": "data/cache/selection_criteria.json",
        "correction": (
            "The first automated pass accepted fuzzy search hits (BERN ranked above Bonk). "
            "That pass is rejected. This decision uses exact ticker names and pool_created_at "
            "before 2026-05-01. Strategy returns were not computed before this correction."
        ),
        "rejected_false_positive_pool": {
            "name": "BERN / SOL",
            "address": "Ebbpz3PWLaQxj2oyK967RgEPbcPypjQCoZ3tpB4fwLsk",
            "reason": "fuzzy search for bonk; not the BONK token",
        },
        "candidates_top_by_reserve": candidates,
        "qualified": [
            {"address": c["address"], "name": c["name"], "span_days": c["daily"]["span_days"], "bars": c["daily"]["bars"]}
            for c in qualified
        ],
        "chosen": chosen,
        "insufficient": chosen is None,
        "note": (
            "History length is a coverage filter declared before returns. "
            "It is not a performance filter. Price returns are not computed in this script."
        ),
        **now_stamps(),
    }
    (CACHE / "meme_pool_decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("CHOSEN", None if not chosen else chosen["address"], "insufficient" if not chosen else "ok")
    return chosen


def finish_after_choice(chosen: dict | None) -> None:
    if chosen:
        # One extra daily page via before_timestamp to see whether keyless history
        # stops near 6 months. Not used to change the selection.
        oldest = chosen["daily"]["oldest_ts"]
        url = (
            f"{GT}/networks/solana/pools/{chosen['address']}/ohlcv/day"
            f"?aggregate=1&limit=1000&currency=usd&before_timestamp={oldest}"
        )
        try:
            status, body = gt_get(url)
            save_raw(
                f"gt_ohlcv_day_before_{chosen['address'][:8]}.json",
                url,
                body,
                {"status": status, "purpose": "probe_whether_keyless_history_extends_before_first_page"},
            )
            probe = {"stats": ohlcv_stats(body), "status": status}
        except Exception as exc:
            probe = {"error": str(exc), "note": "probe failed; first page remains the keyless sample"}
            print("before_timestamp probe failed", exc)
        (CACHE / "meme_before_timestamp_probe.json").write_text(
            json.dumps({"url": url, **probe, **now_stamps()}, indent=2) + "\n",
            encoding="utf-8",
        )
        print("before_timestamp probe", probe)

        pool_url = f"{GT}/networks/solana/pools/{chosen['address']}"
        status, body = gt_get(pool_url)
        save_raw(
            f"gt_pool_meme_{chosen['address'][:8]}.json",
            pool_url,
            body,
            {"status": status, "role": "selected_survivor_meme_pool"},
        )
        trades_url = f"{GT}/networks/solana/pools/{chosen['address']}/trades?trade_volume_in_usd_greater_than=0"
        try:
            status, body = gt_get(trades_url)
            save_raw(
                f"gt_trades_head_{chosen['address'][:8]}.json",
                trades_url,
                body,
                {
                    "status": status,
                    "role": "public_swap_scaffold_not_wallet_pnl",
                    "note": "Recent pool swaps only. Not wallet profit. Transfers are absent.",
                },
            )
        except Exception as exc:
            (CACHE / "gt_trades_error.txt").write_text(str(exc), encoding="utf-8")
            print("trades skipped", exc)

    # Polymarket probability history. Separate regime. Token chosen as the first
    # open Gamma market at fetch time (selection bias recorded; not a token price).
    gamma_url = "https://gamma-api.polymarket.com/markets?closed=false&limit=1"
    status, _, body = http_get(gamma_url)
    save_raw("polymarket_gamma_one_open_market.json", gamma_url, body, {"status": status})
    market = json.loads(body)[0]
    token_ids = json.loads(market["clobTokenIds"]) if isinstance(market["clobTokenIds"], str) else market["clobTokenIds"]
    token = token_ids[0]
    # Docs: token_id is required (tokenId alias). interval=max is whole-life 12h buckets.
    cursor = None
    pages = []
    for page_i in range(1, 8):
        hist_url = (
            "https://data-api.polymarket.com/v2/prices-history"
            f"?token_id={token}&interval=max&limit=1000"
        )
        if cursor:
            hist_url += "&cursor=" + urllib.parse.quote(cursor, safe="")
        status, hdrs, body = http_get(hist_url)
        save_raw(
            f"polymarket_prices_history_page{page_i}.json",
            hist_url,
            body,
            {
                "status": status,
                "token_id": token,
                "question": market.get("question"),
                "condition_id": market.get("conditionId"),
                "trace_id": hdrs.get("x-trace-id"),
                "note": "probability in 0..1; first open Gamma market at fetch time; selection bias",
            },
        )
        payload = json.loads(body)
        pages.append(payload)
        pagination = payload.get("pagination") or {}
        cursor = pagination.get("next_cursor")
        print(
            "polymarket page",
            page_i,
            "rows",
            len(payload.get("data") or []),
            "has_more",
            pagination.get("has_more"),
            "cursor",
            bool(cursor),
        )
        if not cursor or pagination.get("has_more") is False:
            break
    (CACHE / "polymarket_market_ref.json").write_text(
        json.dumps(
            {
                "question": market.get("question"),
                "condition_id": market.get("conditionId"),
                "token_id_yes": token,
                "outcomes": market.get("outcomes"),
                "enable_order_book": market.get("enableOrderBook"),
                "selection": "first closed=false Gamma market at fetch time; not a strategy universe",
                "pages": len(pages),
                **now_stamps(),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def continue_from_cache() -> None:
    """Reselect from search responses already saved. Does not recompute returns."""
    criteria_path = CACHE / "selection_criteria.json"
    criteria = json.loads(criteria_path.read_text(encoding="utf-8"))
    criteria["exact_name"] = (
        "base name must match BONK, $WIF/WIF, or POPCAT versus SOL/WSOL/USDC/USDT; fuzzy search hits are rejected"
    )
    criteria["mature_pool_created_before"] = MATURE_BEFORE
    criteria["tightened_at"] = now_stamps()
    criteria_path.write_text(json.dumps(criteria, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    candidates = []
    for query in PREDECLARED_MEME_QUERIES:
        payload = json.loads((CACHE / f"gt_search_{query}.json").read_text(encoding="utf-8"))
        top = top_exact_candidate(query, payload)
        if top is None:
            print("no exact mature candidate for", query)
            continue
        candidates.append(top)
        print("top", query, top["name"], top["address"], top["reserve_in_usd"], top.get("pool_created_at"))
    chosen = qualify_and_write(candidates, fetch_missing=True)
    finish_after_choice(chosen)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--continue":
        continue_from_cache()
    else:
        main()
