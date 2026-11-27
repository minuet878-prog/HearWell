# 2026-11-27 走查文字精簡驗證（PR #790）

2026/11/27。本人用 dev-prompt 在手機上逐頁標註，從首頁走到註冊、紀錄、問答和聽力圖，共 40 筆。分支 `style/guest-flow-copy`，三個功能 commit：`284e067d`（首頁）、`781c7f5c`（問卷、作答、結果頁）、`34b47158`（註冊、同意、存好了、我的紀錄、問答、聽力圖）。沒有規格 issue：本人逐筆標註，每頁改動前先看過設計圖並點頭。

**不需交叉審查**：這次動到同意前可用的頁面（`OPEN_PAGES` 加入 `email_confirm_resend`），照規定需要交叉審查，本人決定不做。

**實機驗收**：本人 2026/11/27 實際操作，通過。

## 自動驗證

- Django 全套 3,345 項，3,344 項通過、1 項跳過。
- 前端 810 項通過，前端建置與 Ruff 通過。
- 端對端 524 項，523 項通過。`SpeechBananaEarTest.test_switching_stays_put_and_keeps_the_group` 切換左右耳後捲動位置偶爾差 1–2px：在 `main`（`84c32f6e`）另開 worktree 重跑 4 次，失敗 3 次，原本就不穩定，與本 PR 無關。

## 改動與驗證對照

| 頁面 | 改動 | 驗證 |
|---|---|---|
| 首頁（未登入） | 小鳥改「您是否有聽覺困擾？」 | `test_home_doors.py:43`、`test_search_titles.py`、`test_pages.py` 首頁順序 |
| 首頁（未登入） | 藍卡標題、兩個小標、「加到手機主畫面」置中 | `test_home_doors.py:63`（`text-center`）、`test_home.py:99`（`justify-center`） |
| 首頁 | 「內容由台灣執業聽力師設計與審定」置中（未登入與已登入未作答都是） | 只有 CSS，預覽 390px 與 320px＋200% 字級目視 |
| 問卷精靈 | 小鳥小字刪 | `test_bird_hero.py:82`（`ONE_LINE` 清單）、`:206` |
| 作答頁 | 小鳥小字、頁首右邊主題、「・大約 N 分鐘」刪 | `test_answer_page_layout.py:41`、`test_questionnaire_definitions.py:202`、`test_pages.py` `_assert_progress` |
| 作答頁（未註冊） | 只留「隱私權說明」連結 | `test_guest.py:131` |
| 作答頁 | 「先選一個答案，才能按…」刪，按下仍提示「請先選一個答案」 | `AnswerApp.test.jsx:592` |
| 結果頁（所有問卷） | 小鳥一行：剛做完「辛苦了，看看結果」，再打開「這是您這一次的結果」 | `test_just_saved.py:81`、`:106`、`guest-results.test.js:309`、e2e `test_the_bird_says_done_only_right_after_sending` |
| 結果頁 | 「這個分數怎麼算」標題與「每一題的分數加起來…」刪；「聽力問題影響在哪裡」改 h2，標題不跳層 | `test_score_explain.py:44`、`:125`、`test_ioi_ha.py` 標題大綱 |
| 結果頁 | HHIE-S 輕到中度就醫建議改寫 | `test_guest_save.py:179`、`test_result_next_steps.py` |
| 保存卡 | 理由改寫；「想留下這次結果？」、耳鳴問卷、保存天數兩行刪 | `test_guest_save.py:93`、`:130`、`:193`、`test_no_aid_advice.py` |
| 註冊頁 | 小鳥小字、出生年說明、「註冊後會請您閱讀…」刪 | `test_accounts.py:592`、`:661`、`test_consent.py:125` |
| 同意頁 | 標題改「使用之前，請先看看這些說明」 | `test_consent.py:298`、`test_account_redesign.py` |
| 同意頁 | 確認信通知只寫信箱，下面「沒收到？重寄確認信」，按了留在原頁，同意前也能用 | `test_email_confirmation.py:82`（改前：同意前按下被擋，信沒寄）、`:287`（沒有 next 或指向別站時回帳號設定） |
| 存好了 | 小鳥小字、「接下來 首頁會告訴您…」刪 | `test_guest_save.py:298` |
| 我的紀錄 | 小鳥小字、趨勢圖下「分數越低…」、「家人不用登入就能看」刪；「每次的紀錄」改「歷史」 | `test_history.py:664`、`:1040`、`test_records_page.py:80`、`test_thi_history.py`、`test_report.py:309` |
| 我的紀錄 | 問卷標題與下方方塊間距 0.5rem，同「分數趨勢」 | 只有 CSS，預覽量到 9px（0.5rem） |
| 問答回答頁 | 返回主題／問答小助手的連結、小鳥小字刪 | `test_qa_topics.py:125` |
| 聽力圖 | 新增頁的準備說明、小鳥小字刪；聽力圖頁小鳥小字刪 | `test_audiogram.py:1646`、`test_bird_hero.py:82` |

## 不在這個 PR

- 聽力圖日期改成日曆選擇、刪民國換算說明（標註 `#6ba07f21`、`#d8a736bf`）：另開 session 先做比較頁。
- 小鳥小字只刪了標註的頁面，其他頁維持（本人決定）。
