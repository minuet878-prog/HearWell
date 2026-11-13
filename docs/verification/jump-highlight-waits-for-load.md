# #531 帶錨點打開頁面時，亮框等頁面載完才開始等

日期：2026-11-13。規格：#531（#338 的「頁面停下才亮」）。基準：`origin/main` `b26142b`；分支：`claude/xenodochial-engelbart-88bd14`。

狀態：自動測試全部通過，等本人驗收。只改前端一支腳本，沒碰計分、門檻、migration、權限，不需要交叉審查。沒有操作真實資料。

## 根本原因

頁面帶 `#` 打開時，`jump-highlight.js` 一執行就開始等 150 ms。但瀏覽器什麼時候跳到錨點沒有保證：WHATWG HTML 規格「try to scroll to the fragment」寫明先等「由瀏覽器自訂的時間」，找不到目標就重試，到解析結束為止。機器慢時跳得比 150 ms 晚，方塊在頁面最上面已經算在畫面上，就先亮了，之後頁面才跳過去（CI 上 `JumpHighlightTest.test_route_and_its_stop_light` 偶發失敗的原因）。

## 修法（本人 2026-11-13 選定）

頁面帶 `#` 打開時，等 `load` 事件之後才開始原本的等待（150 ms 沒有捲動，或等 `scrollend`）。`load` 一定在解析結束之後，規格保證錨點捲動在這之前就試完了。

另外補一條：頁面還在載入時，使用者先點了頁內連結，就取消開頁那次的亮框，免得 `load` 時把使用者點的那一格搶走。

頁內連結的跳轉沒有改：程式只動了「頁面打開時」那一段。

代價：圖片很慢的網路，開頁的亮框會晚一點才亮（仍然是頁面停下、方塊在畫面上才亮）。

### 定修法前的試驗（暫存資料夾，不在 repo 裡）

Chromium 開一個帶 `#` 的測試頁，記錄腳本執行、`DOMContentLoaded`、`load` 和 `scroll` 時的捲動位置；六種組合（CPU 正常／降速 6 倍／20 倍、樣式表慢 300 ms、圖片慢 800 ms、全部疊加）：

- 腳本執行時頁面每次都還在 0：錨點捲動一定比腳本晚。
- 到 `load` 時捲動位置每次都已經到位；`scroll` 事件有時晚一個畫面才來，原本等 `scrollend` 的邏輯會處理。

## 測試結果

- `npm test --prefix frontend`：36 個檔、542 項通過。
- `npm run build --prefix frontend` 成功。
- `python manage.py test --settings=config.test_settings`：2180 項通過。
- 整套 e2e（`e2e.main_flow --parallel 4`）：420 項通過。
- 沒改 Python，不需要跑 Ruff。

### 試驗：用 issue 的方法重現 CI 失敗（已還原）

issue 裡把 `PAUSE` 改成 0 模擬「瀏覽器晚於等待時間才跳」，修之前 `JumpHighlightTest` 3/3 失敗。修之後同樣改成 0 再跑三次：3/3 通過（每次 5 項）。跑完已改回 150、重建前端，再跑一次 `JumpHighlightTest` 通過。

## 驗收對照（#531）

測試檔＝`frontend/src/jump-highlight.test.js`。

| # | 驗收條件 | 驗證 | 證據 |
|---|---|---|---|
| 1 | 有能重現的測試：瀏覽器晚於 150 ms 才跳時，等跳完、停下才亮（修之前會失敗） | ✅ 自動 | `waits for the page to load before waiting for the jump to the # to stop`：`load` 前過 1 秒不亮（`:198`），跳了還沒停不亮（`:202`），`scrollend` 才亮（`:204`）。修之前在 `:198` 失敗（150 ms 時已亮） |
| 2 | `JumpHighlightTest` 全部通過，`jump-highlight.test.js` 通過 | ✅ 自動 | e2e 整套 420 項通過（含 `JumpHighlightTest` 5 項）；vitest 21 項通過 |
| 3 | 頁內連結跳轉的行為不變 | ✅ 自動 | 頁內連結的 7 項舊測試一字未改、全部通過（`:107`–`:168`、`:221`–`:239`）；新增 `keeps to a jump made before the page has loaded`（`:215`）守住「載入中先點連結」不被開頁那次搶走 |

改了的舊測試：「頁面打開時亮 # 那一格」（`:183`）和「跳到別格時立刻熄掉前一格」（`:171`）兩項，開頁後補送 `load` 事件，斷言不變；後者多一行先確認開頁那格有亮（`:176`）。

## 本人實際操作

- [ ] 從「選配指引」任一章節點「回選配路線看下一站」，頁面跳到路線後才亮框，不會在頁面最上面先亮
