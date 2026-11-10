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
