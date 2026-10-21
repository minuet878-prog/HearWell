# #128 問卷目錄、作答與結果頁改用 Tailwind 排版驗證

日期：2026-10-21；分支 `feat/128-answering-pages`；母分支 `feat/tailwind-migration`。
狀態：自動驗證完成；本人 2026-10-21 實際操作驗收通過。子分支合回 `feat/tailwind-migration`；沒有 push、開 PR 或合併回 `main`。

## 範圍與參考

- [#128](https://github.com/minuet878-prog/HearWell/issues/128)、母規格 #119、ADR 0008、ADR 0009；做法和 #127 相同（[`issue-127.md`](issue-127.md)）。
- 模板：問卷目錄 `questionnaire.html`、作答頁 `screening.html`、四份問卷說明 `questionnaires/*_intro.html`、結果頁 `result.html`、`ssq12_result.html`、`result_ioi_ha.html`、`ioi_ha_source.html`、配戴比較 `hhi_comparison.html`，以及共用片段 `comparison_content.html`、`comparisons/average.html`、`comparisons/total.html`、`level_badge.html`、`questionnaire_icon.html`。
- React：`AnswerApp.jsx`（一題一頁作答）、`answer-main.jsx`。
- 有名字的元件 class（`btn`、`card`、`link-card`、`result-banner-*`、`level-badge-*`、`list-unstyled`、`text-danger` 等）沒動。

## 對照表

#127 的對照表照用（間距 3 級以上換數字、`d-flex`→`flex`、`fw-*`→`font-*`、`text-body-emphasis`→`text-black`）。這張票新出現的：

| Bootstrap | 數值 | Tailwind |
|---|---|---|
| `mb-4`、`my-3` | 1.5rem、上下 1rem | `mb-6`、`my-4` |
| `fs-5` | 字級 1.25rem（不動行高） | `text-xl/normal`（1.25rem、行高 1.5；這些元素原本繼承的行高就是 1.5） |
| `fs-3` | `calc(1.3rem + .6vw)`，1200px 起 1.75rem | `text-[calc(1.3rem+0.6vw)] min-[1200px]:text-[1.75rem]`（只設字級，標題的 1.2 行高不受影響） |
| `fs-4` | `calc(1.275rem + .3vw)`，1200px 起 1.5rem | `text-[calc(1.275rem+0.3vw)] min-[1200px]:text-[1.5rem]` |
| `flex-column`、`flex-sm-row` | 直排；576px 起橫排 | `flex-col`、`min-[576px]:flex-row` |
| `align-items-start`、`justify-content-between` | | `items-start`、`justify-between` |
| `text-muted` | #495057（舊站覆寫成本文色） | `text-body` |

本人 2026-10-21 決定：Bootstrap 的切換寬度（576px、1200px）直接寫數字，Tailwind 的 `sm:`、`xl:` 維持標準意思（640px、1280px）。

`field_messages.html` 已在 #127 改過，這張票沒動。

## 驗收條件對照

| 條件 | 證明 |
|---|---|
| 1. 截圖只比這群頁面（含四種分級結果、無 JS 作答頁、手機與桌機），和 `main` 沒有超過反鋸齒的差異 | 截圖工具 answering 群組：基準在 `origin/main`（`ef638a7`）用暫時的 worktree 拍，本分支再拍；**38 張全部逐像素相同，字型與基礎字級 0 頁不同**。涵蓋問卷目錄、配戴比較、四份問卷作答頁（有 JS 與沒有 JS）、HHIE-S／HHIA-S 三種分級與無法判讀、SSQ12、IOI-HA 結果頁 × 390／1024 寬。#129 的分支（含本票）再拍一次也是 38 張相同 |
| 2. 這些模板與 React 作答元件搜尋不到 Bootstrap 專屬 class | `screening/tests/test_tailwind.py:78`（搜尋範圍擴大到 React 的 `className`）。改之前列出 48 處，改之後通過 |
| 3. 鍵盤與沒有 JavaScript 完成一份問卷，既有 e2e 主流程全部通過 | `e2e/main_flow.py:74` `test_adult_completes_hhia_s_with_keyboard`、`:101` `test_adult_completes_hhia_s_without_javascript`、`:64` `test_new_user_completes_hhie_s` 等；e2e 全套 42 個通過 |
| 4. 前端測試通過 | `npm test --prefix frontend`：13 檔、190 個通過 |

截圖沒拍到、靠逐條對照數值確認的狀態：1200px 以上的字級、React 作答頁的「已經送出過」「要接著答嗎」「錯誤」「登入過期」、沒有 JS 時的錯誤摘要、SSQ12「無法計算」、配戴比較的預覽與錯誤。這些都只換了上表的 class，數值一樣。

## 自動驗證

| 檢查 | 結果 |
|---|---|
| Django 全套 | 646 個通過（3 個斷言舊 class 字串的測試改成新名稱：`test_answering.py`、`test_scoring.py` 各 1 處；e2e `test_heading_classes_and_muted_text_look_as_before` 的選擇器 `p.h3.text-muted` 改成 `p.h3.text-body`，量的數值沒變） |
| 前端 | 13 檔、190 個通過 |
| e2e `e2e.main_flow` 全套 | 42 個通過 |
| `npm run build --prefix frontend`、`ruff check` | 通過 |

截圖工具的 8765 埠被本機另一個專案佔用，沒有停它；兩邊都暫時改成 8766 拍，拍完已還原。暫時的 worktree 已移除。

## 自審

#128、#129 一起審（基準 `feat/tailwind-migration`），Standards 與 Spec 各由一個子代理審查。

- Standards：0 項硬性違規；判斷題 5 項。
- Spec：class 換法逐條核對都正確（含 `text-xl/normal` 套用的元素原本繼承的行高都是 1.5），0 項要修。

| 發現（和本票有關的） | 處理 |
|---|---|
| 截圖沒拍到部分狀態與 1200px 以上 | 列在上方，靠數值對照 |
| 兩個結果頁的按鈕列 `flex flex-col min-[576px]:flex-row gap-2 my-4` 重複 | 不改：Bootstrap 時期就重複，只出現兩次，ADR 0008 說只用在少數地方的排版直接寫 Tailwind |
| `text-black` 不是主題 token | 不改：和 #127 同樣處理，第 2a 階段改外觀時一起決定 |
| 搜尋測試的清單路徑寫法重複三次、抓不到 `className={a ? "x" : "y"}` 這種條件式寫法 | 不改：目前這些地方沒有 Bootstrap class；記為限制 |

不需交叉審查：只改樣式 class，沒有修改計分、分級、門檻、資料 migration 或權限。

## 本人實際操作（2026-10-21 通過）

- [x] 問卷目錄：年齡確認、目的按鈕、問卷卡片間距和之前一樣。
- [x] 作答頁（有 JavaScript）：題目字級、SSQ12 拉桿上方的分數大字。
- [x] 結果頁：手機上按鈕直排、桌機上橫排。
- [x] 配戴比較頁：預覽卡片與已存比較的間距。
