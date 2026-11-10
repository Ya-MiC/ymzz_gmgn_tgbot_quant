# 本機研究服務

這是紙上研究。服務只綁 `127.0.0.1`。沒有部署網址，沒有下單，沒有私鑰，也沒有 Telegram 發送。

## 兩個介面分開

| 介面 | 位置 | 它實際做什麼 |
|---|---|---|
| 本機頁面 | `frontend/index.html`，由下面的指令在 `/` 提供 | 瀏覽器把整份設定 POST 到同一個行程的 `/api/backtest`，結果從那次回應畫出來 |
| Streamlit | `app/dashboard.py` | 在自己的行程裡直接呼叫引擎。它不是這支 HTTP API |
| 靜態預覽 | `preview/index.html` | 先前 WIF 研究的快照。不會重算 |
| 下載快照 | 回應裡的 `snapshot_html` | 只內嵌該一次結果。頁首寫明不會連線、不會重算 |

啟動：

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=src python3 -m ymzz_quant.api
```

瀏覽器開 `http://127.0.0.1:8765/`。埠可以放在指令後面，例如 `python3 -m ymzz_quant.api 8765`。

BTC/ETH 快取若要重抓：

```bash
python3 scripts/fetch_btc_eth.py
```

這支腳本用標準庫呼叫 Kraken 公開 OHLC。ccxt 沒有安裝。ccxt 是免費函式庫；沒有安裝它，也不代表可以用付費行情。Kraken 這個端點不需要 API 金鑰。

## 契約

成功是 HTTP 200，`ok: true`。設定錯誤是 HTTP 400，`ok: false`，`errors` 是 `{field, message}` 陣列，`result` 是 null。錯誤回應不含另一份資料的績效。

| 方法 | 路徑 | 作用 |
|---|---|---|
| GET | `/api/health` | 紙上、未部署 |
| GET | `/api/architecture` | 前後端位置與功能表 |
| GET | `/api/datasets` | 每份資料的市場、網路、報價、單位、周期、覆蓋、抓取時間、sha256 |
| GET | `/api/formulas` | RSI、ATR%、相對成交量、畫圖用 RSI、水平線、假設保證金 |
| GET | `/api/config/default?preset=` | 完整預設。`kraken_btc_spot_assumed_fees`、`kraken_eth_spot_assumed_fees`、`wif_conservative`、`wif_exploratory` |
| POST | `/api/config/validate` | 只檢查，不計算 |
| POST | `/api/backtest` | 檢查後呼叫 `ymzz_quant.engine.run_backtest` |
| GET | `/api/polymarket` | 機率。`shared_bankroll` 是 false |
| GET | `/api/wallets` | 地址清單與 CSV 欄位。不查鏈 |
| POST | `/api/wallets/add` | 公開地址與標籤 |
| POST | `/api/wallets/remove` | 從清單移除 |
| POST | `/api/wallets/import` | 檢查 CSV。不算損益 |

回測回應會回顯 `submitted_config`、`request_sha256`、`scenario`、`metrics.rsi_period`、`provenance`。`provenance` 的市場、網路、報價、單位、代號或池、來源 URL、抓取時間與 sha256 來自資料目錄，不是由表單另外編的。`indicators.rsi` 是引擎用來判斷的那一條。`display_only.rsi_overlays` 只供畫圖。

設定要帶的欄位：本金、RSI 周期與進場上下限、出場門檻、最多兩條比較 RSI、水平線、ATR 周期、相對成交量回看與門檻、停損與停利倍數、每邊費率、池費、滑點、延遲根數、SOL 成本與預留、開始與結束日、資料集、周期、代號、來源、池、單筆預算、回撤金額與比例、倍數、商品模式，以及假設借款費、資金費、維持率、強平罰則。本金必須大於 0 且不超過 10。預算與回撤金額不能超過本金。回撤比例必須等於金額除以本金。

## 資料與拒絕規則

已快取的周期只有各資料集自己的周期。Kraken 日線與小時線是 2026-11-10 的公開回應。日線最後一根已收盤開盤是 2026-11-09 00:00 UTC。抓取當下仍開著的那根已排除。小時線只有端點回傳的約 720 根。

送出 15m、資料集沒有的周期、早於第一根或晚於最後一根的日期，會得到 400。服務不會改去 WIF 日線或其他檔案。

現貨與 GMGN 池沒有原生保證金。`instrument_mode=spot` 時倍數必須是 1。`hypothetical_assumed_margin` 只接受 1、1.5、2，並用抵押、借入、假設費用與下一根開盤的假設平倉。大於 2 會拒絕。這個模式的標籤維持「不是真實永續回測」，因為沒有抓永續 K 線、標記價或資金費歷史。

`no_reentry` 是可選實驗。打開之後，第一筆出場會擋掉後面所有進場，含驗證段與留出段。它不是第一波偵測，也不能證明沒有第二波。

地址模組不把轉帳、入金、出金當成交易，也不計算損益。聰明錢分類、熱門地址新進資金、歷史可賣性與第一波偵測沒有實作。沒有錢包連線。

Stock App 沒有連接。沒有用股價資料代替。

## 引擎與依賴

決策與成交在 `src/ymzz_quant/engine.py`。這次沒有改用 backtesting.py、vectorbt 或 backtrader。HTTP 用標準庫 `http.server`。圖是頁面上的 SVG，不載入 Plotly。Streamlit 與 Plotly 仍只服務舊的本機面板。版本與授權見 `README.md` 與 `NOTICE.md`。
