# 助聽器驗證流程連結（F1–F5）

日期：2026-10-23；分支 `feat/aid-verification-links`（從 `origin/main` 開出，PR #254 合併後）。
狀態：自動驗證完成；**不需交叉審查**（只改文字、連結、預選與章節順序，不碰計分、分級、門檻、資料或權限）；**本人看截圖驗收通過**（2026-10-23；在 worktree 開預覽伺服器被權限擋下，沒有實際操作）。

## 範圍

結果頁與助聽器驗證流程審查的第 3 批（對話中整理，沒有開 issue）。F1、F3 措辭由本人在對話中逐字核准；F2 取代 #190 規格的「沒有保留組合時留空」；F5 本人選對調。

| 項目 | 需求 | 改了哪裡 |
|---|---|---|
| F1 推薦理由 | 改成「您有戴助聽器，也有沒戴助聽器時的紀錄。這份問卷了解助聽器對您的幫助，並和沒戴時困擾程度相近的一般使用者比較。」 | `scoring.py` 的 `RECOMMENDATION_REASONS["has_norm_basis"]` |
| F1 戴著再做一次 | 推薦 IOI-HA 時，「也可以做」第一張：「戴著助聽器再做一次「聽力對生活的影響」（HHIE-S）」＋「和沒戴時的結果比較，看助聽器幫了多少。」；65 歲以下是 HHIA-S；作答頁照常自己選「有戴」 | `scoring.py` 的 `AIDED_RETAKE_*`、`questionnaire_list`、`questionnaire.html`、`questionnaire_card.html` |
| F2 比較頁預選 | 沒有保留組合時，只有一筆的那一邊預先選好；兩筆以上照舊留空。日期「同一天才補時間」是設計，不改 | `forms.py` 的 `HhiComparisonForm` |
| F3 第 5 章卡片 | 「用 HearWell 準備驗證回診」卡片，連 HHIE-S、HHIA-S、IOI-HA、SADL 與聽力報告 | `guide/form_25.html`、`views.py` 的 `_form_25_context` |
| F4 第 6 章連結 | 「也可以戴著助聽器再做一次生活影響問卷（HHIE-S 或 HHIA-S），和沒戴時的結果比較。」兩份都連 | `guide/after_fitting.html`、共用片段 `guide/life_impact_links.html` |
| F5 章節順序 | …種類與價格 → 配戴助聽器之後 → 二十五號表；網址不變 | `views.py` 的 `GUIDE_CHAPTERS` |

## 驗收條件對照

| 條件 | 證明 |
|---|---|
| F1 新理由逐字 | `test_recommendations.py` `test_aided_with_unaided_record_recommends_ioi_ha` |
| F1 戴著再做一次排第一張、標題與說明、不帶 `?preselect` | 同上（卡片網址完全相等、順序 HHIE-S → SSQ12-TW → SADL） |
| F1 65 歲以下是 HHIA-S，標題跟著變 | `test_recommendations.py` `test_aided_retake_card_follows_the_age_group` |
| F1 只有推薦 IOI-HA 時才出現 | `test_thi_wizard.py` `test_aided_result_offers_thi_and_keeps_also_worth_doing`；需要補沒戴紀錄時照舊兩張（`assert_ssq12_also`） |
| F2 一筆預選、兩筆以上留空、日期格式照舊 | `test_hhi_comparisons.py` `test_cards_show_date_and_score_with_time_on_shared_days_and_a_lone_record_chosen`；`test_ssq12_comparisons.py`；e2e `test_wearing_comparison_route_from_result_page_to_report` |
| F2 查詢數不隨紀錄增加 | `test_hhi_comparisons.py` `test_query_count_does_not_grow_with_records` |
| F3 卡片在清單後、措辭照順序、四個連結＋報告、不連 SSQ12-TW | `test_guide_form_25.py` `test_preparation_card_after_the_list_links_the_questionnaires_and_report` |
| F4 句子連到 HHIE-S、HHIA-S | `test_guide_form_25.py` `test_the_aided_retake_sentence_links_both_life_impact_questionnaires` |
| F5 目錄順序、網址不變 | `test_guide.py` 的 `CHAPTERS`；e2e 選配指引路線 |

## 自動驗證

| 檢查 | 結果 |
|---|---|
| `python manage.py test --settings=config.test_settings` | 1076 個全部通過；新測試先確認在改之前失敗 |
| `npm test --prefix frontend` | 217 個全部通過 |
| `ruff check .` | 通過 |
| `e2e.main_flow --parallel 4`（先 `npm run build`） | 104 個全部通過 |

過程中抓到的問題：

- 預選第一版有 bug：第一邊選好後 `self.initial` 就不是空的，第二邊被跳過。「查詢數不隨紀錄增加」的測試抓到（兩邊各一筆時少一次查詢），改成迴圈前先判斷有沒有保留組合。
- 共用連結片段的換行被印出來，畫面會變成「（ HHIE-S 或 HHIA-S ）」；改成單行。
- 舊測試寫死「沒有預選」的（`test_hhi_comparisons`、`test_ssq12_comparisons`、兩個 e2e）改成新行為；量未選取框線顏色的 e2e 多建一筆沒戴的紀錄，讓那一邊維持未選。

## 自審（Standards 與 Spec 兩軸）

已修：

- 規範第 9 條：第 5 章卡片寫死「聽力對生活的影響」，改從問卷定義的主題取。
- HHIE-S／HHIA-S 改從定義的 `life_impact` 挑，不再寫兩個代碼；排除 SSQ12-TW 寫明代碼，不用「平均計分」間接表示。
- 精靈的「戴著再做一次」卡片資料包成一組；變數改名。
- 補 HHIA-S 卡片標題與說明的斷言。

不修（判斷題）：指引兩章各自寫「和沒戴時的結果比較」（指引章節本來就是手寫的審定內容）；測試的 `inline_text` 和 `text_of` 很像。

## 偏離（本人 2026-10-23 接受）

1. **F4 沒有依年齡只連一份**：選配指引的章節不用登入也能看，內容對每個人都一樣、不讀個人資料，所以兩份都連（跟 F3 核准的「HHIE-S 或 HHIA-S」一致）。報告原文寫「依年齡連」，這裡是刻意偏離。
2. **F2 也套用到 SSQ12-TW 的比較頁**：兩頁共用同一個表單，行為一樣。

## 本人驗收

看 390px 手機寬的截圖（推薦精靈、比較頁、指引目錄、第 5 章、第 6 章），2026-10-23 接受：

- [x] 推薦精靈（有戴、有沒戴紀錄）：新理由；「也可以做」第一張是「戴著助聽器再做一次」
- [x] 比較戴與不戴：兩邊各一筆時已選好，按「查看比較」就能看
- [x] 選配指引：目錄「配戴助聽器之後」在「二十五號表」前面；第 5 章有準備卡片；第 6 章句子有連結
- [x] 上面兩項偏離都接受
