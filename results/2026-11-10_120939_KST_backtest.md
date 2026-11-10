# 晏銘湛箴_gmgn_tgbot量化策略 — 紙上回測紀錄

- 產生時間：2026-11-10 12:09:39 KST（2026-11-10 03:09:39 UTC）
- 性質：**模擬損益，價格是公開歷史成交彙總的 OHLCV。不是實盤、不是錢包、不是獲利保證。**
- 徽章：`SIMULATED PnL ON REAL PRICES`
- 已取代：`results/2026-11-10_114212_KST_backtest.md` 與當時的預覽把 2026-11-10 00:00 UTC 開盤、尚未收盤的日線算進 364 根。那一版見 `results/superseded/`，不要再引用成已收盤樣本。
- Stock App：身份未確認，**整合不可用**。沒有用 yfinance 或股票資料頂替。
- 引擎：本倉庫自寫的現貨回測。未安裝、未呼叫 `backtesting.py`。

## 已排除的未收盤 K 線

GeckoTerminal 的時間戳是 K 線**開盤**。一根 K 線只有在 `開盤 + 該周期秒數 <= 該檔的抓取時間` 時才算已收盤。抓取時間剛好等於收盤時刻算已收盤；沒有抓取時間則不當成已收盤。同一根若有一份是收盤後抓到的，就保留那一份。

- 排除開盤 2026-11-10T00:00:00Z / 2026-11-10T09:00:00+0900，收盤 2026-11-11T00:00:00Z / 2026-11-11T09:00:00+0900，抓取 2026-11-10T02:28:22Z，周期 86400 秒，原因 `unclosed_at_fetch`。

## 主結果（保守預設）

GeckoTerminal 的 `pool_fee_percentage` 是 null，歷史可賣性與歷史流動性也無法從 OHLCV 得知。保守預設因此**不開倉**。

- 已收盤 K 線：363 根。時間戳是開盤，不是收盤。第一根開盤 2025-11-12T00:00:00Z / 2025-11-12T09:00:00+0900。最後一根開盤 2026-11-09T00:00:00Z / 2026-11-09T09:00:00+0900，該根收盤 2026-11-10T00:00:00Z / 2026-11-10T09:00:00+0900。抓取時尚未收盤、已排除：1 根。缺口數只描述這些已收盤 K 線之間的間隔，不能把未收盤的最後一根算進樣本，也不能把『缺口 0』說成含未完成 K 線的無前視覆蓋。
- 成交筆數：0（已平 0，未平 0）
- 期末權益：$10.0000；總報酬：0.00%；已實現 $0.0000；未實現 $0.0000
- 最大回撤（收盤市值，不是盤中）：0.00%
- 費用（GMGN＋池費，池費若為假設會另標）：$0.0000；鏈上費美元：$0.0000
- 勝率：未定義（沒有已平倉交易）；獲利因子：未定義
- 被擋下的指標訊號：7
- 現金基準：$10.0000
- 買入持有：狀態 skipped；期末 —；報酬 未定義；最大回撤 未定義。
- 這段沒有成交。報酬記 0，不是獲利。

被擋下的訊號例（第一筆）：2026-03-06T00:00:00Z / 2026-03-06T09:00:00+0900，原因 ['sellability_unknown', 'liquidity_history_unknown', 'pool_fee_unknown']。
單筆損失預算 $0.10 與最大回撤 20% 都是**提議值**，不是使用者指定或已接受的風險額度。以本次 SOL 快照計，單邊鏈上費 $0.4295，來回 $0.8590。這個預算小於或等於來回鏈上費 $0.8590，所以即便安全閘打開，部位也會是 0。

## 探索實驗（放寬實驗，不是完整風控策略）

這個情境**不是**完整風控策略，也**不是**已套用 $0.10 提議預算的策略。單筆預算檢查沒有被關掉。`budget_gate_disabled` 在兩邊都是 false。差別是同一個欄位 `proposed_per_trade_loss_budget_usd` 從 0.1 改成 3。部位大小仍先受這個預算估計限制，再受現金扣除 0.05 SOL 預留的限制。預算變寬之後，現金上限會先綁住，名義金額可以讓虧損超過 $0.10。預算是進場當下用止損距離、雙邊百分比費用與兩筆鏈上費估出來的上限，不是成交後的硬性已實現虧損上限；跳空可以比估計更差。
沒有為了讓結果轉正或增加成交而去改 RSI、相對量、止損倍數、止盈倍數或這兩個預算數字。

與保守預設的參數差（只列出登記值；指標門檻沒有另調）：

| 參數 | 保守預設 | 探索實驗 | |
|---|---|---|---|
| 提議的單筆損失預算（美元） | 0.1 | 3 | 不同 |
| 單筆預算檢查是否被關掉 | false | false | 相同 |
| 池費每邊 | null | 0.003 | 不同 |
| 池費狀態 | unknown_geckoterminal_pool_fee_percentage_null | ASSUMED_because_geckoterminal_pool_fee_percentage_was_null | 不同 |
| 可賣性未知就拒絕進場 | true | false | 不同 |
| 流動性未知就拒絕進場 | true | false | 不同 |
| 歷史可賣性是否已知 | false | false | 相同 |
| 歷史流動性是否已知 | false | false | 相同 |
| 池費未知就拒絕 | true | true | 相同 |
| 鏈上費（SOL／邊） | 0.005 | 0.005 | 相同 |
| 錢包預留（SOL） | 0.05 | 0.05 | 相同 |
| GMGN 費每邊 | 0.01 | 0.01 | 相同 |
| 買入滑點（bp） | 30 | 30 | 相同 |
| 賣出滑點（bp） | 30 | 30 | 相同 |
| 成交模型 | manual_tg_next_open | manual_tg_next_open | 相同 |
| 同一池不再進場 | true | true | 相同 |
| k_sl | 1.5 | 1.5 | 相同 |
| k_tp | 2 | 2 | 相同 |
| RSI 下限 | 25 | 25 | 相同 |
| RSI 上限 | 40 | 40 | 相同 |
| RSI 出場 | 70 | 70 | 相同 |
| 相對量下限 | 1.5 | 1.5 | 相同 |
| 提議的最大回撤 | 0.2 | 0.2 | 相同 |
| 初始現金（美元） | 10 | 10 | 相同 |

保守預設的 $0.10 小於來回鏈上費 $0.8590，所以在這份快照上，即使其他閘打開，保守預算也會讓部位為 0。探索實驗把預算改成 $3.00 之後，這條成本檢查不再把部位打成 0。可賣性閘與流動性閘是另外兩個被關掉的開關（true → false）。池費從 null 改成假設 0.003，狀態是假設，不是查到的費率。鏈上 0.005 SOL／邊、預留 0.05 SOL、GMGN 1%、滑點 30bp、RSI／RV／k_sl／k_tp、手動下一根開盤、以及 `no_reentry` 都沒有改。

- 已收盤 K 線：363 根。時間戳是開盤，不是收盤。第一根開盤 2025-11-12T00:00:00Z / 2025-11-12T09:00:00+0900。最後一根開盤 2026-11-09T00:00:00Z / 2026-11-09T09:00:00+0900，該根收盤 2026-11-10T00:00:00Z / 2026-11-10T09:00:00+0900。抓取時尚未收盤、已排除：1 根。缺口數只描述這些已收盤 K 線之間的間隔，不能把未收盤的最後一根算進樣本，也不能把『缺口 0』說成含未完成 K 線的無前視覆蓋。
- 成交筆數：1（已平 1，未平 0）
- 期末權益：$9.8548；總報酬：-1.45%；已實現 $-0.1452；未實現 $0.0000
- 最大回撤（收盤市值，不是盤中）：12.27%
- 費用（GMGN＋池費，池費若為假設會另標）：$0.1466；鏈上費美元：$0.8590
- 勝率：0.00%；獲利因子：0.0
- 被擋下的指標訊號：6
- 現金基準：$10.0000
- 買入持有：狀態 marked_unrealized_at_end；期末 $6.4028；報酬 -35.97%；最大回撤 40.02%。買入後持有到最後收盤。期末是未實現市值，未扣賣出費用，不是成交。

- 成交落在哪一段：訓練 1，驗證 0，留出 0。留出段成交 0 筆。這個 0 或非 0 都照實寫，沒有為了讓留出段出現交易而去改參數。
- `no_reentry=true`。這是暫定開關，不是指標，也不是第一波偵測。第一筆出場之後，同一池在這次回測結束前的每一個新訊號都會被擋下，驗證段與留出段都包括在內。留出段成交 0 筆是這個開關故意造成的抑制，不是已驗證的樣本外策略。
- 被這個暫定開關擋下的後續訊號 6 筆。這是故意抑制之後所有新倉，不是第一波偵測的證據，也不是樣本外驗證。
  - validation · 2026-06-02T00:00:00Z / 2026-06-02T09:00:00+0900
  - validation · 2026-06-04T00:00:00Z / 2026-06-04T09:00:00+0900
  - validation · 2026-06-05T00:00:00Z / 2026-06-05T09:00:00+0900
  - heldout · 2026-10-30T00:00:00Z / 2026-10-30T09:00:00+0900
  - heldout · 2026-11-02T00:00:00Z / 2026-11-02T09:00:00+0900
  - heldout · 2026-11-04T00:00:00Z / 2026-11-04T09:00:00+0900

成交一筆，狀態 CLOSED，進場段落 train：
- 訊號 2026-03-06T00:00:00Z / 2026-03-06T09:00:00+0900，下一根開盤成交 2026-03-07T00:00:00Z / 2026-03-07T09:00:00+0900
- 出場訊號 2026-05-06T00:00:00Z（rsi_exit_next_open），成交 2026-05-07T00:00:00Z / 2026-05-07T09:00:00+0900
- 已實現 $-0.1452；未實現 —；GMGN 費 $0.1128；池費 $0.0338；鏈上費 $0.8590
- 進場執行殘差（成交價 − 訊號收盤）0.000569；出場執行殘差（訊號收盤 − 成交價）0.000667
- same_bar_sl=False。手動模式不用 high／low 成交，也不把止損價當成成交價。

### 成交與現金帳（沒有改參數）

- 公開情境的成交模型是 `manual_tg_next_open`。探索實驗的 same_bar_sl_first_count = 0。止損與止盈在這個模式只比較已收盤的收盤價，掛到下一根開盤成交。
- 進場後現金至少留下預留 $4.2950。單邊鏈上費 $0.4295。預留大於或等於單邊鏈上費，所以下一根開盤即使接近 0，固定鏈上費仍可從進場後留下的現金支付，現金不會被記成負數。百分比費用從賣出名義扣除。
- 探索實驗最低現金 $4.2950，餘額被截斷的次數 0。每一根的權益＝該根當下的現金＋持倉數量×收盤價。已平倉且沒有截斷時，期末權益＝初始現金＋已實現損益。
- 探索實驗期末 $9.8548，高於買入持有的未實現期末 $6.4028。策略大部分時間停在現金。這只說明少暴露在這一段價格裡，不是指標已被證明有預測力。

## 時間切分（依實際已收盤窗，50/25/25）

- 規則在看報酬之前就寫死：實際時間跨度的前 50% 訓練、接著 25% 驗證、最後 25% 留出。沒有用留出段重估 RSI／RV／ATR 分位。
- 第一根開盤 2025-11-12T00:00:00Z / 2025-11-12T09:00:00+0900
- 訓練結束（不含）2026-05-12T00:00:00Z / 2026-05-12T09:00:00+0900
- 驗證結束（不含）2026-08-10T12:00:00Z / 2026-08-10T21:00:00+0900
- 最後一根開盤 2026-11-09T00:00:00Z / 2026-11-09T09:00:00+0900；該根收盤 2026-11-10T00:00:00Z / 2026-11-10T09:00:00+0900
- 根數：訓練 181，驗證 91，留出 91
- 訓練段 ATR% 分位 [0.2, 0.9] → 凍結區間 7.02% 到 11.17%（訓練樣本 167）。規格稿裡 2026-05-11 起的日曆三段，是在假設只有約六個月時寫的；這次 $WIF 合併窗更長，日曆邊界改由同一條比例規則落在實際已收盤窗上。

## 資料窗與選擇（先寫條件，再看報酬）

選擇紀錄（報酬計算之前寫下的條件，以及事後沒有用報酬改選）：

```json
{
  "declared_before_ohlcv": true,
  "purpose": "exploratory survivor pool, not a point-in-time universe and not meme-market performance",
  "queries": [
    "bonk",
    "wif",
    "popcat"
  ],
  "why_these_names": "BONK, WIF, and POPCAT are widely known Solana meme tokens that began trading well before this keyless window. They are selected because a multi-week history is plausible, not because of any return. Pools that already died and left the search index cannot appear. This is survivorship plus selected-pool bias.",
  "rank": "highest reserve_in_usd only; price_change_percentage is ignored and not stored",
  "quote_allow": [
    "SOL",
    "WSOL",
    "USDC",
    "USDT"
  ],
  "exclude_pool": "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE",
  "qualify": {
    "min_daily_bars": 60,
    "min_span_days": 21
  },
  "among_qualified": "longest span_days, tie-break higher reserve_in_usd",
  "major_pair_role": "plumbing baseline only; must not be reported as meme performance",
  "fetched_at_utc": "2026-11-10T02:27:01Z",
  "fetched_at_kst": "2026-11-10T11:27:01+0900",
  "exact_name": "base name must match BONK, $WIF/WIF, or POPCAT versus SOL/WSOL/USDC/USDT; fuzzy search hits are rejected",
  "mature_pool_created_before": "2026-05-01T00:00:00Z",
  "tightened_at": {
    "fetched_at_utc": "2026-11-10T02:30:03Z",
    "fetched_at_kst": "2026-11-10T11:30:03+0900"
  }
}

```

```json
{
  "criteria_file": "data/cache/selection_criteria.json",
  "correction": "The first automated pass accepted fuzzy search hits (BERN ranked above Bonk). That pass is rejected. This decision uses exact ticker names and pool_created_at before 2026-05-01. Strategy returns were not computed before this correction.",
  "rejected_false_positive_pool": {
    "name": "BERN / SOL",
    "address": "Ebbpz3PWLaQxj2oyK967RgEPbcPypjQCoZ3tpB4fwLsk",
    "reason": "fuzzy search for bonk; not the BONK token"
  },
  "candidates_top_by_reserve": [
    {
      "id": "solana_5zpyutJu9ee6jFymDGoK7F6S5Kczqtc9FomP3ueKuyA9",
      "name": "Bonk / SOL",
      "address": "5zpyutJu9ee6jFymDGoK7F6S5Kczqtc9FomP3ueKuyA9",
      "reserve_in_usd": 274685.3406,
      "pool_created_at": "2023-07-05T14:41:09Z",
      "base_token_symbol": null,
      "quote_token_symbol": null,
      "base_token_address": null,
      "quote_token_address": null,
      "dex": "orca",
      "price_change_percentage": null,
      "query": "bonk",
      "search_rank_by_reserve": 1,
      "exact_match_count": 13,
      "rejected_examples": [
        {
          "name": "Bonk / USDC",
          "address": "5Dp922oSaj9rdLHTxZzq1B7QV7KmwY7U7K1JNCRhc45J",
          "reason": "created_inside_or_after_window",
          "pool_created_at": "2026-06-16T19:28:58Z"
        },
        {
          "name": "Bonk / SOL 0.25%",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "BONKAI / SOL",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "LetsBONK / SOL",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "BONKY / Bonk",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "BERN / SOL",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "SAVIOUR / SOL",
          "reason": "fuzzy_or_different_ticker"
        }
      ],
      "daily": {
        "bars": 184,
        "newest_ts": 1794268800,
        "oldest_ts": 1778457600,
        "newest_utc": "2026-11-10T00:00:00Z",
        "oldest_utc": "2026-05-11T00:00:00Z",
        "span_days": 183.0
      }
    },
    {
      "id": "solana_EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx",
      "name": "$WIF / SOL",
      "address": "EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx",
      "reserve_in_usd": 4625709.1515,
      "pool_created_at": "2023-11-20T20:10:04Z",
      "base_token_symbol": null,
      "quote_token_symbol": null,
      "base_token_address": null,
      "quote_token_address": null,
      "dex": "raydium",
      "price_change_percentage": null,
      "query": "wif",
      "search_rank_by_reserve": 1,
      "exact_match_count": 5,
      "rejected_examples": [
        {
          "name": "wifout / $WIF",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "swordcat / SOL",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "WIFE / SOL",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "swordcat / SOL",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "KWIF / SOL",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "WIF / SOL",
          "address": "JTsSu7MiYCFAoMGNL9zwR2UzLCCJKNA6KpQJFQzppEx",
          "reason": "created_inside_or_after_window",
          "pool_created_at": "2026-11-01T02:33:36Z"
        },
        {
          "name": "WIFLOAT / SOL",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "WIFORANGE / SOL",
          "reason": "fuzzy_or_different_ticker"
        }
      ],
      "daily": {
        "bars": 184,
        "newest_ts": 1794268800,
        "oldest_ts": 1778457600,
        "newest_utc": "2026-11-10T00:00:00Z",
        "oldest_utc": "2026-05-11T00:00:00Z",
        "span_days": 183.0
      }
    },
    {
      "id": "solana_FRhB8L7Y9Qq41qZXYLtC2nw8An1RJfLLxRF2x9RwLLMo",
      "name": "POPCAT / SOL",
      "address": "FRhB8L7Y9Qq41qZXYLtC2nw8An1RJfLLxRF2x9RwLLMo",
      "reserve_in_usd": 2810820.856,
      "pool_created_at": "2023-12-12T22:00:11Z",
      "base_token_symbol": null,
      "quote_token_symbol": null,
      "base_token_address": null,
      "quote_token_address": null,
      "dex": "raydium",
      "price_change_percentage": null,
      "query": "popcat",
      "search_rank_by_reserve": 1,
      "exact_match_count": 8,
      "rejected_examples": [
        {
          "name": "POPCAT / Coinomi",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "POPCAT / TOPCAT",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "POPCAT / POPDAT",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "POPCAT / $WIF",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "POPCAT / SPX",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "POPCAT / USDC",
          "address": "GaDLUkaMH1XG784V1kny54BJnSHkrWuxESDsJ9kSEZ1f",
          "reason": "created_inside_or_after_window",
          "pool_created_at": "2026-05-25T09:43:13Z"
        },
        {
          "name": "POPCAT / Fartcoin",
          "reason": "fuzzy_or_different_ticker"
        },
        {
          "name": "POPCAT / Fartcoin",
          "reason": "fuzzy_or_different_ticker"
        }
      ],
      "daily": {
        "bars": 184,
        "newest_ts": 1794268800,
        "oldest_ts": 1778457600,
        "newest_utc": "2026-11-10T00:00:00Z",
        "oldest_utc": "2026-05-11T00:00:00Z",
        "span_days": 183.0
      }
    }
  ],
  "qualified": [
    {
      "address": "EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx",
      "name": "$WIF / SOL",
      "span_days": 183.0,
      "bars": 184
    },
    {
      "address": "FRhB8L7Y9Qq41qZXYLtC2nw8An1RJfLLxRF2x9RwLLMo",
      "name": "POPCAT / SOL",
      "span_days": 183.0,
      "bars": 184
    },
    {
      "address": "5zpyutJu9ee6jFymDGoK7F6S5Kczqtc9FomP3ueKuyA9",
      "name": "Bonk / SOL",
      "span_days": 183.0,
      "bars": 184
    }
  ],
  "chosen": {
    "id": "solana_EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx",
    "name": "$WIF / SOL",
    "address": "EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx",
    "reserve_in_usd": 4625709.1515,
    "pool_created_at": "2023-11-20T20:10:04Z",
    "base_token_symbol": null,
    "quote_token_symbol": null,
    "base_token_address": null,
    "quote_token_address": null,
    "dex": "raydium",
    "price_change_percentage": null,
    "query": "wif",
    "search_rank_by_reserve": 1,
    "exact_match_count": 5,
    "rejected_examples": [
      {
        "name": "wifout / $WIF",
        "reason": "fuzzy_or_different_ticker"
      },
      {
        "name": "swordcat / SOL",
        "reason": "fuzzy_or_different_ticker"
      },
      {
        "name": "WIFE / SOL",
        "reason": "fuzzy_or_different_ticker"
      },
      {
        "name": "swordcat / SOL",
        "reason": "fuzzy_or_different_ticker"
      },
      {
        "name": "KWIF / SOL",
        "reason": "fuzzy_or_different_ticker"
      },
      {
        "name": "WIF / SOL",
        "address": "JTsSu7MiYCFAoMGNL9zwR2UzLCCJKNA6KpQJFQzppEx",
        "reason": "created_inside_or_after_window",
        "pool_created_at": "2026-11-01T02:33:36Z"
      },
      {
        "name": "WIFLOAT / SOL",
        "reason": "fuzzy_or_different_ticker"
      },
      {
        "name": "WIFORANGE / SOL",
        "reason": "fuzzy_or_different_ticker"
      }
    ],
    "daily": {
      "bars": 184,
      "newest_ts": 1794268800,
      "oldest_ts": 1778457600,
      "newest_utc": "2026-11-10T00:00:00Z",
      "oldest_utc": "2026-05-11T00:00:00Z",
      "span_days": 183.0
    }
  },
  "insufficient": false,
  "note": "History length is a coverage filter declared before returns. It is not a performance filter. Price returns are not computed in this script.",
  "fetched_at_utc": "2026-11-10T02:30:17Z",
  "fetched_at_kst": "2026-11-10T11:30:17+0900"
}

```

- SOL 美元快照：85.9，時間 2026-11-10T02:27:01Z / 2026-11-10T11:27:01+0900，來源 https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd。這是換算用的快照，不是預測。
- 預留 0.05 SOL 約 $4.2950，不能拿去開倉。可動用現金約 $5.7050。
- 鍵less `before_timestamp` 對選定的 $WIF 池又取回一頁。兩頁重疊的已收盤 K 線一致。回測使用的是合併後的已收盤日線 363 根，不是下載頁裡含未收盤最後一根的根數。選擇檔裡的原始頁根數包含抓取當下尚未收盤的 K 線，那份檔案沒有改寫。文件寫 Basic／keyless 大約 6 個月；這次呼叫實際回了更早的日線。不能据此說所有池都能超過 6 個月，只記錄這次回應。
- 規格稿的主周期是 15 分鐘。本輪完整窗是**日線**。沒有把日線結果說成 15 分鐘策略績效。
- OHLCV 不能證明當時買得進、賣得出。失敗出場與貔貅都沒有被這份 K 線證實或排除。

## 其他樣本（同一凍結規則，不用來改門檻）

### SOL / USDC · 主流 SOL/USDC 管線基準，不可當成 meme 績效 · conservative_no_trade

- 已收盤 K 線：183 根。時間戳是開盤，不是收盤。第一根開盤 2026-05-11T00:00:00Z / 2026-05-11T09:00:00+0900。最後一根開盤 2026-11-09T00:00:00Z / 2026-11-09T09:00:00+0900，該根收盤 2026-11-10T00:00:00Z / 2026-11-10T09:00:00+0900。抓取時尚未收盤、已排除：1 根。缺口數只描述這些已收盤 K 線之間的間隔，不能把未收盤的最後一根算進樣本，也不能把『缺口 0』說成含未完成 K 線的無前視覆蓋。
- 成交筆數：0（已平 0，未平 0）
- 期末權益：$10.0000；總報酬：0.00%；已實現 $0.0000；未實現 $0.0000
- 最大回撤（收盤市值，不是盤中）：0.00%
- 費用（GMGN＋池費，池費若為假設會另標）：$0.0000；鏈上費美元：$0.0000
- 勝率：未定義（沒有已平倉交易）；獲利因子：未定義
- 被擋下的指標訊號：1
- 現金基準：$10.0000
- 買入持有：狀態 skipped；期末 —；報酬 未定義；最大回撤 未定義。
- 這段沒有成交。報酬記 0，不是獲利。

### SOL / USDC · 主流 SOL/USDC 管線基準，不可當成 meme 績效 · exploratory_ohlcv_only

- 已收盤 K 線：183 根。時間戳是開盤，不是收盤。第一根開盤 2026-05-11T00:00:00Z / 2026-05-11T09:00:00+0900。最後一根開盤 2026-11-09T00:00:00Z / 2026-11-09T09:00:00+0900，該根收盤 2026-11-10T00:00:00Z / 2026-11-10T09:00:00+0900。抓取時尚未收盤、已排除：1 根。缺口數只描述這些已收盤 K 線之間的間隔，不能把未收盤的最後一根算進樣本，也不能把『缺口 0』說成含未完成 K 線的無前視覆蓋。
- 成交筆數：1（已平 1，未平 0）
- 期末權益：$8.4802；總報酬：-15.20%；已實現 $-1.5198；未實現 $0.0000
- 最大回撤（收盤市值，不是盤中）：15.20%
- 費用（GMGN＋池費，池費若為假設會另標）：$0.1285；鏈上費美元：$0.8590
- 勝率：0.00%；獲利因子：0.0
- 被擋下的指標訊號：0
- 現金基準：$10.0000
- 買入持有：狀態 marked_unrealized_at_end；期末 $9.5906；報酬 -4.09%；最大回撤 19.10%。買入後持有到最後收盤。期末是未實現市值，未扣賣出費用，不是成交。

### Bonk / SOL · 附錄：同一規則的 BONK 池，沒有用來挑選主池 · conservative_no_trade

- 已收盤 K 線：183 根。時間戳是開盤，不是收盤。第一根開盤 2026-05-11T00:00:00Z / 2026-05-11T09:00:00+0900。最後一根開盤 2026-11-09T00:00:00Z / 2026-11-09T09:00:00+0900，該根收盤 2026-11-10T00:00:00Z / 2026-11-10T09:00:00+0900。抓取時尚未收盤、已排除：1 根。缺口數只描述這些已收盤 K 線之間的間隔，不能把未收盤的最後一根算進樣本，也不能把『缺口 0』說成含未完成 K 線的無前視覆蓋。
- 成交筆數：0（已平 0，未平 0）
- 期末權益：$10.0000；總報酬：0.00%；已實現 $0.0000；未實現 $0.0000
- 最大回撤（收盤市值，不是盤中）：0.00%
- 費用（GMGN＋池費，池費若為假設會另標）：$0.0000；鏈上費美元：$0.0000
- 勝率：未定義（沒有已平倉交易）；獲利因子：未定義
- 被擋下的指標訊號：5
- 現金基準：$10.0000
- 買入持有：狀態 skipped；期末 —；報酬 未定義；最大回撤 未定義。
- 這段沒有成交。報酬記 0，不是獲利。

### Bonk / SOL · 附錄：同一規則的 BONK 池，沒有用來挑選主池 · exploratory_ohlcv_only

- 已收盤 K 線：183 根。時間戳是開盤，不是收盤。第一根開盤 2026-05-11T00:00:00Z / 2026-05-11T09:00:00+0900。最後一根開盤 2026-11-09T00:00:00Z / 2026-11-09T09:00:00+0900，該根收盤 2026-11-10T00:00:00Z / 2026-11-10T09:00:00+0900。抓取時尚未收盤、已排除：1 根。缺口數只描述這些已收盤 K 線之間的間隔，不能把未收盤的最後一根算進樣本，也不能把『缺口 0』說成含未完成 K 線的無前視覆蓋。
- 成交筆數：1（已平 1，未平 0）
- 期末權益：$8.3272；總報酬：-16.73%；已實現 $-1.6728；未實現 $0.0000
- 最大回撤（收盤市值，不是盤中）：16.73%
- 費用（GMGN＋池費，池費若為假設會另標）：$0.1265；鏈上費美元：$0.8590
- 勝率：0.00%；獲利因子：0.0
- 被擋下的指標訊號：4
- 現金基準：$10.0000
- 買入持有：狀態 marked_unrealized_at_end；期末 $6.6937；報酬 -33.06%；最大回撤 37.91%。買入後持有到最後收盤。期末是未實現市值，未扣賣出費用，不是成交。

### POPCAT / SOL · 附錄：同一規則的 POPCAT/SOL 池，沒有用來挑選主池 · conservative_no_trade

- 已收盤 K 線：183 根。時間戳是開盤，不是收盤。第一根開盤 2026-05-11T00:00:00Z / 2026-05-11T09:00:00+0900。最後一根開盤 2026-11-09T00:00:00Z / 2026-11-09T09:00:00+0900，該根收盤 2026-11-10T00:00:00Z / 2026-11-10T09:00:00+0900。抓取時尚未收盤、已排除：1 根。缺口數只描述這些已收盤 K 線之間的間隔，不能把未收盤的最後一根算進樣本，也不能把『缺口 0』說成含未完成 K 線的無前視覆蓋。
- 成交筆數：0（已平 0，未平 0）
- 期末權益：$10.0000；總報酬：0.00%；已實現 $0.0000；未實現 $0.0000
- 最大回撤（收盤市值，不是盤中）：0.00%
- 費用（GMGN＋池費，池費若為假設會另標）：$0.0000；鏈上費美元：$0.0000
- 勝率：未定義（沒有已平倉交易）；獲利因子：未定義
- 被擋下的指標訊號：3
- 現金基準：$10.0000
- 買入持有：狀態 skipped；期末 —；報酬 未定義；最大回撤 未定義。
- 這段沒有成交。報酬記 0，不是獲利。

### POPCAT / SOL · 附錄：同一規則的 POPCAT/SOL 池，沒有用來挑選主池 · exploratory_ohlcv_only

- 已收盤 K 線：183 根。時間戳是開盤，不是收盤。第一根開盤 2026-05-11T00:00:00Z / 2026-05-11T09:00:00+0900。最後一根開盤 2026-11-09T00:00:00Z / 2026-11-09T09:00:00+0900，該根收盤 2026-11-10T00:00:00Z / 2026-11-10T09:00:00+0900。抓取時尚未收盤、已排除：1 根。缺口數只描述這些已收盤 K 線之間的間隔，不能把未收盤的最後一根算進樣本，也不能把『缺口 0』說成含未完成 K 線的無前視覆蓋。
- 成交筆數：1（已平 1，未平 0）
- 期末權益：$8.2338；總報酬：-17.66%；已實現 $-1.7662；未實現 $0.0000
- 最大回撤（收盤市值，不是盤中）：17.66%
- 費用（GMGN＋池費，池費若為假設會另標）：$0.1252；鏈上費美元：$0.8590
- 勝率：0.00%；獲利因子：0.0
- 被擋下的指標訊號：2
- 現金基準：$10.0000
- 買入持有：狀態 marked_unrealized_at_end；期末 $7.4761；報酬 -25.24%；最大回撤 25.86%。買入後持有到最後收盤。期末是未實現市值，未扣賣出費用，不是成交。

## 費用敏感度（$WIF 日線，安全閘已放寬）

池費 null 的列維持 0 筆。其餘池費是假設。正負號會隨鏈上費假設改變；每一格最多一筆，不能當成穩定優勢。

| 鏈上 SOL／邊 | 池費／邊 | 成交 | 期末權益 | 總報酬 | 費用 | 鏈上費美元 | 被擋訊號 |
|---|---|---|---|---|---|---|---|
| 0.002 | 未知→不交易 | 0 | $10.0000 | 0.00% | $0.0000 | $0.0000 | 7 |
| 0.002 | 0.30% 假設 | 1 | $10.4050 | 4.05% | $0.1537 | $0.3436 | 6 |
| 0.002 | 1.00% 假設 | 1 | $10.3177 | 3.18% | $0.2349 | $0.3436 | 6 |
| 0.005 | 未知→不交易 | 0 | $10.0000 | 0.00% | $0.0000 | $0.0000 | 7 |
| 0.005 | 0.30% 假設 | 1 | $9.8548 | -1.45% | $0.1466 | $0.8590 | 6 |
| 0.005 | 1.00% 假設 | 1 | $9.7715 | -2.29% | $0.2240 | $0.8590 | 6 |
| 0.006 | 未知→不交易 | 0 | $10.0000 | 0.00% | $0.0000 | $0.0000 | 7 |
| 0.006 | 0.30% 假設 | 1 | $9.6713 | -3.29% | $0.1442 | $1.0308 | 6 |
| 0.006 | 1.00% 假設 | 1 | $9.5894 | -4.11% | $0.2203 | $1.0308 | 6 |

## Polymarket（分開的機率檢視，沒有損益回測）

- 問題：Xi Jinping out before 2027?
- condition `0xa467b14d51f01b957109d9cbb1d6c124fab2a089d52ed8f471d23c2812e743b7`
- Yes token `32338220190071351435772801779725302244575775216413325951443816017994629993401`
- 選擇方式：first closed=false Gamma market at fetch time; not a strategy universe
- 已結束的機率桶 911 點（原始回應 912 點，排除未完成或非桶報價 1 點）。價格區間 0.0165–0.335，最後已結束桶 0.0165，單位是 0–1 機率。
- `has_more=False`。抓取 2026-11-10T02:30:58Z / 2026-11-10T11:30:58+0900。
- `resolution_seconds` 為 0 的終端報價不是已收盤的 12 小時桶，圖上不畫。沒有替它發明收盤時刻。
- 沒有把這條機率和 $10 meme 帳戶合併，也沒有用代幣 RSI 規則去算預測市場損益。

## 公開池成交骨架

GeckoTerminal 公開池成交。不是錢包損益，沒有把轉帳當成買入，也沒有計算地址報酬。
檔內 300 筆，報告只列最近 8 筆的欄位，不計算地址損益。

## 仍未解決

- Stock App 產品身份未知。
- 池費未知；Pump.fun 與 Raydium 費率不能互相替代。GMGN 文件示例 Pump.fun 1%，Help Center 另有 1.25% 的說法，本池是 Raydium $WIF/SOL，兩種都沒有套用成已核費率。
- 沒有 point-in-time 宇宙，死掉的池不在搜尋結果裡。
- 官方 SOL 交易機器人名稱與部分教學不一致；本程式沒有、也不能控制那些機器人。
- 「永遠不要發二次財」沒有收成唯一解釋。`no_reentry` 只是暫定開關：第一筆出場後故意擋掉同一池之後所有新倉，含驗證段與留出段。它不是第一波偵測，也不是已驗證的樣本外策略。

