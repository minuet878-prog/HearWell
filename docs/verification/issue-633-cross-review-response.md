# #633 交叉審查的處理（給 Codex 複核）

審查：Codex，2026-11-17，對 `89378df4`。處理的 commit：`69cd5de6`（程式修正）、`4ed6ce19`（補證據的測試），同分支 `feat/633-about-feedback`。
本人 2026-11-17 決定：P1 接受、P2 分享頁不帶回原頁、P4 加一句、P6 接受。
請**只複核下面標「已修」「已補」的項目**，看有沒有修對、測試有沒有真的驗到。

## Standards

| # | 處理 | 證據 |
|---|---|---|
| S1 後台先刪後查權限 | 已修。兩個後台（意見回饋、提問紀錄）都改成有檢視或修改權限才清除：同一個原因，一起修 | `screening/admin.py`（兩個 `changelist_view`）；`screening/tests/test_feedback_admin.py:187`、`screening/tests/test_qa_purge.py:143`（沒權限的 staff 得 403、舊資料還在、月統計沒加） |
| S2 驗收測試缺口 | 見下方 Spec 表 | |
| S3 Sentry 事件 | 已補測試。遮罩本來就有（`config/monitoring.py`：去掉例外訊息、表單內容、查詢字串、標頭） | `screening/tests/test_monitoring.py:221`：真的走 WSGI 送出一則、寄信失敗，事件只有固定訊息，沒有回饋內容、email、來源、回原頁路徑 |
| S4 聯絡信箱寫在模板 | 不改：全站模板都直接寫這個信箱（忘記密碼頁、頁尾），一起改才一致，不在這張規格 | |

## Spec 實作發現

| # | 處理 | 證據 |
|---|---|---|
| P1 並行超額 | 本人接受，寫進 ADR 0064「代價」（跟忘記密碼的限制一樣「大致準」） | `docs/adr/0064-feedback-stored-anonymous-90-days.md` |
| P2 分享代碼進網址 | 已修。分享報告兩頁的頁尾連結不帶回原頁，已送出頁改「回到首頁」 | `screening/context_processors.py` 的 `NO_WAY_BACK`；`screening/tests/test_feedback.py:126`（比對到結尾引號，且頁尾沒有代碼）、`:590`（從分享報告頁尾實走，存下的資料沒有代碼） |
| P3 午夜交界 | 已修。通知信用這則回饋自己的送出日期 | `screening/views/feedback.py` 的 `notify_owner(request, feedback)`；`screening/tests/test_feedback.py:357` |
| P4 隱私權說明漏寫次數 | 已修。加「同一個網路每小時最多送 5 次」，只更新日期、不升版 | `screening/templates/screening/privacy.html`；`screening/tests/test_feedback.py:443` 跟程式的 `FEEDBACKS_PER_ADDRESS` 比對 |
| P5 隱藏欄在上限後 | 已修。隱藏欄改成最先判斷 | `screening/tests/test_feedback.py:255` |
| P6 頁尾格寬 | 本人接受（只有 320px 差幾個像素，字不斷開） | |

## 驗收證據缺口

| 條件 | 處理 | 證據 |
|---|---|---|
| 2 | 不補：比對的是兩頁同一個模板輸出的 HTML 完全相等，「先看重點」本身的條數由同意書的測試管 | |
| 4 | 已補：查核日期在最後一段之後、頁面最後 | `screening/tests/test_about.py:44` |
| 7 | 已有，不在 diff 裡：通用測試逐一跑公開頁面清單（含 `/about`） | `screening/tests/test_standards.py:550,566,575`；`screening/tests/test_sitemap.py:24`；`screening/tests/test_line_preview.py:35` |
| 8 | 已有：sitemap 跟公開頁面清單完全相等，兩頁不在清單 | `screening/tests/test_sitemap.py:24`；`screening/tests/test_feedback.py:181`（禁止收錄） |
| 9 | 已補：恰好一個文字框、一個 email（沒有 required）、一顆送出 | `screening/tests/test_feedback.py:608` |
| 12 | 已補：email 欄 `value=""` | `:617` |
| 14 | 已補：打勾 | `:622` |
| 16 | 已補：空字串 | `:626` |
| 19 | 已補：`javascript:`、反斜線、`http:///`、`https:` 開頭；送出時帶站外 next 也被丟掉 | `:631`、`:645` |
| 22 | 已補：登入送出時，存下的就是文字、email、種類、未處理，沒有路徑 | `:651` |
| 23 | 已補：從結果頁、聽力圖頁、分享報告頁的頁尾實走一次，存下的資料沒有編號、代碼、路徑 | `:578`、`:584`、`:590` |
| 24 | 已補：從問答題目頁的頁尾實走一次 | `:595` |
| 25 | 已補：在刪除帳號頁刪除，帳號沒了、回饋還在 | `:668` |
| 29 | 已補（同 P5） | `:255` |
| 31 | 已補：真的瀏覽器裡隱藏欄看不到、Tab 從文字框到 email 到送出，無障礙樹沒有它 | `e2e/main_flow.py:16657` |
| 34 | 不補：真的同時送兩個要開多執行緒，成本高；唯一鍵已有測試，邏輯只有「建得起來的那一次才寄」 | |
| 35 | 已補（同 S3） | `screening/tests/test_monitoring.py:221` |
| 37 | 已補：每列的送出時間（台灣時間）與已處理圖示 | `screening/tests/test_feedback_admin.py:203` |
| 39 | 已補：偽造時間送出，時間不變 | `:217` |
| 40 | 已補：一次勾兩則刪除，歷史紀錄兩筆、沒有文字和 email | `:226` |
| 41 | 已補：用管理指令跑剛好 90 天與多 1 秒 | `:246` |
| 44 | 已補：刪除的方法寫到收件信箱；日期「上線那天」由上線時對一次（#643） | `screening/tests/test_feedback.py:430` |
| 45 | 已補（同 P4） | `:443` |
| 48 | 不補：開工時序是流程，#635 結案後 #642 才開工，見 issue 時間 | |
| 49 | 部分：頁尾等寬本人接受（P6）；其餘排法是設計圖選項，本人驗收時看 | |
