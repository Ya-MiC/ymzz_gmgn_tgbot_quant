"""Read-only wallet notes. This is not a tracker and it does not compute PnL."""

from __future__ import annotations

import json
import re
from pathlib import Path

CSV_COLUMNS = ("timestamp_utc", "kind", "base_amount", "quote_amount", "quote_symbol", "tx", "note")
KINDS = {"buy", "sell", "transfer", "deposit", "withdrawal", "unknown"}
NOT_IMPLEMENTED = [
    "有資金證明的聰明錢分類",
    "熱門地址的新進資金",
    "歷史可賣性",
    "第一波偵測",
    "把鏈上轉帳解讀成成交",
    "把淨入金當成損益",
]
ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def schema() -> dict:
    return {
        "status": "data_required",
        "live_parser": False,
        "network_lookup_in_this_service": False,
        "csv_columns": list(CSV_COLUMNS),
        "kinds": sorted(KINDS),
        "pnl_usd": None,
        "not_implemented": NOT_IMPLEMENTED,
        "example": "timestamp_utc,kind,base_amount,quote_amount,quote_symbol,tx,note\n2026-01-01T00:00:00Z,transfer,1,0,SOL,signature,not a trade\n",
        "note": "公開 RPC 即使回傳簽章，那些簽章也不是成交。這個服務在回測與測試時不會去呼叫 RPC。",
    }


def book_path(root: Path) -> Path:
    return root / "data" / "local" / "address_book.json"


def load_book(root: Path) -> list[dict]:
    path = book_path(root)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("address book")
    return payload


def save_book(root: Path, rows: list[dict]) -> None:
    path = book_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _check_address(address: str) -> str | None:
    if not isinstance(address, str) or not ADDRESS_RE.fullmatch(address):
        return "地址需為 32 到 44 碼的公開地址"
    if len(address) > 50:
        return "拒絕看起來像私鑰的內容"
    return None


def add_address(root: Path, address: str, label: str) -> dict:
    message = _check_address(address)
    if message:
        return {"ok": False, "errors": [{"field": "address", "message": message}]}
    if not isinstance(label, str) or not label.strip() or len(label) > 80:
        return {"ok": False, "errors": [{"field": "label", "message": "標籤需要 1 到 80 字"}]}
    rows = [row for row in load_book(root) if row["address"] != address]
    rows.append({"address": address, "label": label.strip(), "network": "solana", "read_only": True})
    save_book(root, rows)
    return {"ok": True, "addresses": rows, "not_implemented": NOT_IMPLEMENTED}


def remove_address(root: Path, address: str) -> dict:
    rows = [row for row in load_book(root) if row["address"] != address]
    save_book(root, rows)
    return {"ok": True, "addresses": rows, "not_implemented": NOT_IMPLEMENTED}


def parse_activity_csv(text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "errors": [{"field": "csv", "message": "CSV 是空的"}]}
    lowered = text.lower()
    for banned in ("private_key", "seed", "secret", "pnl_usd", "profit"):
        if banned in lowered:
            return {"ok": False, "errors": [{"field": "csv", "message": f"不接受欄位或內容 {banned}"}]}
    lines = [line for line in text.splitlines() if line.strip()]
    header = [part.strip() for part in lines[0].split(",")]
    if header != list(CSV_COLUMNS):
        return {"ok": False, "errors": [{"field": "csv", "message": "表頭必須是 " + ",".join(CSV_COLUMNS)}]}
    rows = []
    errors = []
    for index, line in enumerate(lines[1:], start=2):
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != len(CSV_COLUMNS):
            errors.append({"field": "csv", "message": f"第 {index} 列欄數不對"})
            continue
        item = dict(zip(CSV_COLUMNS, parts))
        if item["kind"] not in KINDS:
            errors.append({"field": "kind", "message": f"第 {index} 列 kind 不在允許清單"})
            continue
        is_trade = item["kind"] in {"buy", "sell"}
        rows.append(
            {
                **item,
                "is_trade": is_trade,
                "pnl_usd": None,
                "classification": "user_declared_swap" if is_trade else "not_a_trade",
            }
        )
    if errors:
        return {"ok": False, "errors": errors}
    return {
        "ok": True,
        "rows": rows,
        "pnl_computed": False,
        "not_implemented": NOT_IMPLEMENTED,
        "note": "buy/sell 只代表這份 CSV 自己這樣標。轉帳、入金、出金不是交易。這一模組不計算損益。",
    }
