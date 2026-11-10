# 執行紀錄

時間：2026-11-10 11:42 KST 起（報告檔 `results/2026-11-10_114212_KST_backtest.md`）。

```text
PYTHONPATH=src python3 -m pytest -q tests
14 passed

python3 scripts/run_backtest.py
wif_daily conservative_no_trade trades=0 return=0.000000 equity=10.0000
wif_daily exploratory_ohlcv_only trades=1 return=-0.014524 equity=9.8548
sol_usdc_daily conservative_no_trade trades=0 return=0.000000 equity=10.0000
sol_usdc_daily exploratory_ohlcv_only trades=1 return=-0.151980 equity=8.4802
bonk_daily_appendix conservative_no_trade trades=0 return=0.000000 equity=10.0000
bonk_daily_appendix exploratory_ohlcv_only trades=1 return=-0.167283 equity=8.3272
popcat_daily_appendix conservative_no_trade trades=0 return=0.000000 equity=10.0000
popcat_daily_appendix exploratory_ohlcv_only trades=1 return=-0.176617 equity=8.2338

python3 scripts/build_preview.py
```

資料抓取在更早的 `python3 scripts/fetch_public_data.py` 與 `--continue`。SOL 快照 $85.90，2026-11-10 02:27:01 UTC / 11:27:01 KST。

Streamlit 預設頁（保守情境）以應用測試跑完：期末權益 $10.00、成交 0、三張圖、沒有例外。瀏覽器也打開本機 `http://127.0.0.1:8599/`，頁面文字包含「沒有成交」「未計算」「倖存者與選定池」。靜態預覽是 `preview/index.html`，截圖在 `artifacts/`。

## 2026-11-10 更正：排除未收盤 K 線

上一份 `results/2026-11-10_114212_KST_backtest.md` 把 2026-11-10 00:00 UTC 的日線算進 364 根。該 K 線在抓取時尚未收盤，已標成取代，原文在 `results/superseded/`。

更正後重跑：

```text
PYTHONPATH=src python3 -m pytest -q tests
17 passed

PYTHONPATH=src python3 scripts/run_backtest.py
PYTHONPATH=src python3 scripts/build_preview.py
```

$WIF 已收盤 363 根。報告檔 `results/2026-11-10_120939_KST_backtest.md`。四個樣本的已平倉損益與費用敏感度格子沒有變。切分邊界、訓練 ATR 分位樣本數，以及買入持有的最後收盤市值有變。留出段成交仍是 0，原因是暫定的 `no_reentry`，不是樣本外驗證。Streamlit 預設頁文字含「已收盤 363 根」「已排除未收盤 1 根」「留出段成交 0 筆」，期末權益 $10、成交 0。
