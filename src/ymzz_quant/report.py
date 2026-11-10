"""Traditional Chinese research report. Numbers come from the engine, not from a hand-written claim."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ymzz_quant.data_adapters import fmt_ts

KST = ZoneInfo("Asia/Seoul")


def _pct(value):
    if value is None:
        return "未定義"
    return f"{value * 100:.2f}%"


def _usd(value):
    if value is None:
        return "—"
    return f"${value:.4f}"


def _line_metrics(result) -> list[str]:
    m = result.metrics
    b = result.benchmarks["buy_and_hold"]
    lines = [
        f"- 樣本 K 線：{m['sample_bars']} 根（{result.bars_meta['start']['utc']} / {result.bars_meta['start']['kst']} → {result.bars_meta['end']['utc']} / {result.bars_meta['end']['kst']}）",
        f"- 成交筆數：{m['trade_count']}（已平 {m['closed_trade_count']}，未平 {m['open_trade_count']}）",
        f"- 期末權益：{_usd(m['final_equity_usd'])}；總報酬：{_pct(m['total_return'])}；已實現 {_usd(m['realized_pnl'])}；未實現 {_usd(m['unrealized_pnl'])}",
        f"- 最大回撤（收盤市值，不是盤中）：{_pct(m['max_drawdown'])}",
        f"- 費用（GMGN＋池費，池費若為假設會另標）：{_usd(m['fees_paid_usd'])}；鏈上費美元：{_usd(m['chain_fees_paid_usd'])}",
        f"- 勝率：{_pct(m['win_rate']) if m['win_rate_defined'] else '未定義（沒有已平倉交易）'}；獲利因子：{m['profit_factor'] if m['profit_factor_defined'] else '未定義'}",
        f"- 被擋下的指標訊號：{m['signal_blocked_count']}",
        f"- 現金基準：{_usd(result.benchmarks['cash']['final_equity_usd'])}",
        f"- 買入持有：狀態 {b.get('status')}；期末 {_usd(b.get('final_equity_usd'))}；報酬 {_pct(b.get('total_return'))}；最大回撤 {_pct(b.get('max_drawdown'))}。{b.get('note','')}",
    ]
    if m["zero_trades"]:
        lines.append("- 這段沒有成交。報酬記 0，不是獲利。")
    return lines


def render_markdown(bundle: dict) -> str:
    now = datetime.now(timezone.utc).astimezone(KST)
    primary = bundle["runs"]["wif_daily|conservative_no_trade"]
    explor = bundle["runs"]["wif_daily|exploratory_ohlcv_only"]
    split = explor.split
    train_end = fmt_ts(int(split["train_end_exclusive_ts"]))
    val_end = fmt_ts(int(split["validation_end_exclusive_ts"]))
    start = fmt_ts(int(split["start_ts"]))
    end = fmt_ts(int(split["end_ts"]))
    lines = [
        f"# 晏銘湛箴_gmgn_tgbot量化策略 — 紙上回測紀錄",
        "",
        f"- 產生時間：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}（{now.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}）",
        "- 性質：**模擬損益，價格是公開歷史成交彙總的 OHLCV。不是實盤、不是錢包、不是獲利保證。**",
        "- 徽章：`SIMULATED PnL ON REAL PRICES`",
        "- Stock App：身份未確認，**整合不可用**。沒有用 yfinance 或股票資料頂替。",
        "- 引擎：本倉庫自寫的現貨回測。未安裝、未呼叫 `backtesting.py`。",
        "",
        "## 主結果（保守預設）",
        "",
        "GeckoTerminal 的 `pool_fee_percentage` 是 null，歷史可賣性與歷史流動性也無法從 OHLCV 得知。保守預設因此**不開倉**。",
        "",
    ]
    lines.extend(_line_metrics(primary))
    lines += [
        "",
        f"被擋下的訊號例（第一筆）：{primary.skips[0]['utc'] if primary.skips else '無'}，原因 {primary.skips[0]['reasons'] if primary.skips else []}。",
        "單筆損失預算 $0.10 與最大回撤 20% 都是**提議值**，不是使用者指定或已接受的風險額度。以本次 SOL 快照計，單邊鏈上 0.005 SOL 已約 $0.43，來回鏈上費就超過 $0.10，所以即便安全閘打開，這個提議預算也會跳過交易。",
        "",
        "## 探索實驗（不是完整安全策略）",
        "",
        "這個情境明確假設池費每邊 0.30%（因為 API 沒有給費率，**不是查到的費率**），並關掉「可賣性／歷史流動性未知就拒絕」的閘。鏈上費仍用建議值 0.005 SOL／邊，GMGN 文件上的 1%／筆照算，滑點 30bp 是研究假設而不是 GMGN 介面的 30–35% 容忍上限。預留 0.05 SOL。不補倉、不馬丁、不加倉、不加槓。`no_reentry` 是暫定設定，不是第四個指標。",
        "",
    ]
    lines.extend(_line_metrics(explor))
    if explor.trades:
        trade = explor.trades[0]
        lines += [
            "",
            "唯一一筆（在訓練段，不是留出段）：",
            f"- 訊號 {trade['entry_signal_utc']} / {trade['entry_signal_kst']}，下一根開盤成交 {trade['entry_fill_utc']} / {trade['entry_fill_kst']}",
            f"- 出場訊號 {trade['exit_signal_utc']}（{trade['exit_reason']}），成交 {trade['exit_fill_utc']}",
            f"- 段落：{trade['segment']}",
            f"- 已實現損益 {_usd(trade['realized_pnl'])}；GMGN 費 {_usd(trade['gmgn_fees'])}；假設池費 {_usd(trade['pool_fees'])}；鏈上費 {_usd(trade['chain_fees'])}",
            f"- 進場執行殘差（成交價 − 訊號收盤）{trade['entry_residual']:.6f}；出場執行殘差（訊號收盤 − 成交價）{trade['exit_residual']:.6f}",
            "- 之後的指標訊號被暫定「同一池不再進場」擋下，其中包含驗證段與留出段。留出段**沒有成交**。不能把這一筆訓練段損益說成留出段績效。",
        ]
    lines += [
        "",
        "買入持有在這段 $WIF 日線上的未實現市值明顯低於現金。探索策略大部分時間停在現金，所以跌得比買入持有少。這只說明「少暴露在一段下跌裡」，不是指標已被證明有預測力。同一套探索假設拿到 SOL/USDC 管線樣本時，單筆止損的虧損大於該樣本的買入持有，方向並不一致。",
        "",
        "## 時間切分（依實際抓到的窗，50/25/25）",
        "",
        f"- 規則在看報酬之前就寫死：實際時間跨度的前 50% 訓練、接著 25% 驗證、最後 25% 留出。沒有用留出段重估 RSI／RV／ATR 分位。",
        f"- 起點 {start['utc']} / {start['kst']}",
        f"- 訓練結束（不含）{train_end['utc']} / {train_end['kst']}",
        f"- 驗證結束（不含）{val_end['utc']} / {val_end['kst']}",
        f"- 終點 {end['utc']} / {end['kst']}",
        f"- 根數：訓練 {split['counts']['train']}，驗證 {split['counts']['validation']}，留出 {split['counts']['heldout']}",
        f"- 訓練段 ATR% 分位 [{explor.frozen_atr_band['quantile_low']}, {explor.frozen_atr_band['quantile_high']}] → 凍結區間 {_pct(explor.frozen_atr_band['low'])} 到 {_pct(explor.frozen_atr_band['high'])}（訓練樣本 {explor.frozen_atr_band['train_samples']}）。規格稿裡 2026-05-11 起的日曆三段，是在假設只有約六個月時寫的；這次 $WIF 合併窗更長，日曆邊界改由同一條比例規則落在實際窗上。",
        "",
        "## 資料窗與選擇（先寫條件，再看報酬）",
        "",
        bundle["selection_note"],
        "",
        f"- SOL 美元快照：{explor.scenario['sol_usd']}，時間 {explor.scenario['sol_usd_fetched_at_utc']} / {explor.scenario['sol_usd_fetched_at_kst']}，來源 {explor.scenario['sol_usd_source']}。這是換算用的快照，不是預測。",
        f"- 預留 0.05 SOL 約 {_usd(explor.scenario['reserve_usd_at_snapshot'])}，不能拿去開倉。可動用現金約 {_usd(10 - explor.scenario['reserve_usd_at_snapshot'])}。",
        "- 鍵less `before_timestamp` 對選定的 $WIF 池又取回一頁，合併後 364 根日線、間隔都是 1 日、重疊的那一根兩頁一致。文件寫 Basic／keyless 大約 6 個月；這次呼叫實際回了更早的日線。不能据此說所有池都能超過 6 個月，只記錄這次回應。",
        "- 規格稿的主周期是 15 分鐘。本輪完整窗是**日線**。沒有把日線結果說成 15 分鐘策略績效。",
        "- OHLCV 不能證明當時買得進、賣得出。失敗出場與貔貅都沒有被這份 K 線證實或排除。",
        "",
        "## 其他樣本（同一凍結規則，不用來改門檻）",
        "",
    ]
    for key in ("sol_usdc_daily", "bonk_daily_appendix", "popcat_daily_appendix"):
        for scenario_name in ("conservative_no_trade", "exploratory_ohlcv_only"):
            result = bundle["runs"][f"{key}|{scenario_name}"]
            lines.append(f"### {result.bars_meta['dataset']['symbol']} · {result.bars_meta['dataset']['role_zh']} · {scenario_name}")
            lines.append("")
            lines.extend(_line_metrics(result))
            lines.append("")
    lines += [
        "## 費用敏感度（$WIF 日線，安全閘已放寬）",
        "",
        "池費 null 的列維持 0 筆。其餘池費是假設。正負號會隨鏈上費假設改變；每一格最多一筆，不能當成穩定優勢。",
        "",
        "| 鏈上 SOL／邊 | 池費／邊 | 成交 | 期末權益 | 總報酬 | 費用 | 鏈上費美元 | 被擋訊號 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in bundle["sensitivity"]:
        pool = "未知→不交易" if row["pool_fee_rate_per_side"] is None else f"{row['pool_fee_rate_per_side']*100:.2f}% 假設"
        lines.append(
            f"| {row['chain_cost_sol_per_side']} | {pool} | {row['trade_count']} | {_usd(row['final_equity_usd'])} | {_pct(row['total_return'])} | {_usd(row['fees_paid_usd'])} | {_usd(row['chain_fees_paid_usd'])} | {row['signal_blocked_count']} |"
        )
    poly = bundle["polymarket"]
    lines += [
        "",
        "## Polymarket（分開的機率檢視，沒有損益回測）",
        "",
        f"- 問題：{poly.get('question')}",
        f"- condition `{poly.get('condition_id')}`",
        f"- Yes token `{poly.get('token_id_yes')}`",
        f"- 選擇方式：{poly.get('selection_bias')}",
        f"- 點數 {poly.get('points')}，價格區間 {poly.get('min_price')}–{poly.get('max_price')}，最後 {poly.get('last_price')}，單位是 0–1 機率。",
        f"- `has_more={poly.get('has_more')}`。抓取 {poly.get('fetched_at_utc')} / {poly.get('fetched_at_kst')}。",
        "- 沒有把這條機率和 $10 meme 帳戶合併，也沒有用代幣 RSI 規則去算預測市場損益。",
        "",
        "## 公開池成交骨架",
        "",
        bundle["swaps"]["note"] if bundle["swaps"].get("available") else "沒有成交檔。",
        f"檔內 {bundle['swaps'].get('count_in_file', 0)} 筆，報告只列最近 {len(bundle['swaps'].get('rows') or [])} 筆的欄位，不計算地址損益。",
        "",
        "## 仍未解決",
        "",
        "- Stock App 產品身份未知。",
        "- 池費未知；Pump.fun 與 Raydium 費率不能互相替代。GMGN 文件示例 Pump.fun 1%，Help Center 另有 1.25% 的說法，本池是 Raydium $WIF/SOL，兩種都沒有套用成已核費率。",
        "- 沒有 point-in-time 宇宙，死掉的池不在搜尋結果裡。",
        "- 官方 SOL 交易機器人名稱與部分教學不一致；本程式沒有、也不能控制那些機器人。",
        "- 「永遠不要發二次財」沒有收成唯一解釋。程式裡的不再進場只是暫定設定。",
        "",
    ]
    return "\n".join(lines) + "\n"
