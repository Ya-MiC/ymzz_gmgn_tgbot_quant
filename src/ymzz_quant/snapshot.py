"""Offline HTML for one finished response. The page does not recompute."""

from __future__ import annotations

import json


def render_snapshot(payload: dict) -> str:
    embedded = {
        key: value
        for key, value in payload.items()
        if key not in {"snapshot_html", "report_markdown", "ledger_csv"}
    }
    data = json.dumps(embedded, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>研究快照</title>
<style>
body {{ font-family: sans-serif; margin: 24px; background: #161616; color: #f2f2f2; }}
.banner {{ background: #5c4308; color: #fff8e8; padding: 12px 16px; }}
table {{ border-collapse: collapse; margin-top: 16px; }}
td, th {{ border: 1px solid #444; padding: 6px 10px; text-align: left; }}
</style>
</head>
<body>
<p class="banner">這是快照。頁面只顯示內嵌的那一次結果，不會連線，也不會重算。要改設定請用本機研究頁。</p>
<h1 id="title"></h1>
<table id="facts"></table>
<pre id="warnings"></pre>
<script id="payload" type="application/json">{data}</script>
<script>
const payload = JSON.parse(document.getElementById("payload").textContent);
const p = payload.provenance;
const m = payload.metrics;
document.getElementById("title").textContent = p.symbol + " · " + p.interval + " · " + p.marketplace;
const rows = [
  ["來源", p.source_url],
  ["sha256", p.sha256],
  ["抓取", p.fetched_at_utc],
  ["網路", p.network],
  ["報價 / 單位", p.quote + " · " + p.unit],
  ["代號或池", p.pair],
  ["已收盤", String(p.closed_bars)],
  ["RSI 周期", String(m.rsi_period)],
  ["模式 / 倍數", m.instrument_mode + " / " + m.leverage_used],
  ["期末權益", String(m.final_equity_usd)],
  ["已平倉筆數", String(m.closed_trade_count)]
];
document.getElementById("facts").innerHTML = rows.map(row => "<tr><th>" + row[0] + "</th><td>" + row[1] + "</td></tr>").join("");
document.getElementById("warnings").textContent = payload.warnings.join("\\n");
</script>
</body>
</html>
"""
