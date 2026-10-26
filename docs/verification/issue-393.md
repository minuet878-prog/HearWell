# 跨檔共用的 view 函式改公開名字、找送出代號改成 model 查詢（#393）

日期：2026-10-26。基準：`dc158a5`（origin/main）；分支：`refactor/393-shared-helpers`。規格：[#393](https://github.com/minuet878-prog/HearWell/issues/393)（#380 拆檔的後續票）。

狀態：自動測試全過；自審要修 0 項；交叉審查（Codex）要修 0 項，摘要已留言到 #393。**等本人實際操作驗收。** 沒有 migration，沒有操作真實資料。動到「只查自己的資料」的查詢，依 AGENTS.md 屬權限，已做交叉審查。

## 本人決定（2026-10-26）

1. 跨檔共用的底線函式留在原檔、去掉底線（不搬到 `common`）。
2. `_find_by_key` 改成 `Submission` 的查詢方法，網頁與 API 都從 model 層拿；「只查自己的」由 `user.submissions` 保證，不在方法裡另外帶 user（自審提出，本人決定維持）。
3. `has_subscores` 搬到結果頁，切斷「結果頁 ← 匯出 ← 指引 ← 作答」這條依賴。
4. 測試切入點：用現有測試，不新增；交叉審查後補 API 並發測試的呼叫次數斷言。

## 做了什麼

- 去掉底線：`continue_notice`、`wearing_follow_ups`（answering）；`score_bar`、`score_gauge`、`ioi_ha_summary`（results）；`safe_next`（common）；`shows_wearing_comparison`（my_hearing）；`audiogram_context`（audiograms）。
- `has_subscores` 從 export 搬到 results；export 改從 results 匯入，原本同名的區域變數改叫 `subscored`，免得蓋掉函式。
- `SubmissionQuerySet.find_by_key(key)` 取代 API 的 `_find_by_key(user, key)`；四個呼叫點都寫 `request.user.submissions.find_by_key(key)`。
- 兩個並發測試的 mock 改指 `SubmissionQuerySet.find_by_key`（`autospec=True`），API 那個補上「查兩次」斷言。
- `AGENTS.md` 結構段的 `_safe_next` 改成 `safe_next`；`ioi_ha_summary.html` 註解跟著改名。

Commits：`3bbb6d2` 主要改動、`0b9107b` 自審（results 的 import 寫法統一）、`3ae129b` 交叉審查（補斷言）。

## 驗收對照

| 驗收 | 驗證 | 證據 |
|---|---|---|
| 9 處跨檔借用都處理，函式本體不變 | ✅ 一次性比對 | 用 `ast` 比對拆前（origin/main）與現在的函式本體，新舊名字視為同一個：9 個全部相同；`screening` 裡已沒有從 views／api 匯入底線名字的地方 |
| 結果頁不再依賴匯出 | ✅ 一次性比對 | `views/results.py` 只匯入 `views.common`、`views.my_hearing`；my_hearing 只匯入 common |
| 網頁作答只查本人的送出代號 | ✅ 自動（既有） | `test_answering.py` 的 `test_same_key_for_two_users`（:651–653） |
| API 送出只查本人的送出代號 | ✅ 自動（既有） | `test_api.py` 的 `test_key_is_scoped_to_user`（:587–590） |
| 兩下同時送出，網頁只存一筆、第二下走到重查 | ✅ 自動（既有，mock 改指） | `test_answering.py` 的 `test_simultaneous_clicks_save_once`（:735 查兩次、:736、:737） |
| 同上，API | ✅ 自動（補斷言） | `test_api.py` 的 `test_concurrent_same_key_returns_first_not_500`：新增 `find.call_count == 2`。試驗：把 mock 指到沒用到的方法時，這行失敗（`0 != 2`），試完已還原 |

決定 1、3 是程式結構要求，依決定 4 不加永久測試，以上表的一次性比對為證據（交叉審查也獨立比對過）。

## 測試與審查

- 單元測試 `manage.py test --settings=config.test_settings --parallel 4`：1449 項全過（`0b9107b`）；補斷言後 `test_api` 47 項全過。
- 端對端 `e2e.main_flow --parallel 4`：276 項全過（先建置前端）。
- `ruff check .`、`ruff format --check`：通過。
- 自審（Standards／Spec）：要修 0 項。採納：results 的 import 寫法統一。不採納：`find_by_key` 改成必須傳 user（本人決定維持由 `user.submissions` 限定）、`has_subscores` 改放 model（本人已決定放結果頁）。
- 交叉審查（Codex，HEAD `0b9107b`）：要修 0 項。四個呼叫點都限定 `request.user`，沒有名稱衝突或循環 import。證據缺口：結構要求沒有測試斷言（依決定 4 用比對）；API 並發測試沒斷言呼叫次數（已補）。

## 人工驗收

這次畫面沒有改，請用預覽網站走一輪受影響的頁面：

1. 首頁：上次結果的半圓儀表、「接著答」提示正常。
2. 作答一份 HHIE-S 或 HHIA-S：送出後到結果頁，看得到情緒／社交分項；按瀏覽器上一頁再送一次，仍只有一筆。
3. 我的紀錄：配戴前後比較的提示正常。
4. 聽力報告：IOI-HA 摘要和聽力圖正常。
5. 帳號設定 → 下載我的資料：檔案打得開，HHIE-S／HHIA-S 有分項分數。
6. 選配指引「配戴之後」那一章：建議再做的問卷正常。

回覆：（待填）
