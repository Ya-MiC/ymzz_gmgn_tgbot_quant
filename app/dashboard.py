"""Local Traditional Chinese paper dashboard. No orders, no secrets, no network."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ymzz_quant.catalog import DATASETS
from ymzz_quant.engine import run_backtest
from ymzz_quant.report import scenario_diff_rows
from ymzz_quant.service import load_bars, load_named_scenarios, polymarket_summary, recent_swaps

st.set_page_config(page_title="晏銘湛箴_gmgn_tgbot量化策略", layout="wide")
st.title("晏銘湛箴_gmgn_tgbot量化策略")
st.caption("紙上回測。模擬損益，價格是公開歷史資料。沒有錢包、沒有下單、沒有實盤。")
st.info(
    "這一頁在 Streamlit 行程裡直接呼叫引擎，不是獨立部署的 API。"
    "完整的本機研究服務是 `PYTHONPATH=src python3 -m ymzz_quant.api`，頁面在 frontend/index.html。"
    "preview/index.html 是先前那次研究的靜態快照，不會重算。"
)

badges = st.columns(6)
badges[0].markdown("**模擬損益·真實價格**")
badges[1].markdown("**非實盤**")
badges[2].markdown("**初始 $10 · 1×**")
badges[3].markdown("**Stock App 不可用**")
badges[4].markdown("**倖存者偏差**")
badges[5].markdown("**池費未知則預設不交易**")

scenarios = load_named_scenarios(ROOT)
dataset_key = st.selectbox(
    "資料集",
    list(DATASETS),
    format_func=lambda key: f"{DATASETS[key]['symbol']} — {DATASETS[key]['role_zh']}",
)
scenario_name = st.selectbox(
    "成本情境",
    list(scenarios),
    format_func=lambda key: scenarios[key].label_zh,
)
base = scenarios[scenario_name]
conservative = scenarios["conservative_no_trade"]
exploratory = scenarios["exploratory_ohlcv_only"]
if scenario_name == "exploratory_ohlcv_only":
    st.warning(
        "這是放寬實驗，不是完整風控策略，也不是已套用 $0.10 提議預算的策略。"
        "單筆預算檢查沒有被關掉；`proposed_per_trade_loss_budget_usd` 從 0.10 改成 3.00，"
        "可賣性閘與流動性閘從 true 改成 false，池費從 null 改成假設 0.003。"
        "部位可以虧超過 $0.10。沒有為了獲利或更多成交去改這些數字。"
    )
with st.expander("保守預設與放寬實驗的登記差（不是完整風控策略）", expanded=True):
    st.markdown(
        "放寬實驗可以虧過提議的 $0.10，因為預算檢查仍開著，只是門檻從 **$0.10 改成 $3.00**。"
        "來回鏈上費約 $0.86，已經大於 $0.10，所以保守預算即使打開其他閘也不會進場。"
        "`no_reentry` 兩邊都是 true：第一筆出場後，同一池在這次回測結束前的新倉全部被擋下，驗證段與留出段都包括在內。"
        "那是暫定開關故意抑制後續交易，不是第一波偵測，也不是已驗證的樣本外策略。"
    )
    diff = scenario_diff_rows(conservative.to_public_dict(), exploratory.to_public_dict())
    st.dataframe(
        [
            {
                "參數": row["label"],
                "保守預設": row["conservative"],
                "放寬實驗": row["exploratory"],
                "比較": "不同" if row["changed"] else "相同",
            }
            for row in diff
        ],
        width="stretch",
        hide_index=True,
    )
with st.expander("研究參數（偏離預設後，驗證與留出不再算未調參）", expanded=False):
    rsi_low = st.slider("RSI 下限", 0, 50, int(base.rsi_low))
    rsi_high = st.slider("RSI 上限", 10, 80, int(base.rsi_high))
    rsi_exit = st.slider("RSI 出場", 50, 100, int(base.rsi_exit))
    rv_min = st.slider("相對量下限", 0.5, 5.0, float(base.rv_min), 0.1)
    k_sl = st.slider("止損倍數 k_sl（研究參數）", 0.5, 4.0, float(base.k_sl), 0.1)
    k_tp = st.slider("止盈倍數 k_tp（研究參數）", 0.5, 6.0, float(base.k_tp), 0.1)
    chain_options = [0.002, 0.005, 0.006]
    chain_index = min(range(len(chain_options)), key=lambda i: abs(chain_options[i] - base.chain_cost_sol_per_side))
    chain = st.selectbox("鏈上費 SOL／邊（建議值，不是協議最低）", chain_options, index=chain_index)
    fee_mode = st.radio("池費", ["沿用情境", "未知（不交易）", "假設 0.30%", "假設 1%"], horizontal=True)
    no_reentry = st.checkbox(
        "同一池在本次回測結束前不再進場（暫定開關：第一筆出場後擋掉之後所有驗證段與留出段的新倉；不是第一波偵測，也不是已驗證的樣本外策略）",
        value=base.no_reentry,
    )
    execution = st.radio(
        "成交模型",
        ["manual_tg_next_open", "resting_stop_research"],
        format_func=lambda v: "手動 TG：下一根開盤" if v.startswith("manual") else "研究用掛單止損（不是手動 TG）",
        index=0 if base.execution_mode.startswith("manual") else 1,
    )

pool_fee = base.pool_fee_rate_per_side
pool_status = base.pool_fee_status
if fee_mode == "未知（不交易）":
    pool_fee, pool_status = None, "unknown_user_selected"
elif fee_mode == "假設 0.30%":
    pool_fee, pool_status = 0.003, "ASSUMED_dashboard"
elif fee_mode == "假設 1%":
    pool_fee, pool_status = 0.01, "ASSUMED_dashboard"
scenario = replace(
    base,
    rsi_low=float(rsi_low),
    rsi_high=float(rsi_high),
    rsi_exit=float(rsi_exit),
    rv_min=float(rv_min),
    k_sl=float(k_sl),
    k_tp=float(k_tp),
    chain_cost_sol_per_side=float(chain),
    pool_fee_rate_per_side=pool_fee,
    pool_fee_status=pool_status,
    no_reentry=bool(no_reentry),
    execution_mode=execution,
)
changed = scenario != base
if changed:
    st.warning("參數已偏離預先登記的情境。驗證段與留出段此時只是重算，不是未調參結果。")

bars, meta = load_bars(dataset_key, ROOT)
if not bars:
    st.error("沒有歷史價格，不繪製假圖。")
    st.stop()
result = run_backtest(
    bars,
    scenario,
    dataset_key,
    meta["expected_interval_seconds"],
    synthetic=False,
    dataset_meta=meta,
)
metrics = result.metrics
st.subheader(meta["symbol"])
end_close = result.bars_meta.get("end_close") or result.bars_meta["end"]
st.write(
    f"鏈 {meta['chain']} · 池 `{meta['pool']}` · 代幣 `{meta.get('base_token')}` · "
    f"{meta['interval_label']} · 已收盤 {meta['bar_count']} 根 · 已排除未收盤 {meta.get('unclosed_bar_count', 0)} 根 · "
    f"缺口 {meta['gap_count']} · "
    f"第一根開盤 {result.bars_meta['start']['utc']} / {result.bars_meta['start']['kst']} · "
    f"最後一根開盤 {result.bars_meta['end']['utc']} / {result.bars_meta['end']['kst']} · "
    f"該根收盤 {end_close['utc']} / {end_close['kst']}"
)
dropped = meta.get("dropped_unclosed") or []
if dropped:
    detail = "；".join(
        f"開盤 {row['utc']} / {row['kst']}，收盤 {row['close_utc']} / {row['close_kst']}，抓取 {row.get('fetched_at_utc')}"
        for row in dropped
    )
    st.caption("未收盤、未畫進圖：" + detail + "。橫軸是已收盤 K 線的開盤時刻（UTC）。缺口 0 只表示這些已收盤 K 線彼此相接。")
else:
    st.caption("橫軸是已收盤 K 線的開盤時刻（UTC）。這次沒有再排除未收盤 K 線。")
st.caption(meta.get("bias_zh") or meta["bias"])
if metrics["zero_trades"]:
    st.info("這段沒有成交。期末仍是 $10，報酬 0。不要把空結果讀成獲利。")
else:
    st.write(
        f"成交 {metrics['trade_count']} 筆，總報酬 {metrics['total_return']*100:.2f}%，"
        f"期末 ${metrics['final_equity_usd']:.4f}，最大回撤 {metrics['max_drawdown']*100:.2f}%，"
        f"費用 ${metrics['fees_paid_usd']:.4f}，鏈上費 ${metrics['chain_fees_paid_usd']:.4f}。"
    )
    if metrics["win_rate_defined"]:
        st.write(f"勝率 {metrics['win_rate']*100:.1f}%。獲利因子 {metrics['profit_factor'] if metrics['profit_factor_defined'] else '未定義'}。")

cols = st.columns(4)
cols[0].metric("期末權益", f"${metrics['final_equity_usd']:.2f}")
cols[1].metric("總報酬", f"{metrics['total_return']*100:.2f}%")
cols[2].metric("最大回撤", f"{metrics['max_drawdown']*100:.2f}%")
cols[3].metric("成交", metrics["trade_count"])
bench = result.benchmarks["buy_and_hold"]
bench_final = bench.get("final_equity_usd")
bench_final_txt = "未計算" if bench_final is None else f"${bench_final:.4f}"
st.caption(
    f"現金基準 $10。買入持有：{bench.get('status')}，期末 {bench_final_txt}。"
    f" {bench.get('note') or bench.get('reason') or ''}"
)
st.caption(
    f"SOL 快照 ${scenario.sol_usd:.2f} @ {scenario.sol_usd_fetched_at_kst}。"
    f" 預留 {scenario.wallet_reserve_sol} SOL ≈ ${scenario.reserve_usd:.2f}。"
    f" 池費狀態 {scenario.pool_fee_status}。這個畫面的單筆預算是 ${scenario.proposed_per_trade_loss_budget_usd}（提議值，不是使用者指定）。"
    f" 回撤 {scenario.proposed_max_drawdown_frac:.0%} 也是提議值。"
    f" 留出段成交 {metrics.get('heldout_trade_count', 0)} 筆。"
    f" 成交模型 {scenario.execution_mode}，same-bar SL 次數 {metrics.get('same_bar_sl_first_count', 0)}。"
    f" 最低現金 ${metrics['min_cash']:.4f}。"
)

frame = pd.DataFrame(
    {
        "time": [b.iso_utc() for b in bars],
        "open": [b.open for b in bars],
        "high": [b.high for b in bars],
        "low": [b.low for b in bars],
        "close": [b.close for b in bars],
        "rsi": result.indicators["rsi"],
        "atr_pct": result.indicators["atr_pct"],
        "rv": result.indicators["rv"],
    }
)
equity = pd.DataFrame(result.equity)
last = st.slider("重播到第幾根已收盤 K 線（含，時間是開盤）", 1, len(frame), len(frame))
view = frame.iloc[:last]
eq = equity.iloc[:last]
fig = make_subplots(rows=4, cols=1, shared_xaxes=True, row_heights=[0.46, 0.18, 0.18, 0.18], vertical_spacing=0.03)
fig.add_trace(
    go.Candlestick(x=view["time"], open=view["open"], high=view["high"], low=view["low"], close=view["close"], name="K 線"),
    row=1, col=1,
)
for trade in result.trades:
    if trade.get("entry_fill_index") is not None and trade["entry_fill_index"] < last:
        fig.add_trace(
            go.Scatter(
                x=[frame.loc[trade["entry_fill_index"], "time"]],
                y=[trade["entry_fill_px"]],
                mode="markers",
                marker=dict(color="#15803d", size=10, symbol="triangle-up"),
                name="進場",
            ),
            row=1, col=1,
        )
    if trade.get("exit_fill_index") is not None and trade["exit_fill_index"] < last:
        fig.add_trace(
            go.Scatter(
                x=[frame.loc[trade["exit_fill_index"], "time"]],
                y=[trade["exit_fill_px"] or frame.loc[trade["exit_fill_index"], "close"]],
                mode="markers",
                marker=dict(color="#b91c1c", size=10, symbol="triangle-down"),
                name="出場",
            ),
            row=1, col=1,
        )
fig.add_trace(go.Scatter(x=view["time"], y=view["rsi"], name="RSI14", line=dict(color="#0369a1")), row=2, col=1)
fig.add_trace(go.Scatter(x=view["time"], y=view["atr_pct"], name="ATR%", line=dict(color="#b45309")), row=3, col=1)
fig.add_trace(go.Scatter(x=view["time"], y=view["rv"], name="相對量", line=dict(color="#6d28d9")), row=4, col=1)
fig.update_layout(height=860, xaxis_rangeslider_visible=False, margin=dict(l=40, r=20, t=30, b=20))
st.plotly_chart(fig, width="stretch")

eq_fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06)
eq_fig.add_trace(go.Scatter(x=eq["utc"], y=eq["equity"], name="權益", line=dict(color="#1d4ed8")), row=1, col=1)
eq_fig.add_trace(go.Scatter(x=eq["utc"], y=[10] * len(eq), name="現金基準", line=dict(color="#a8a29e", dash="dot")), row=1, col=1)
eq_fig.add_trace(go.Scatter(x=eq["utc"], y=eq["drawdown"], name="回撤", line=dict(color="#b91c1c")), row=2, col=1)
eq_fig.update_layout(height=420, margin=dict(l=40, r=20, t=30, b=20))
st.plotly_chart(eq_fig, width="stretch")

st.subheader("成交明細")
trades = pd.DataFrame(result.trades)
if trades.empty:
    st.write("沒有成交。")
else:
    st.dataframe(trades, width="stretch")
    st.download_button("下載成交 CSV", trades.to_csv(index=False).encode("utf-8"), "trades.csv", "text/csv")

st.subheader("被擋下的訊號")
skips = pd.DataFrame(result.skips)
if skips.empty:
    st.write("沒有被擋下的指標訊號。")
else:
    st.dataframe(skips, width="stretch")
    st.download_button("下載跳過原因 CSV", skips.to_csv(index=False).encode("utf-8"), "skips.csv", "text/csv")

st.subheader("Polymarket（機率，不是這筆 $10）")
poly = polymarket_summary(ROOT)
if not poly.get("available"):
    st.write("沒有機率資料。")
else:
    st.write(poly["note"])
    st.write(f"{poly['question']} · 點數 {poly['points']} · 最後機率 {poly['last_price']}")
    series = pd.DataFrame(poly["series"])
    series["time"] = pd.to_datetime(series["timestamp"], unit="s", utc=True)
    prob = go.Figure(go.Scatter(x=series["time"], y=series["price"], name="機率", line=dict(color="#7c3aed")))
    prob.update_yaxes(range=[0, 1], title="機率")
    prob.update_layout(height=320, margin=dict(l=40, r=20, t=30, b=20))
    st.plotly_chart(prob, width="stretch")

st.subheader("公開池成交骨架")
swaps = recent_swaps(ROOT)
st.write(swaps.get("note") or swaps.get("reason"))
if swaps.get("rows"):
    st.dataframe(pd.DataFrame(swaps["rows"]), width="stretch")

st.caption("Powered by CoinGecko. 初始資金固定 $10。不補倉、不馬丁、不加槓。OHLCV 不能保證出場價。")
