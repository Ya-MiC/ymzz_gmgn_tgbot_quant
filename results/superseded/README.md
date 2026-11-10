# 已取代

`2026-11-10_114212_KST_backtest_OPEN_BAR.md`、`preview_index_OPEN_BAR.html`、三張截圖，以及 `wif_exploratory_trades_OPEN_BAR.csv` 是排除未收盤日線之前的版本。

那一版把 2026-11-10 00:00 UTC 開盤的日線算進樣本，並寫成 364 根。該 K 線要到 2026-11-11 00:00 UTC 才收盤，抓取時間是 2026-11-10 02:27–02:30 UTC，所以當時仍是未收盤。不要把那一版的窗終點或「364 根」說成已收盤、無前視的覆蓋。

更正後的報告是 `results/LATEST_backtest.md`。
