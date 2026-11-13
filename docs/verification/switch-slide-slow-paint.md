# 「問卷｜聽力圖」藍色藥丸在手機上常常沒滑（無 issue）

日期：2026-11-13。基準：`2a6632a`（origin/main，#501 合併後）；分支：`fix/switch-slide-slow-paint`；commit：`c3d3e74`（重現測試）、`458dc73`（修正）、`ef58e84`（自審修正）、`bf825df`（印出被略過的原因）、改成等藍色藥丸（本次）。

狀態：本機自動測試與自審（Standards／Spec）已通過；改成等藍色藥丸後等 CI 結果，再等本人操作驗收。沒碰計分、分級、門檻、資料 migration、權限，**不需交叉審查**。未操作真實資料，沒有啟動開發伺服器；重現和測試都在 e2e 的臨時測試資料庫上跑。不需 migration。

## 問題與根本原因

本人回報：「我的紀錄」上方「問卷｜聽力圖」的藍色藥丸動畫有時候出不來，閃一下就切過去了。

原因：藥丸滑動靠的是瀏覽器的「換頁過場」，新舊兩頁都要有藍色藥丸才能滑。手機比較慢時，瀏覽器只解析了新頁開頭一小段（約 22 個元素，還沒到切換鈕），就先畫出第一個畫面。這時 `switch-reveal.js`（#334）照設計取消轉場，直接換頁，避免只剩舊藥丸淡出的半套動畫。聽力圖比較頁的「右耳｜左耳」也是同一個原因。

重現（手機大小 390×844，來回切換 30 次，記錄新頁畫第一個畫面時有沒有切換鈕）：

| 情境 | 有滑 | 被略過 |
|---|---|---|
| 不降速 | 30 | 0 |
| CPU 慢 4 倍 | 8 | 22 |
| CPU 慢 4 倍＋修正 | 30 | 0 |

## 做法

- 三個頁面（`/my_hearing`、`/audiograms`、`/audiograms/compare`）的 `<head>` 加上 `<link rel="expect" href="#…-current" blocking="render">`，只有目前那一側的藍色藥丸連結有這個 `id`（`records-switch-current`、`ear-switch-current`）：瀏覽器要等藥丸解析好才畫第一個畫面。藥丸在頁面開頭，延後的時間很短（CPU 慢 4 倍時，新頁最晚 0.38 秒畫出）。
- 第一版指向整個切換鈕 `<nav>`，CI 上失敗兩次（「問卷｜聽力圖」一次、「右耳｜左耳」一次）。把被略過的原因印出來後看到 `{'error': 'AbortError', 'pill': False, 'parsed': 132, 'ms': 1709}`：比較頁的 `<nav>` 正好是第 132 個元素、藥丸是第 133 個，Chrome 讀到 `<nav>` 的開頭就放行畫面，藥丸還沒讀到，`switch-reveal.js` 於是取消轉場。規格寫的是等元素「完整讀完」，但 CI 上的 Chromium 沒有等到；本機 Mac 讀得快，一直重現不了（CPU 慢 20 倍、伺服器延遲 5 秒都試過）。改成等藥丸本身（本人選做法 A），和 `switch-reveal.js` 檢查的條件一致：就算一樣讀到開頭就放行，藥丸也已經在了。
- 支援範圍：Chrome、Edge 124 起。Safari、Firefox 目前查到不支援（[web-features](https://web-platform-dx.github.io/web-features-explorer/features/link-rel-expect)），會忽略這一行，照舊由 `switch-reveal.js` 直接換頁。
- 比較頁只有一張聽力圖或兩張選同一張時沒有切換鈕，這時會等到整頁解析完才畫；頁面很短，影響可忽略。
- `docs/verification/issue-326.md:32` 記錄當初「實測 Chromium 156 不生效」。這次用同版 Chromium（156.0.8078.4）實測有效，當時為什麼不生效已查不到。ADR 0028 補了一行。

## 驗收對照

勾選代表自動驗證或本次對話的檢查，不代替本人操作確認。

| 需求 | 驗證 | 證據 |
|---|---|---|
| 慢的手機上，問卷｜聽力圖的藥丸每次都滑 | ✅ 自動 | `e2e/main_flow.py:2914`（CPU 慢 6 倍、來回 6 次，斷言在 `:2902`，失敗時印出被略過的原因）；修正前失敗：`'skipped' != 'transition'` |
| 慢的手機上，右耳｜左耳的藥丸每次都滑 | ✅ 自動 | 同上，`選耳朵` subTest；修正前同樣失敗 |
| 不支援 render-blocking 的瀏覽器：慢的時候直接換頁，不出現半套動畫 | ✅ 自動 | `e2e/main_flow.py:2932`（拿掉那一行後，每次不是完整滑動就是直接換頁，且至少一次直接換頁）；暫時讓 `switch-reveal.js` 失效時，這項抓到「只剩舊藥丸淡出」而失敗 |
| 頁面真的有那一行，而且指到目前那一側的藥丸 | ✅ 自動 | `screening/tests/test_records_switch.py:81`（另見 `_switch`：`id` 只在 `aria-current` 那個連結）；`screening/tests/test_audiogram.py:1374` |
| CI（Linux）上慢的時候也每次都滑 | ⬜ CI | 第一版失敗兩次；改成等藥丸後要看 CI 是否穩定通過 |
| 一般速度也滑；減少動態效果不轉場；不支援轉場照常換頁；其他換頁不轉場 | ✅ 自動 | `e2e/main_flow.py:2953`、`:2963`、`:2973`、`:2985`、`:3037`（後兩項以前容許略過，現在要求一定滑） |
| 本人在手機上切換幾次，藥丸都有滑 | ⬜ 本人 | 合併部署後在手機上操作 |

## 測試結果

- 單元測試：`Ran 2094 tests … OK`
- 前端：`Test Files 34 passed`、`Tests 482 passed`
- e2e 整套（`--parallel 4`，自審修正前）：`Ran 412 tests … OK`；自審修正後 `SlidingPillTest` 連跑三輪，每輪 `Ran 8 tests … OK`
- Ruff：`ruff check`、`ruff format --check` 都通過
- 改成等藍色藥丸後（本機）：單元測試 `Ran 2094 tests … OK`；`SlidingPillTest` 連跑兩輪，每輪 `Ran 8 tests … OK`；CI 結果待補

## 自審

- Standards：沒有硬性違規。已改：測試註解的 4 倍／6 倍講清楚、ADR 精簡。沒改：建議把三頁 `<head>` 的兩行抽成共用 include，會連帶搬動原本就有的 `switch-reveal.js` 那行，超出這次範圍；id 對不上時，單元測試和 e2e 都會抓到。
- Spec：已補「不支援 render-blocking 時」的瀏覽器測試，以及 `#records-switch` 的 id 檢查。
