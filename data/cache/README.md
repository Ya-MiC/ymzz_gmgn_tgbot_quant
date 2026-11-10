# 公開資料快照

這些 JSON 是 2026-11-10 從免金鑰公開端點抓下來的原始回應，用來讓這次回測的數字可以被對上同一批 K 線。

CoinGecko API 條款不鼓勵快取，並要求若必須保存則至少每 24 小時更新，同時標示 Powered by CoinGecko。條款沒有把「把歷史檔放進公開倉庫再轉售」授權出去。這裡留下快照只為了核對這一篇紙上回測，不是資料產品。要更新請重跑 `python3 scripts/fetch_public_data.py`。若權利人要求移除，刪掉本目錄即可，腳本仍可重抓。

GeckoTerminal 池 OHLCV 不是 GMGN 官方歷史檔。Polymarket 的檔是 0–1 機率，不是代幣價格。`gt_ohlcv_day_Ebbpz3PW.json` 是搜尋「bonk」時誤抓的 BERN 池，已拒絕，不進入績效。

`kraken_ohlc_XBTUSD_1440.json`、`kraken_ohlc_ETHUSD_1440.json`、`kraken_ohlc_XBTUSD_60.json`、`kraken_ohlc_ETHUSD_60.json` 是 2026-11-10 從 Kraken 公開 OHLC 抓的原始回應，沒有 API 金鑰。sidecar 裡有 URL、抓取時間與 sha256。載入時會拿掉抓取當下尚未收盤的最後一根。Kraken 這次只回了最近約 720 根，小時線因此只有大約一個月。這是再現用快照，不是資料產品。沒有 15 分鐘檔。要求 15 分鐘不會改用這些日線。
