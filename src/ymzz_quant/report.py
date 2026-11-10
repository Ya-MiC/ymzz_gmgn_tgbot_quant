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


DIFF_FIELDS = (
    ("proposed_per_trade_loss_budget_usd", "提議的單筆損失預算（美元）"),
    ("budget_gate_disabled", "單筆預算檢查是否被關掉"),
    ("pool_fee_rate_per_side", "池費每邊"),
    ("pool_fee_status", "池費狀態"),
    ("require_historical_sellability", "可賣性未知就拒絕進場"),
    ("require_historical_liquidity", "流動性未知就拒絕進場"),
    ("historical_sellability_known", "歷史可賣性是否已知"),
    ("historical_liquidity_known", "歷史流動性是否已知"),
    ("require_known_pool_fee", "池費未知就拒絕"),
    ("chain_cost_sol_per_side", "鏈上費（SOL／邊）"),
    ("wallet_reserve_sol", "錢包預留（SOL）"),
    ("gmgn_fee_rate_per_side", "GMGN 費每邊"),
    ("slip_bp_buy", "買入滑點（bp）"),
    ("slip_bp_sell", "賣出滑點（bp）"),
    ("execution_mode", "成交模型"),
    ("no_reentry", "同一池不再進場"),
    ("k_sl", "k_sl"),
    ("k_tp", "k_tp"),
    ("rsi_low", "RSI 下限"),
    ("rsi_high", "RSI 上限"),
    ("rsi_exit", "RSI 出場"),
    ("rv_min", "相對量下限"),
    ("proposed_max_drawdown_frac", "提議的最大回撤"),
    ("initial_cash_usd", "初始現金（美元）"),
)


def format_param(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def scenario_diff_rows(conservative: dict, exploratory: dict) -> list[dict]:
    rows = []
    for key, label in DIFF_FIELDS:
        left = conservative.get(key)
        right = exploratory.get(key)
        rows.append(
            {
                "key": key,
                "label": label,
                "conservative": format_param(left),
                "exploratory": format_param(right),
                "changed": left != right,
            }
        )
    return rows


def _budget_sentence(budget: float, chain_per_side: float) -> str:
    round_trip = 2 * chain_per_side
    if budget <= round_trip:
        return f"這個預算小於或等於來回鏈上費 {_usd(round_trip)}，所以即便安全閘打開，部位也會是 0。"
    return f"這個預算大於來回鏈上費 {_usd(round_trip)}，成本檢查本身不會單憑鏈上費把部位打成 0。"


def _window_line(result) -> str:
    m = result.metrics
    start = result.bars_meta["start"]
    end_open = result.bars_meta["end"]
    end_close = result.bars_meta.get("end_close") or end_open
    dropped = result.bars_meta.get("unclosed_bar_count", 0)
    return (
        f"- 已收盤 K 線：{m['sample_bars']} 根。時間戳是開盤，不是收盤。"
        f"第一根開盤 {start['utc']} / {start['kst']}。"
        f"最後一根開盤 {end_open['utc']} / {end_open['kst']}，該根收盤 {end_close['utc']} / {end_close['kst']}。"
        f"抓取時尚未收盤、已排除：{dropped} 根。"
        "缺口數只描述這些已收盤 K 線之間的間隔，不能把未收盤的最後一根算進樣本，也不能把『缺口 0』說成含未完成 K 線的無前視覆蓋。"
    )


def _line_metrics(result) -> list[str]:
    m = result.metrics
    b = result.benchmarks["buy_and_hold"]
    lines = [
        _window_line(result),
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
    end_close = explor.bars_meta.get("end_close") or fmt_ts(int(split["end_ts"]))
    dropped = (explor.bars_meta.get("dataset") or {}).get("dropped_unclosed") or []
    chain = float(explor.scenario["chain_fee_usd_per_side"])
    reserve = float(explor.scenario["reserve_usd_at_snapshot"])
    budget_conservative = float(primary.scenario["proposed_per_trade_loss_budget_usd"])
    budget_exploratory = float(explor.scenario["proposed_per_trade_loss_budget_usd"])
    lines = [
        f"# 晏銘湛箴_gmgn_tgbot量化策略 — 紙上回測紀錄",
        "",
        f"- 產生時間：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}（{now.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}）",
        "- 性質：**模擬損益，價格是公開歷史成交彙總的 OHLCV。不是實盤、不是錢包、不是獲利保證。**",
        "- 徽章：`SIMULATED PnL ON REAL PRICES`",
        "- 已取代：`results/2026-11-10_114212_KST_backtest.md` 與當時的預覽把 2026-11-10 00:00 UTC 開盤、尚未收盤的日線算進 364 根。那一版見 `results/superseded/`，不要再引用成已收盤樣本。",
        "- Stock App：身份未確認，**整合不可用**。沒有用 yfinance 或股票資料頂替。",
        "- 引擎：本倉庫自寫的現貨回測。未安裝、未呼叫 `backtesting.py`。",
        "",
        "## 已排除的未收盤 K 線",
        "",
        "GeckoTerminal 的時間戳是 K 線**開盤**。一根 K 線只有在 `開盤 + 該周期秒數 <= 該檔的抓取時間` 時才算已收盤。抓取時間剛好等於收盤時刻算已收盤；沒有抓取時間則不當成已收盤。同一根若有一份是收盤後抓到的，就保留那一份。",
        "",
    ]
    if dropped:
        for row in dropped:
            lines.append(
                f"- 排除開盤 {row['utc']} / {row['kst']}，收盤 {row['close_utc']} / {row['close_kst']}，"
                f"抓取 {row.get('fetched_at_utc')}，周期 {row['interval_seconds']} 秒，原因 `{row['reason']}`。"
            )
    else:
        lines.append("- 這次載入沒有再排除未收盤 K 線。")
    lines += [
        "",
        "## 主結果（保守預設）",
        "",
        "GeckoTerminal 的 `pool_fee_percentage` 是 null，歷史可賣性與歷史流動性也無法從 OHLCV 得知。保守預設因此**不開倉**。",
        "",
    ]
    lines.extend(_line_metrics(primary))
    lines += [
        "",
        f"被擋下的訊號例（第一筆）：{primary.skips[0]['utc'] if primary.skips else '無'} / {primary.skips[0]['kst'] if primary.skips else ''}，原因 {primary.skips[0]['reasons'] if primary.skips else []}。",
        f"單筆損失預算 ${budget_conservative:.2f} 與最大回撤 20% 都是**提議值**，不是使用者指定或已接受的風險額度。以本次 SOL 快照計，單邊鏈上費 {_usd(chain)}，來回 {_usd(2 * chain)}。{ _budget_sentence(budget_conservative, chain) }",
        "",
        "## 探索實驗（放寬實驗，不是完整風控策略）",
        "",
        "這個情境**不是**完整風控策略，也**不是**已套用 $0.10 提議預算的策略。單筆預算檢查沒有被關掉。`budget_gate_disabled` 在兩邊都是 false。差別是同一個欄位 `proposed_per_trade_loss_budget_usd` 從 "
        f"{format_param(budget_conservative)} 改成 {format_param(budget_exploratory)}。"
        "部位大小仍先受這個預算估計限制，再受現金扣除 0.05 SOL 預留的限制。預算變寬之後，現金上限會先綁住，名義金額可以讓虧損超過 $0.10。"
        "預算是進場當下用止損距離、雙邊百分比費用與兩筆鏈上費估出來的上限，不是成交後的硬性已實現虧損上限；跳空可以比估計更差。",
        "沒有為了讓結果轉正或增加成交而去改 RSI、相對量、止損倍數、止盈倍數或這兩個預算數字。",
        "",
        "與保守預設的參數差（只列出登記值；指標門檻沒有另調）：",
        "",
        "| 參數 | 保守預設 | 探索實驗 | |",
        "|---|---|---|---|",
    ]
    for row in scenario_diff_rows(primary.scenario, explor.scenario):
        mark = "不同" if row["changed"] else "相同"
        lines.append(f"| {row['label']} | {row['conservative']} | {row['exploratory']} | {mark} |")
    lines += [
        "",
        f"保守預設的 ${budget_conservative:.2f} {'小於' if budget_conservative <= 2 * chain else '不小於'}來回鏈上費 {_usd(2 * chain)}，所以在這份快照上，即使其他閘打開，保守預算也會讓部位為 0。探索實驗把預算改成 ${budget_exploratory:.2f} 之後，這條成本檢查不再把部位打成 0。可賣性閘與流動性閘是另外兩個被關掉的開關（true → false）。池費從 null 改成假設 0.003，狀態是假設，不是查到的費率。鏈上 0.005 SOL／邊、預留 0.05 SOL、GMGN 1%、滑點 30bp、RSI／RV／k_sl／k_tp、手動下一根開盤、以及 `no_reentry` 都沒有改。",
        "",
    ]
    lines.extend(_line_metrics(explor))
    lines += [
        "",
        f"- 成交落在哪一段：訓練 {explor.metrics['train_trade_count']}，驗證 {explor.metrics['validation_trade_count']}，留出 {explor.metrics['heldout_trade_count']}。留出段成交 {explor.metrics['heldout_trade_count']} 筆。這個 0 或非 0 都照實寫，沒有為了讓留出段出現交易而去改參數。",
        f"- `no_reentry={str(explor.scenario['no_reentry']).lower()}`。這是暫定開關，不是指標，也不是第一波偵測。第一筆出場之後，同一池在這次回測結束前的每一個新訊號都會被擋下，驗證段與留出段都包括在內。留出段成交 {explor.metrics['heldout_trade_count']} 筆是這個開關故意造成的抑制，不是已驗證的樣本外策略。",
    ]
    blocked = [s for s in explor.skips if "provisional_no_reentry" in s.get("reasons", [])]
    if blocked:
        lines.append(
            f"- 被這個暫定開關擋下的後續訊號 {len(blocked)} 筆。這是故意抑制之後所有新倉，不是第一波偵測的證據，也不是樣本外驗證。"
        )
        for skip in blocked:
            lines.append(f"  - {skip['segment']} · {skip['utc']} / {skip['kst']}")
    else:
        lines.append("- 這次沒有訊號被 `provisional_no_reentry` 擋下。若留出段成交為 0，原因要看上面的其他拒絕理由，不能改寫成第一波偵測。")
    for trade in explor.trades:
        exit_residual = trade.get("exit_residual")
        residual = "未平倉，沒有出場殘差" if exit_residual is None else f"{exit_residual:.6f}"
        entry_residual = trade.get("entry_residual")
        entry_residual_txt = "—" if entry_residual is None else f"{entry_residual:.6f}"
        lines += [
            "",
            f"成交一筆，狀態 {trade['status']}，進場段落 {trade['segment']}：",
            f"- 訊號 {trade.get('entry_signal_utc')} / {trade.get('entry_signal_kst')}，下一根開盤成交 {trade.get('entry_fill_utc')} / {trade.get('entry_fill_kst')}",
            f"- 出場訊號 {trade.get('exit_signal_utc')}（{trade.get('exit_reason')}），成交 {trade.get('exit_fill_utc')} / {trade.get('exit_fill_kst')}",
            f"- 已實現 {_usd(trade.get('realized_pnl'))}；未實現 {_usd(trade.get('unrealized_pnl'))}；GMGN 費 {_usd(trade.get('gmgn_fees'))}；池費 {_usd(trade.get('pool_fees'))}；鏈上費 {_usd(trade.get('chain_fees'))}",
            f"- 進場執行殘差（成交價 − 訊號收盤）{entry_residual_txt}；出場執行殘差（訊號收盤 − 成交價）{residual}",
            f"- same_bar_sl={trade.get('same_bar_sl')}。手動模式不用 high／low 成交，也不把止損價當成成交價。",
        ]
    cover = "預留大於或等於單邊鏈上費，所以下一根開盤即使接近 0，固定鏈上費仍可從進場後留下的現金支付，現金不會被記成負數。百分比費用從賣出名義扣除。" if reserve + 1e-9 >= chain else "預留小於單邊鏈上費。若賣出收入不夠付固定費，狀態是 COSTS_EXCEED_CASH_MARKED_ZERO，不記虛構賣出收入，現金維持原值。"
    bh = explor.benchmarks["buy_and_hold"].get("final_equity_usd")
    eq = explor.metrics["final_equity_usd"]
    if bh is None:
        bh_sentence = "保守路徑的買入持有因池費未知而沒有計算，沒有把池費當成 0。"
    elif eq > bh:
        bh_sentence = f"探索實驗期末 {_usd(eq)}，高於買入持有的未實現期末 {_usd(bh)}。策略大部分時間停在現金。這只說明少暴露在這一段價格裡，不是指標已被證明有預測力。"
    else:
        bh_sentence = f"探索實驗期末 {_usd(eq)}，沒有高於買入持有的未實現期末 {_usd(bh)}。少暴露不是指標有效的證明。"
    lines += [
        "",
        "### 成交與現金帳（沒有改參數）",
        "",
        f"- 公開情境的成交模型是 `{explor.scenario['execution_mode']}`。探索實驗的 same_bar_sl_first_count = {explor.metrics['same_bar_sl_first_count']}。止損與止盈在這個模式只比較已收盤的收盤價，掛到下一根開盤成交。",
        f"- 進場後現金至少留下預留 {_usd(reserve)}。單邊鏈上費 {_usd(chain)}。{cover}",
        f"- 探索實驗最低現金 {_usd(explor.metrics['min_cash'])}，餘額被截斷的次數 {explor.metrics['balance_clamp_events']}。每一根的權益＝該根當下的現金＋持倉數量×收盤價。已平倉且沒有截斷時，期末權益＝初始現金＋已實現損益。",
        f"- {bh_sentence}",
        "",
        "## 時間切分（依實際已收盤窗，50/25/25）",
        "",
        f"- 規則在看報酬之前就寫死：實際時間跨度的前 50% 訓練、接著 25% 驗證、最後 25% 留出。沒有用留出段重估 RSI／RV／ATR 分位。",
        f"- 第一根開盤 {start['utc']} / {start['kst']}",
        f"- 訓練結束（不含）{train_end['utc']} / {train_end['kst']}",
        f"- 驗證結束（不含）{val_end['utc']} / {val_end['kst']}",
        f"- 最後一根開盤 {end['utc']} / {end['kst']}；該根收盤 {end_close['utc']} / {end_close['kst']}",
        f"- 根數：訓練 {split['counts']['train']}，驗證 {split['counts']['validation']}，留出 {split['counts']['heldout']}",
        f"- 訓練段 ATR% 分位 [{explor.frozen_atr_band['quantile_low']}, {explor.frozen_atr_band['quantile_high']}] → 凍結區間 {_pct(explor.frozen_atr_band['low'])} 到 {_pct(explor.frozen_atr_band['high'])}（訓練樣本 {explor.frozen_atr_band['train_samples']}）。規格稿裡 2026-05-11 起的日曆三段，是在假設只有約六個月時寫的；這次 $WIF 合併窗更長，日曆邊界改由同一條比例規則落在實際已收盤窗上。",
        "",
        "## 資料窗與選擇（先寫條件，再看報酬）",
        "",
        bundle["selection_note"],
        "",
        f"- SOL 美元快照：{explor.scenario['sol_usd']}，時間 {explor.scenario['sol_usd_fetched_at_utc']} / {explor.scenario['sol_usd_fetched_at_kst']}，來源 {explor.scenario['sol_usd_source']}。這是換算用的快照，不是預測。",
        f"- 預留 0.05 SOL 約 {_usd(reserve)}，不能拿去開倉。可動用現金約 {_usd(10 - reserve)}。",
        f"- 鍵less `before_timestamp` 對選定的 $WIF 池又取回一頁。兩頁重疊的已收盤 K 線一致。回測使用的是合併後的已收盤日線 {explor.metrics['sample_bars']} 根，不是下載頁裡含未收盤最後一根的根數。選擇檔裡的原始頁根數包含抓取當下尚未收盤的 K 線，那份檔案沒有改寫。文件寫 Basic／keyless 大約 6 個月；這次呼叫實際回了更早的日線。不能据此說所有池都能超過 6 個月，只記錄這次回應。",
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
        f"- 已結束的機率桶 {poly.get('points')} 點（原始回應 {poly.get('raw_points')} 點，排除未完成或非桶報價 {poly.get('unclosed_point_count')} 點）。價格區間 {poly.get('min_price')}–{poly.get('max_price')}，最後已結束桶 {poly.get('last_price')}，單位是 0–1 機率。",
        f"- `has_more={poly.get('has_more')}`。抓取 {poly.get('fetched_at_utc')} / {poly.get('fetched_at_kst')}。",
        "- `resolution_seconds` 為 0 的終端報價不是已收盤的 12 小時桶，圖上不畫。沒有替它發明收盤時刻。",
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
        "- 「永遠不要發二次財」沒有收成唯一解釋。`no_reentry` 只是暫定開關：第一筆出場後故意擋掉同一池之後所有新倉，含驗證段與留出段。它不是第一波偵測，也不是已驗證的樣本外策略。",
        "",
    ]
    return "\n".join(lines) + "\n"
