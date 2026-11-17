# #633 關於聽伴、意見回饋

日期：2026-11-17。分支：`feat/633-about-feedback`，PR [#688](https://github.com/minuet878-prog/HearWell/pull/688)。規格 [#633](https://github.com/minuet878-prog/HearWell/issues/633)，票 #634（設計圖）、#635（本人寫字）、#636–#642（實作）、#643（本人上線後在正式站做）。

狀態：2026-11-17 本人在本機實際操作後回覆「看過了，沒問題」，**驗收通過**（含「不一樣的地方」第 1 條代理擬的頁面名稱）。自動測試全過。2026-11-17 上線，#643 本人在正式站驗收 43、50、51 通過（見最後一段）。

- 本人在設計圖選定（2026-11-16，#634）：頁尾 A（兩排圖示）、回饋頁 A（先提醒再寫）、已送出頁 A、關於頁 A（四段攤開）、「了解」頁 A（接在最後一張）。
- 本人寫的字（2026-11-16，#635）：一題一題選定，原文在 [#635 的留言](https://github.com/minuet878-prog/HearWell/issues/635#issuecomment-6920791719)。
- 隱私權說明「意見回饋」一段：代理擬稿、本人照擬稿核准（#641），交叉審查後本人同意加「同一個網路每小時最多送 5 次」。同意書維持第 8 版（ADR 0064）。
- 第 4 步自審（`/mattpocock-skills:code-review`，基準 `origin/main`）：Standards 1 項硬性（後台查詢次數測試）、Spec 1 項錯（建議表 A5 少一個分隔符號，比對測試略過關於頁）與 4 個測試缺口，都修了；判斷題本人選不動。
- 交叉審查（Codex，2026-11-17）：[審查摘要](issue-633-cross-review.md)、[逐項處理](issue-633-cross-review-response.md)、[#633 留言](https://github.com/minuet878-prog/HearWell/issues/633#issuecomment-6922364413)。要修的都修了並補測試；**Codex 的複核本人決定跳過**（2026-11-17）。
- 沒有操作真實資料。測試都在臨時測試資料庫上。

## 行為

| 項目 | 現在 |
|---|---|
| 頁尾 | 家人專區、關於聽伴、意見回饋、隱私權說明、帳號設定（登入時）；手機上每排最多三格，字放大時自動換行；電腦上一排 |
| 意見回饋頁 `/feedback` | 不用登入、未同意新版同意書也能用。「您是從〈某頁〉過來的」→ 本人的提醒 → 急症紅框（沿用問答小助手）→ 文字框（1,000 字）→ 選填 email → 送出 |
| 存什麼 | 內容、選填 email、頁面種類的中文名（例如「結果頁」）、送出時間、已處理。不存帳號、IP、session、網址 |
| 擋灌單 | 隱藏欄（填了就假裝成功、不存）；同一來源每小時 5 次（填錯不算）；全站每天（台灣時間）100 則；被擋時字留在框裡 |
| 已送出頁 | ✓ 已送出，謝謝您＋本人那一句＋「回到剛才那一頁」（不知道原頁或從分享報告來時是「回到首頁」） |
| 回饋通知信 | 那一天（台灣時間，用回饋自己的送出時間）第一則送出時寄一封到專案信箱，只有後台連結和「今天之後的回饋不會再寄信通知」；寄不出去送 Sentry，回饋照樣存 |
| 後台 | 新到舊、可篩已處理、可搜 email、只有「已處理」可改、不能新增、可刪單筆與多筆；打開清單時（有權限才）先清掉超過 90 天的 |
| 90 天清除 | `purge_feedback` 指令；VPS 02:30 排程要本人加一行（[清單](../deployment/feedback-purge.md)，#643） |
| 關於聽伴 `/about` | 公開頁面（進 sitemap、有 LINE 預覽）。誰做的、內容怎麼查核、資料怎麼處理（同意書「先看重點」＋連到隱私權說明）、不能取代檢查；最下面「本頁資料查核於 2026/11/16」，列進每年查核 |
| 「了解」頁 | 最後一張「關於聽伴／誰做的、內容怎麼查核」 |
| 隱私權說明 | 多「意見回饋」一段、「為什麼蒐集」「保存多久」各一項、備份那一行加意見回饋；日期 2026/11/16，同意書第 8 版 |

跟規格或設計圖不一樣、或規格沒寫到的地方（請本人驗收時一起看）：

1. **「您是從〈某頁〉過來的」的頁面名稱是代理擬的**（例如「結果頁」「家人看的聽力報告」「聽力圖的語言香蕉區」「選配指引：〈章名〉」「問答小助手：〈題目〉」），沒有逐一給本人看過。名稱表在 `screening/views/feedback.py` 的 `PAGE_NAMES`。
2. **頁尾在 320px 手機上「隱私權說明」那格比同排寬約 10px**（設計圖是一樣寬）。本人 2026-11-17 接受（交叉審查 P6）。
3. **從分享報告頁來的不帶回原頁**：避免分享代碼進到回饋頁的網址（交叉審查 P2，本人選定）。家人要用瀏覽器的上一頁回報告。
4. **每小時 5 次、每天 100 則是「大致準」**：同一瞬間送出的幾則可能多存（交叉審查 P1，本人接受，寫進 ADR 0064）。
5. **填錯被退回的不算次數**：規格只寫「每小時 5 次」，代理定成只算真的存下的和隱藏欄的。
6. **已送出頁用訪客保存結果的深綠底白字框**：設計圖畫的是淺綠，代理沿用現有元件、不新增。
7. **提問紀錄後台也一起修了權限順序**：跟意見回饋後台同一個原因（交叉審查 S1），沒有權限的人打開清單不會再觸發清除。
8. **隱私權說明日期**：寫 2026/11/16，上線那天要對成上線日。
9. **截圖腳本 `e2e/screenshots.py`** 多拍回饋頁和已送出頁（規格沒要求，方便以後比對）。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。「頁面」＝`screening/tests/`，「端對端」＝`e2e/main_flow.py`。

| # | 驗收條件（簡寫） | 驗證 | 證據 |
|---|---|---|---|
| 1 | 關於頁不用登入、四段各有標題 | ✅ 自動 | 頁面 `test_about.py`（`AboutPageTests`） |
| 2 | 資料那段是「先看重點」並連到隱私權說明 | ✅ 自動 | 頁面 `test_about.py` |
| 3 | 誰做的只寫執業聽力師、沒有姓名單位 | ✅ 自動 | 頁面 `test_about.py`（`AboutWordsTests`） |
| 4 | 查核日期在最下面、列進每年查核 | ✅ 自動＋文件 | 頁面 `test_about.py`；`docs/roadmap.md` 每年查核清單 |
| 5 | 每頁頁尾有兩個連結 | ✅ 自動 | 頁面 `test_layout.py`（`FooterOneRowTests`）、`test_feedback.py` |
| 6 | 「了解」頁最後一張卡 | ✅ 自動 | 頁面 `test_learn.py`；端對端 `test_learn_cards_are_list_rows` |
| 7 | 關於頁是公開頁面：標題描述是本人確認的字、sitemap、可收錄、LINE 預覽 | ✅ 自動 | 頁面 `test_search_titles.py`（23 列）、`test_public_pages.py`、`test_sitemap.py`、`test_standards.py`、`test_line_preview.py` |
| 8 | 回饋頁與已送出頁不公開、不在 sitemap、禁止收錄 | ✅ 自動 | 頁面 `test_public_pages.py`、`test_sitemap.py`、`test_feedback.py` |
| 9–13 | 表單欄位、從哪一頁來、提醒與急症、登入時 email 空白、未同意也能送 | ✅ 自動 | 頁面 `test_feedback.py`（`SendFeedbackTests`、`FormDetailsTests`、`OwnersWordsTests`） |
| 14–19 | 送出、存 email、空白、太長、email 錯、回原頁不會到站外 | ✅ 自動 | 頁面 `test_feedback.py` |
| 20–21 | 關掉 JavaScript 能送；200% 字級不左右捲 | ✅ 自動 | 端對端 `FeedbackTest` |
| 22–25 | 不存帳號 IP 網址、只存頁面種類、從真的頁尾走一次、不進下載、刪帳號不影響 | ✅ 自動 | 頁面 `test_feedback.py`（含 `FromARealFooterTests`） |
| 26–31 | 每小時 5 次、認最後一個轉送位址、計數不存 IP、隱藏欄、每天 100 則、隱藏欄看不到也 Tab 不到 | ✅ 自動 | 頁面 `test_feedback.py`（`FeedbackLimitTests`）；端對端 `FeedbackTest` |
| 32–36 | 通知信一天一封、只有後台連結、寄失敗照樣存並送 Sentry（不含內容）、被擋的不寄 | ✅ 自動 | 頁面 `test_feedback.py`（`FeedbackNoticeTests`）、`test_monitoring.py` |
| 37–40 | 後台清單、篩選搜尋、只有已處理可改、刪除與歷史紀錄 | ✅ 自動 | 頁面 `test_feedback_admin.py` |
| 41–42 | 90 天清除（指令與打開清單） | ✅ 自動 | 頁面 `test_feedback_admin.py` |
| 43 | VPS 02:30 排程加清除 | ✅ 本人 | 2026-11-17 加進 `hearwell-purge-question-log.service`，手動跑一次兩行都有（見最後一段） |
| 44–47 | 隱私權說明的段落、天數與次數跟程式一致、忘記密碼那段仍正確、同意書第 8 版 | ✅ 自動 | 頁面 `test_feedback.py`（`FeedbackPrivacyTests`）、`test_consent.py`、`test_family_zone.py` |
| 48 | 用本人的原文 | ✅ 自動 | 頁面 `test_feedback.py`（`OwnersWordsTests`）、`test_about.py`（`AboutWordsTests`） |
| 49 | 照設計圖選定的排法 | ✅ 本人 | 2026-11-17 本機操作，下面的清單 |
| 50–51 | 正式站收得到通知信、連送 6 次被擋 | ✅ 本人 | 2026-11-17（見最後一段） |

## 本人實際操作驗收（本機）

在終端機開 worktree 的網站（會用您本機的資料庫；送出的回饋會存進本機資料庫，通知信在終端機印出、不會真的寄）：

```bash
cd /Users/huangweizhe/HearWell/.claude/worktrees/about-feedback-grill && /Users/huangweizhe/HearWell/py313/bin/python manage.py migrate && /Users/huangweizhe/HearWell/py313/bin/python manage.py runserver 8001
```

打開 http://localhost:8001 ，手機寬度或字放大 200% 也看一次：

- [x] 任一頁的頁尾：兩排圖示（家人專區、關於聽伴、意見回饋／隱私權說明、帳號設定）
- [x] 關於聽伴：四段的字、「先看重點」、最下面的查核日期
- [x] 「了解」頁：最後一張「關於聽伴」
- [x] 從某一頁的頁尾按「意見回饋」：「您是從〈那一頁〉過來的」、提醒、急症紅框、文字框、email
- [x] 送出後：✓ 已送出、那一句話、「回到剛才那一頁」回得去
- [x] 什麼都不寫按送出：提醒要先寫
- [x] 終端機印出一封回饋通知信（只有後台連結）；同一天再送一則不再印
- [x] 後台 `/admin/` →「意見回饋」：看得到剛才那幾則，可以勾已處理
- [x] 隱私權說明「意見回饋」那一段
- [x] 上面「不一樣的地方」第 1 條的頁面名稱

## 測試結果

| 項目 | 結果 |
|---|---|
| 單元測試（本機，合併 `origin/main` 後） | 2,864 條全過 |
| e2e（本機，合併前） | 482 條全過 |
| e2e（本機，合併後） | 電腦負載 40 多，28 條逾時；逐條單獨重跑全過 |
| CI（`2f3b8730`） | backend、frontend、e2e 全過 |
| Ruff check／format | 全過 |

## 上線（#643，2026-11-17）

照 VPS 筆記「更新程式碼到最新 main」那張表，代理一步一步帶本人做：

| 步驟 | 結果 |
|---|---|
| 隱私權說明日期 | 先開小 PR #692 改成 2026/11/17（上線日），CI 全綠後本人合併 |
| VPS 現況 | `working tree clean`，停在 `4d2c3b86`（#628）；`git fetch` 後要帶上 93 個 commit 到 `6ba1a8dc` |
| 預覽變動 | migration 只多 `0037_feedback`、`0038_feedbacknotice`；`requirements.txt` 沒變；`settings.py` 多 1 行 |
| 備份 | `~/backups/hearwell-before-0037.dump`（約 100 KB，權限 600） |
| 拉程式、安全檢查 | `git pull`；`check --deploy` no issues（1 silenced） |
| 前端、靜態檔 | build 2.8 秒；collectstatic 871 copied、177 unmodified |
| migration | `--plan` 只列兩條建表；`migrate` 兩個 OK；快取表已存在 |
| 清除與問卷 | 提問紀錄、意見回饋各清 0 筆；問卷照舊 |
| 重啟 | 等 `main`（`6ba1a8dc`）CI 全綠才重啟；`active (running) … 35ms ago` |
| 從外面檢查（代理） | `/uptime-check`、`/about`、`/feedback`、`/feedback/sent`、`/privacy`、`/sitemap.xml` 都 200；關於頁可收錄、兩個回饋頁禁止收錄；隱私權說明「第 8 版，2026/11/17 更新」並有每小時 5 次；sitemap 有 `/about`；首頁頁尾有兩個新連結 |
| 02:30 排程（驗收 43） | `hearwell-purge-question-log.service` 多一行 `purge_feedback`；手動跑一次：01:19:39 清提問紀錄、01:19:40 清意見回饋 |
| 正式站送出（驗收 50、51） | 本人沒登入從頁尾送一則：收到回饋通知信；同一個網路連送，第 6 次被擋；後台看得到 5 則 |

還沒做：

- VPS 上的手動備份 `~/backups/hearwell-before-0037.dump` 等確認沒問題後由本人刪（檔名不符合自動刪除規則）。
- VPS 顯示 `System restart required`，這次沒處理，另找時間照筆記「系統更新與重開機」做。

