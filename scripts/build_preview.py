#!/usr/bin/env python3
"""Self-contained HTML preview. Charts are inline SVG of the cached public series."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ymzz_quant.data_adapters import fmt_ts  # noqa: E402
from ymzz_quant.service import load_bars, polymarket_summary, recent_swaps  # noqa: E402

RUNS = ROOT / "results" / "runs.json"


def main() -> None:
    if not RUNS.exists():
        raise SystemExit("missing results/runs.json — run scripts/run_backtest.py first; no chart was invented")
    payload = json.loads(RUNS.read_text(encoding="utf-8"))
    bars, meta = load_bars("wif_daily", ROOT)
    conservative = payload["runs"]["wif_daily|conservative_no_trade"]
    explor = payload["runs"]["wif_daily|exploratory_ohlcv_only"]
    poly = polymarket_summary(ROOT)
    swaps = recent_swaps(ROOT)
    page = render_page(payload, bars, meta, conservative, explor, poly, swaps)
    out = ROOT / "preview" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print("wrote", out, "bytes", out.stat().st_size)


def render_page(payload, bars, meta, conservative, explor, poly, swaps) -> str:
    m = explor["metrics"]
    c = conservative["metrics"]
    trade = explor["trades"][0] if explor["trades"] else None
    candle = svg_candles(bars, explor["trades"])
    equity = svg_lines(
        [row["equity"] for row in explor["equity"]],
        [row["equity"] for row in conservative["equity"]],
        "權益（美元）",
        "探索實驗",
        "保守預設（沒有成交）",
    )
    drawdown = svg_lines(
        [row["drawdown"] * 100 for row in explor["equity"]],
        [row["drawdown"] * 100 for row in conservative["equity"]],
        "回撤（%）",
        "探索實驗",
        "保守預設",
        percent=True,
    )
    poly_svg = svg_probability(poly["series"]) if poly.get("series") else "<p>沒有機率序列。</p>"
    sens_rows = []
    for row in payload["sensitivity"]:
        pool = "未知，不交易" if row["pool_fee_rate_per_side"] is None else f"{row['pool_fee_rate_per_side']*100:.2f}% 假設"
        sens_rows.append(
            "<tr>"
            f"<td>{row['chain_cost_sol_per_side']}</td>"
            f"<td>{pool}</td>"
            f"<td>{row['trade_count']}</td>"
            f"<td>{row['final_equity_usd']:.4f}</td>"
            f"<td>{row['total_return']*100:.2f}%</td>"
            "</tr>"
        )
    swap_rows = []
    for row in swaps.get("rows") or []:
        addr = row.get("tx_from_address") or ""
        short = addr[:4] + "…" + addr[-4:] if len(addr) > 10 else addr
        swap_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('block_timestamp')))}</td>"
            f"<td>{html.escape(str(row.get('kind')))}</td>"
            f"<td>{html.escape(str(row.get('volume_in_usd')))}</td>"
            f"<td>{html.escape(short)}</td>"
            f"<td class='mono'>{html.escape(str(row.get('tx_hash')))}</td>"
            "</tr>"
        )
    trade_row = "這段沒有成交。"
    if trade:
        trade_row = (
            f"訊號 {trade['entry_signal_utc']}（KST {trade['entry_signal_kst']}）"
            f" → 下一根開盤 {trade['entry_fill_utc']} 買入，"
            f"出場 {trade['exit_fill_utc']}（{trade['exit_reason']}）。"
            f"已實現 ${trade['realized_pnl']:.4f}。"
            f"段落：{trade['segment']}。留出段沒有成交。"
        )
    start = explor["bars_meta"]["start"]
    end = explor["bars_meta"]["end"]
    bench = explor["benchmarks"]["buy_and_hold"]
    generated = payload["generated_at_kst"]
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8"/>
<title>晏銘湛箴_gmgn_tgbot量化策略 — 紙上預覽</title>
<style>
  body {{ margin: 0; background: #f6f3ee; color: #1c1917; font-family: "WenQuanYi Micro Hei", "Noto Sans CJK TC", sans-serif; }}
  main {{ max-width: 1180px; margin: 0 auto; padding: 24px 20px 64px; }}
  h1 {{ font-size: 28px; margin: 0 0 8px; }}
  h2 {{ font-size: 20px; margin: 28px 0 8px; }}
  p, li {{ line-height: 1.55; }}
  .badges {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 18px; }}
  .badge {{ border-radius: 999px; padding: 4px 10px; font-size: 13px; background: #ffedd5; color: #9a3412; }}
  .badge.dark {{ background: #1c1917; color: #fafaf9; }}
  .badge.blue {{ background: #e0f2fe; color: #075985; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  .card {{ background: white; border: 1px solid #e7e5e4; border-radius: 12px; padding: 14px 16px; }}
  .card strong {{ font-size: 22px; }}
  svg {{ width: 100%; height: auto; background: white; border: 1px solid #e7e5e4; border-radius: 12px; }}
  table {{ width: 100%; border-collapse: collapse; background: white; font-size: 13px; }}
  th, td {{ border-bottom: 1px solid #e7e5e4; padding: 6px 8px; text-align: left; vertical-align: top; }}
  .mono {{ font-family: ui-monospace, monospace; font-size: 11px; word-break: break-all; }}
  .warn {{ background: #fff7ed; border-left: 4px solid #c2410c; padding: 10px 12px; }}
  label {{ font-size: 14px; }}
  input[type=range] {{ width: 100%; }}
  footer {{ font-size: 14px; color: #44403c; }}
  @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<main>
  <h1>晏銘湛箴_gmgn_tgbot量化策略</h1>
  <p>紙上預覽。價格來自 GeckoTerminal 公開池 OHLCV，損益是模型算的。產生時間 {html.escape(generated)}。</p>
  <div class="badges">
    <span class="badge dark">模擬損益 · 真實價格</span>
    <span class="badge">非實盤 · 無錢包 · 無下單</span>
    <span class="badge">初始資金 $10 · 現貨 1×</span>
    <span class="badge blue">Solana 池 · 日線 · 非 GMGN 官方歷史檔</span>
    <span class="badge">倖存者／選定池偏差</span>
    <span class="badge">Stock App 整合不可用</span>
  </div>

  <div class="grid">
    <section class="card">
      <h2>保守預設</h2>
      <p><strong>0 筆成交</strong></p>
      <p>期末權益 ${c['final_equity_usd']:.2f}，總報酬 {c['total_return']*100:.2f}%。池費未知、歷史可賣性未知、歷史流動性未知，所以不開倉。沒有成交就不是獲利。</p>
      <p>被擋下的指標訊號：{c['signal_blocked_count']}。</p>
    </section>
    <section class="card">
      <h2>探索實驗（假設池費）</h2>
      <p><strong>{m['trade_count']} 筆 · 總報酬 {m['total_return']*100:.2f}%</strong></p>
      <p>期末 ${m['final_equity_usd']:.4f}。最大回撤 {m['max_drawdown']*100:.2f}%（收盤市值）。費用 ${m['fees_paid_usd']:.4f}，鏈上費 ${m['chain_fees_paid_usd']:.4f}。勝率 {m['win_rate']*100:.0f}%（已平倉 {m['closed_trade_count']} 筆），獲利因子 {m['profit_factor']}。</p>
      <p>{html.escape(trade_row)}</p>
    </section>
  </div>

  <p class="warn">這不是獲利宣告。探索實驗放寬了 OHLCV 無法核實的安全閘，池費 0.30%/邊是假設。唯一成交落在訓練段；$10 裡約 $4.30 是 0.05 SOL 預留。買入持有的未實現期末約 ${bench['final_equity_usd']:.2f}（報酬 {bench['total_return']*100:.2f}%），賣出費還沒扣。現金基準是 $10。少做交易而少賠，不等於指標有效。</p>

  <h2>$WIF / SOL 日線</h2>
  <p>池 <span class="mono">{html.escape(meta['pool'])}</span> · 代幣 <span class="mono">{html.escape(meta['base_token'])}</span> · Raydium · {html.escape(start['utc'])}（{html.escape(start['kst'])}）至 {html.escape(end['utc'])}（{html.escape(end['kst'])}）· {meta['bar_count']} 根 · 缺口 {meta['gap_count']}。來源 <span class="mono">https://api.geckoterminal.com/api/v2</span>。這是倖存池，不是 meme 全市場。</p>
  <label for="scrub">重播到第 <output id="scrubOut">{len(bars)}</output> / {len(bars)} 根（含當日）</label>
  <input id="scrub" type="range" min="1" max="{len(bars)}" value="{len(bars)}"/>
  <p id="scrubDate"></p>
  {candle}
  <h2>權益與回撤</h2>
  {equity}
  {drawdown}

  <h2>費用敏感度</h2>
  <p>鏈上 0.002 / 0.005 / 0.006 SOL 是 GMGN 建議，不是協議最低費。池費未知的列是 0 筆。正報酬那一格仍是一筆假設成本下的訓練段交易。</p>
  <table>
    <thead><tr><th>鏈上 SOL／邊</th><th>池費／邊</th><th>成交</th><th>期末權益</th><th>總報酬</th></tr></thead>
    <tbody>
      {''.join(sens_rows)}
    </tbody>
  </table>

  <h2>Polymarket 機率（分開，沒有損益）</h2>
  <p>{html.escape(str(poly.get('question')))}。Yes token 的價格是 0–1 機率，不是美元報酬。選擇方式：{html.escape(str(poly.get('selection_bias')))}。點數 {poly.get('points')}，區間 {poly.get('min_price')}–{poly.get('max_price')}，最後 {poly.get('last_price')}。沒有和 $10 帳戶合併。</p>
  {poly_svg}

  <h2>公開池成交骨架（不是錢包獲利）</h2>
  <p>{html.escape(swaps.get('note') or '')}</p>
  <table>
    <thead><tr><th>時間</th><th>方向</th><th>美元量</th><th>發起地址（截斷）</th><th>交易雜湊</th></tr></thead>
    <tbody>
      {''.join(swap_rows) or '<tr><td colspan="5">沒有公開成交可供顯示。</td></tr>'}
    </tbody>
  </table>

  <h2>限制</h2>
  <ul>
    <li>最多三個指標：RSI(14)、ATR%(14)、相對量。不再進場是暫定設定，不是第四個指標。</li>
    <li>手動 TG 模型：收盤訊號、下一根開盤成交。沒有理想化的盤中止損。</li>
    <li>SOL/USDC 只是管線基準，不在這張主圖裡，也不能當成打金狗績效。</li>
    <li>日線不是規格稿裡的 15 分鐘。15 分鐘整段沒有下載。</li>
    <li>單筆 $0.10 與回撤 20% 是提議值，不是已接受的風險額度。</li>
  </ul>
  <footer>
    <p>Powered by CoinGecko. GeckoTerminal keyless 資料依其 API 條款僅作這次回測的可重現快照，不是資料轉售。Polymarket Data API 的機率序列另計。</p>
  </footer>
</main>
<script>
const stamps = {json.dumps([b.iso_utc() for b in bars])};
const slider = document.getElementById('scrub');
const out = document.getElementById('scrubOut');
const date = document.getElementById('scrubDate');
function apply() {{
  const n = Number(slider.value);
  out.textContent = String(n);
  date.textContent = stamps[n - 1] + ' UTC 之前的 K 線';
  document.querySelectorAll('[data-i]').forEach((node) => {{
    node.style.display = Number(node.getAttribute('data-i')) < n ? '' : 'none';
  }});
}}
slider.addEventListener('input', apply);
apply();
</script>
</body>
</html>
"""


def svg_candles(bars, trades) -> str:
    width, height, pad_l, pad_r, pad_t, pad_b = 1100, 420, 48, 16, 16, 28
    lows = [b.low for b in bars]
    highs = [b.high for b in bars]
    ymin, ymax = min(lows), max(highs)
    span = ymax - ymin or 1
    n = len(bars)
    plot_w = width - pad_l - pad_r

    def x(i: int) -> float:
        return pad_l + plot_w * (i / max(n - 1, 1))

    def y(price: float) -> float:
        return pad_t + (height - pad_t - pad_b) * (1 - (price - ymin) / span)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="WIF 日線與進出場">',
        f'<text x="{pad_l}" y="14" font-size="12" fill="#44403c">$WIF / SOL 日線（USD）· 綠點進場 · 紅點出場 · 探索實驗</text>',
    ]
    step = plot_w / max(n, 1)
    body = max(1.2, step * 0.62)
    for i, bar in enumerate(bars):
        color = "#0f766e" if bar.close >= bar.open else "#b91c1c"
        xmid = x(i)
        parts.append(
            f'<g data-i="{i}"><line x1="{xmid:.2f}" x2="{xmid:.2f}" y1="{y(bar.high):.2f}" y2="{y(bar.low):.2f}" stroke="{color}" stroke-width="1"/>'
            f'<rect x="{xmid - body/2:.2f}" y="{y(max(bar.open, bar.close)):.2f}" width="{body:.2f}" height="{max(1, abs(y(bar.open)-y(bar.close))):.2f}" fill="{color}"/></g>'
        )
    for trade in trades:
        if trade.get("entry_fill_index") is not None:
            i = trade["entry_fill_index"]
            parts.append(
                f'<circle data-i="{i}" cx="{x(i):.2f}" cy="{y(bars[i].low) + 10:.2f}" r="4" fill="#15803d"/>'
            )
        if trade.get("exit_fill_index") is not None:
            i = trade["exit_fill_index"]
            parts.append(
                f'<circle data-i="{i}" cx="{x(i):.2f}" cy="{y(bars[i].high) - 10:.2f}" r="4" fill="#b91c1c"/>'
            )
    parts.append(f'<text x="{pad_l}" y="{height-8}" font-size="11" fill="#57534e">{bars[0].iso_utc()} → {bars[-1].iso_utc()}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_lines(primary, secondary, title, legend_a, legend_b, percent=False) -> str:
    width, height, pad_l, pad_r, pad_t, pad_b = 1100, 260, 48, 16, 22, 24
    values = list(primary) + list(secondary)
    ymin, ymax = min(values), max(values)
    if ymin == ymax:
        ymin -= 1
        ymax += 1
    span = ymax - ymin
    n = len(primary)

    def x(i: int) -> float:
        return pad_l + (width - pad_l - pad_r) * (i / max(n - 1, 1))

    def y(value: float) -> float:
        return pad_t + (height - pad_t - pad_b) * (1 - (value - ymin) / span)

    def poly(series, color):
        lines = []
        for i in range(1, len(series)):
            lines.append(
                f'<line data-i="{i}" x1="{x(i-1):.2f}" y1="{y(series[i-1]):.2f}" x2="{x(i):.2f}" y2="{y(series[i]):.2f}" stroke="{color}" stroke-width="1.6"/>'
            )
        return "".join(lines)

    label = f"{ymax:.2f}" if not percent else f"{ymax:.1f}%"
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">'
        f'<text x="{pad_l}" y="16" font-size="12" fill="#44403c">{html.escape(title)} · '
        f'<tspan fill="#1d4ed8">{html.escape(legend_a)}</tspan> · '
        f'<tspan fill="#a8a29e">{html.escape(legend_b)}</tspan></text>'
        f'<text x="4" y="{pad_t+8}" font-size="10" fill="#78716c">{label}</text>'
        + poly(secondary, "#a8a29e")
        + poly(primary, "#1d4ed8")
        + "</svg>"
    )


def svg_probability(points: list[dict]) -> str:
    if len(points) < 2:
        return "<p>機率點不足，沒有繪圖。</p>"
    width, height, pad_l, pad_r, pad_t, pad_b = 1100, 240, 48, 16, 22, 24
    prices = [p["price"] for p in points]
    t0, t1 = points[0]["timestamp"], points[-1]["timestamp"]
    span_t = max(t1 - t0, 1)

    def x(ts: int) -> float:
        return pad_l + (width - pad_l - pad_r) * ((ts - t0) / span_t)

    def y(price: float) -> float:
        return pad_t + (height - pad_t - pad_b) * (1 - price)

    poly = " ".join(f"{x(p['timestamp']):.2f},{y(p['price']):.2f}" for p in points)
    start = fmt_ts(points[0]["timestamp"])["utc"]
    end = fmt_ts(points[-1]["timestamp"])["utc"]
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Polymarket 機率">'
        f'<text x="{pad_l}" y="16" font-size="12" fill="#44403c">機率 0–1 · 不是代幣價格 · {start} → {end}</text>'
        f'<line x1="{pad_l}" x2="{width-pad_r}" y1="{y(0):.2f}" y2="{y(0):.2f}" stroke="#e7e5e4"/>'
        f'<line x1="{pad_l}" x2="{width-pad_r}" y1="{y(1):.2f}" y2="{y(1):.2f}" stroke="#e7e5e4"/>'
        f'<polyline points="{poly}" fill="none" stroke="#7c3aed" stroke-width="1.6"/>'
        "</svg>"
    )


if __name__ == "__main__":
    main()
