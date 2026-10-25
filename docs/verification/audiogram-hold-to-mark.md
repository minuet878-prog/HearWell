# 聽力圖：手指按住 0.3 秒才標記（#353）

日期：2026-10-25。基準：`9063200`（origin/main）；分支：`fix/audiogram-hold-to-mark`。規格：[#353](https://github.com/minuet878-prog/HearWell/issues/353)。

狀態：自動測試全過，**等本人 iPhone 實機驗收**。只改標記聽力圖的觸控操作與說明文字；沒碰計分、分級、門檻、migration、權限，所以不需要交叉審查。沒有操作真實資料。

## 原因

可標記的圖設了 `touch-action: none`，手指一碰就開始標、放開就存點；手機上圖超過半個螢幕，往下滑時很容易碰到，結果是誤標（或在已有的點上誤刪），頁面也滑不動。跟是不是 PWA 無關，瀏覽器版一樣。

## 行為

- 手指：碰到圖後要不動（容許 10 px 晃動）0.3 秒才開始標，出現放大鏡；之後上下拖不會捲動頁面，放開就標好。
- 0.3 秒內移動超過 10 px、提早放開、瀏覽器接手捲動、或第二根手指放上來（縮放）：都不標、不刪。
- 刪除：在點上按住 0.3 秒後原地放開。
- 滑鼠（和觸控筆）：照舊，按下就開始。
- 圖改成 `touch-action: manipulation`：可以捲動、雙指縮放，不做連點兩下放大（原本 `none` 連這些都擋）。
- 說明文字：「在圖上按住不動一下，等數值出現，再上下拖到報告上的位置」「放開就標好了；標錯就在那個點上按住一下再放開，可以刪除」；圖的讀螢幕名稱也跟著改。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。jsdom 不會真的捲動，「頁面捲動」以 touchmove 有沒有被擋（`preventDefault`）代表。

| 驗收條件 | 驗證 | 證據 |
|---|---|---|
| 1 直接滑動：頁面捲動，不新增、不刪除、沒有放大鏡 | ✅ 自動 | `frontend/src/AudiogramApp.test.jsx:245`、`:249`、`:250`、`:252`；從已有的點上滑也不刪 `:260` |
| 2 按住 0.3 秒：出現放大鏡，拖曳不捲動，放開處標點 | ✅ 自動 | `frontend/src/AudiogramApp.test.jsx:289`、`:291`、`:292`、`:295` |
| 3 快速點一下：不新增、不刪除 | ✅ 自動 | `frontend/src/AudiogramApp.test.jsx:306`、`:313` |
| 4 在點上按住後原地放開：刪除 | ✅ 自動 | `frontend/src/AudiogramApp.test.jsx:322` |
| 5 滑鼠照舊立刻標 | ✅ 自動（既有，測試輔助函式改標明 `pointerType: "mouse"`） | `frontend/src/AudiogramApp.test.jsx:81`、`:85` |
| 6 說明文字更新 | ✅ 自動 | `frontend/src/AudiogramApp.test.jsx:426` |
| 7 唯讀聽力圖不變 | ✅ 自動（既有） | `frontend/src/AudiogramChart.test.jsx:20` |
| 瀏覽器接手捲動、第二根手指：不標 | ✅ 自動（新增） | `frontend/src/AudiogramApp.test.jsx:268`、`:276`–`:279` |
| iPhone 上真的能捲、按住後真的不捲、不跳出系統放大鏡或選單 | ⚠️ 要人工 | 請本人實機操作 |

## 測試與審查

- 前端 `npm test --prefix frontend`：355 項全過（新增 6 項）。
- 單元測試 `manage.py test --settings=config.test_settings`：1389 項全過。
- 端對端（先 `npm run build --prefix frontend`）`e2e.main_flow --parallel 4`：236 項全過。
- 先寫測試看它失敗（直接標點、說明文字舊的），再修。自審時多寫一個「第二根手指」的測試，重現了計時器遺留造成的 `TypeError`，已修。
- 自審（`/mattpocock-skills:code-review`，基準 `origin/main`，規格 #353）：
  - **Standards**：沒有硬違規。採納：`start` 改名 `startDrag`、清理函式改用 `stopHolding()`、註明 `marking` 用布林值的原因、在測試標明它也證明舊規格 acceptance 11。不採納：座標物件重複兩次（很輕，抽函式反而多一層）；第二根手指與 pointercancel 的處理（開放捲動與縮放後真的會發生，是正確性需要）。
  - **Spec**：補上條件 1「不刪除」的測試。多做的：第二根手指取消（正確性需要）、觸控筆跟滑鼠一樣（規格只講滑鼠，手機使用者用不到）、`manipulation` 關掉圖上的連點放大（原本 `none` 也關）。

## 人工驗收

（待本人 iPhone 實機操作後填寫）

1. 在耳朵步驟，手指從圖上開始往下滑：頁面會捲，沒有標點。
2. 手指在圖上按住不動一下：出現數值；接著上下拖，頁面不動；放開就標好。
3. 快速點一下圖：什麼都沒發生。
4. 在已標的點上按住一下再放開：點被刪掉。
5. 按住時沒有跳出 iOS 的放大鏡、文字選取或選單。
6. 說明文字讀起來清楚。
