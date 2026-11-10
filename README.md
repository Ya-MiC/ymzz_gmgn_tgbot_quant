# 晏銘湛箴_gmgn_tgbot量化策略

紙上回測與本機預覽。**模擬損益，價格來自公開歷史資料。沒有錢包、沒有下單、沒有實盤，也不保證獲利。** Stock App 的產品身份仍未知，這裡沒有接上，也沒有用股票資料代替。

## 這次跑出來的數字

主結果用保守預設：GeckoTerminal 的池費是 null，歷史可賣性與歷史流動性也無法從 K 線得知，所以**不開倉**。

| 項目 | 數值 |
|---|---|
| 資料 | Solana `$WIF / SOL` 日線，池 `EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx`，代幣 `EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm` |
| 窗 | 已收盤日線。第一根開盤 2025-11-12 00:00 UTC（09:00 KST）。最後一根開盤 2026-11-09 00:00 UTC（09:00 KST），該根收盤 2026-11-10 00:00 UTC（09:00 KST）。363 根。2026-11-10 00:00 UTC 開盤的日線在抓取時（約 02:27–02:30 UTC）尚未收盤，已排除 |
| 切分 | 實際已收盤跨度的 50/25/25：訓練到 2026-05-12 00:00 UTC，驗證到 2026-08-10 12:00 UTC，其後為留出。根數 181 / 91 / 91。門檻沒有用留出段重估 |
| 保守預設 | **0 筆成交，期末 $10.00，報酬 0，勝率與獲利因子未定義** |
| SOL 快照 | $85.90，2026-11-10 02:27:01 UTC / 11:27:01 KST，CoinGecko keyless |

探索實驗是**放寬實驗，不是完整風控策略**。單筆預算檢查沒有被關掉：`proposed_per_trade_loss_budget_usd` 從提議的 **$0.10 改成 $3.00**，可賣性閘與流動性閘從 true 改成 false，池費從 null 改成假設 0.003。$0.10 小於來回鏈上費約 $0.86，所以保守預算即使打開其他閘也不會進場；改成 $3 之後，部位改由現金扣除 0.05 SOL 預留來限制，虧損可以超過 $0.10。指標門檻、鏈上 0.005 SOL、預留 0.05 SOL、`no_reentry` 都沒有為了獲利或更多成交而改。

這個放寬實驗在**訓練段**有 1 筆，已實現 **$-0.1452（-1.45%）**，期末 **$9.8548**，收盤最大回撤 **12.27%**。鏈上費 $0.859，大於 GMGN 費與假設池費。`no_reentry` 是暫定開關：第一筆出場後，同一池在這次回測結束前的新倉全部被擋下，其中驗證段 3 筆、留出段 3 筆。**留出段成交 0 筆。** 這不是第一波偵測，也不是已驗證的樣本外策略。費用敏感度裡，把鏈上費改成 0.002 SOL 時同一筆會變成正報酬；改回 0.005 或 0.006 又是負的。池費維持未知時仍然是 0 筆。

同一套探索假設在 SOL/USDC（管線，不是 meme）、BONK、POPCAT 上各有 1 筆，已實現報酬仍約 -15.20%、-16.73%、-17.66%。這四筆已平倉損益在排除未收盤日線之後沒有變。買入持有用的是最後一根已收盤的收盤價，所以市值有變：$WIF 未實現期末約 $6.40（-35.97%），賣出費還沒扣。少暴露不等於指標有效。

已收盤樣本的完整表：`results/LATEST_backtest.md`。含未收盤日線的上一版在 `results/superseded/`，已標成取代，不要再引用成 364 根已收盤。

## 預覽

- 靜態頁（不用安裝）：[`preview/index.html`](preview/index.html)
- 截圖：`artifacts/preview_full.png`、`artifacts/streamlit_default.png`
- 本機互動面板：`python3 -m streamlit run app/dashboard.py`

沒有部署網址。靜態頁就是預覽。

## 怎麼重跑

```bash
python3 -m pip install -r requirements.txt
python3 scripts/fetch_public_data.py
PYTHONPATH=src python3 -m pytest -q tests
python3 scripts/run_backtest.py
python3 scripts/build_preview.py
python3 -m streamlit run app/dashboard.py
```

這次測試是 **17 passed**。合成價格只存在測試裡，並標成排除在真實市場數字之外。

## 規則（v0）

最多三個指標：RSI(14)、ATR%(14)、相對成交量。流動性、可賣性、池費、資金是閘，不是第四個指標。`no_reentry` 是暫定開關：第一筆出場後擋掉同一池之後所有新倉，含驗證段與留出段。它不是第一波偵測，也不是已驗證的樣本外策略。訊號只用抓取時已收盤的 K 線，下一根開盤才成交。預設是手動通知模型，不用盤中 high／low，也不把止損價當成成交價。同一根若研究用掛單同時碰到止損與止盈，先算止損。初始資金 $10，不補倉、不馬丁、不加倉、現貨 1 倍。單筆損失預算 $0.10 與回撤 20% 是**提議值**，不是已接受的風險額度。放寬實驗把預算改成 $3，不是完整風控策略。預留 0.05 SOL 大於單邊鏈上 0.005 SOL，下一根的固定費從留下的現金支付。

## 參考倉庫

| 倉庫 | 完整 URL | 2026-11-10 查到的 commit | 授權 | 在這裡的角色 |
|---|---|---|---|---|
| kernc/backtesting.py | https://github.com/kernc/backtesting.py | `ca2e2611621e472542ba90f7243a1fa06a7d7108` | AGPL-3.0 | 只參考。未安裝、未匯入。引擎是本倉庫自寫的 |
| streamlit/streamlit | https://github.com/streamlit/streamlit | `86edf082ae9f4bd7fd9d5f45ab9bdd872709daa2` | Apache-2.0 | 依賴，本機面板 |
| plotly/plotly.py | https://github.com/plotly/plotly.py | `3c1aeba0a90ef6f7a32fd35a48338ef7ee349d93` | MIT | 依賴，面板圖。靜態預覽是 SVG，不載入 Plotly |
| GMGNAI/gmgn-skills | https://github.com/GMGNAI/gmgn-skills | `6a04e1f00b5463cfc965e41003ca0c7c2db5b69f` | MIT | 只參考。不是歷史行情，也沒有匯入 |
| polakowo/vectorbt | https://github.com/polakowo/vectorbt | `07f5e85e83a5286c396f4ecfd55dfaa05f25442d` | Apache-2.0 + Commons Clause | 未使用 |
| mementum/backtrader | https://github.com/mementum/backtrader | `b853d7c90b6721476eb5a5ea3135224e33db1f14` | GPL-3.0 | 未使用 |

本倉庫原創程式是 MIT。細節在 `NOTICE.md`。行情快照不是資料產品，見 `data/cache/README.md`。Powered by CoinGecko.

## 刻意沒做

- 不連 GMGN、Telegram 實發、MetaMask 或任何私鑰。`src/ymzz_quant/tg_adapter.py` 不能送出訊息，也沒有下單函式。
- 沒有把 15 分鐘整段抓下來。規格稿的主周期是 15 分鐘；這次完整窗是日線，不能把日線數字說成 15 分鐘績效。
- 沒有 point-in-time 宇宙。選定的是現在還查得到的 BONK / $WIF / POPCAT，再以名稱、池齡、覆蓋、儲備決定，不用報酬。死掉的池不在樣本裡。
- Polymarket 只顯示機率（這次是抓取當下 Gamma 未關閉列表的第一個市場），不和 $10 帳戶合併，也不用代幣 RSI 去算預測市場損益。
