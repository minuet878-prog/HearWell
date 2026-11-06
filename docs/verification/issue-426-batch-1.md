# 家人專區第一批（#426，票 #427–#429）

日期：2026-11-06。分支：`feat/426-family-zone`。規格：[#426](https://github.com/minuet878-prog/HearWell/issues/426)；拷問決定：[family-zone](../planning/family-zone/grill-decisions.md)。

狀態：2026-11-06 本人審字並回覆「驗收通過」。自動測試與自審都已完成。第二批（#430–#432）、第三批（#433–#435）還沒開始，母規格 #426 繼續開著。

## 本人決定

1. 專區首頁版面在比較頁選 A 案：一條一張卡，有圖示和一句說明。
2. 主標題由審定過的「給家人的溝通與陪伴」改成「家人專區」，分享標題跟著變。原本的溝通、陪伴、就醫內文不變。
3. 「長輩不肯去怎麼說」拿掉 Cleveland Clinic（代理只讀到摘要）和 UHCW 單張（已過複審日）兩個出處，只留讀過全文的 NCOA、ASHA、NIDCD。
4. 問卷與新增聽力圖的下一步連結加「（要先註冊或登入）」。
5. 頁尾、帳號設定、失效分享頁的「給家人看：怎麼跟聽損的家人溝通」統一成「家人專區：溝通與陪伴」。問答小助手答案裡的「給家人看的」留給 #402。
6. 交叉審查略過：這批改了 `OPEN_PAGES`，多放行一個不含個人資料、不讀 `request.user` 的頁面，屬於 `AGENTS.md` 要做交叉審查的權限改動，本人決定略過。

## 做了什麼

- `/family` 變成家人專區首頁：入口卡、溝通情境題（5 題、每題 3 個選項，選了才看到說明，不打分、可改選）。
- 新公開頁 `/family/reluctant`：依狀況看可以試的說法、容易有反效果的說法和下一步。
- 新訪客首頁加家人卡片；了解頁、頁尾、分享報告頁都連得到專區。老使用者首頁和底部分頁不動。
- 共用「點選看說明」：內容在 `screening/family_zone.py`，模板片段與 `pick-explain.js` 第三批會重用。沒有 JavaScript 時說明全部顯示，不存也不送資料。
- `family_reluctant` 加入 `OPEN_PAGES`，跟 `/family` 一樣，未同意隱私權也能開。
- roadmap 的每年查核加上家人專區。

## 文字審查

2026-11-06 本人審過[審字清單](#審字清單的內容)後回覆驗收通過，沒有要求改字。代理延伸或來源不足的句子都在清單標給本人看：

- 情境題：「您是想讓他聽到」「您是想幫忙」「您已經走近了」「吃飯時不急著說也沒關係」「請醫師面對他，說慢一點」「可以先跟他說一聲，再把電視關小聲」。
- 長輩不肯去：「容易有反效果」的例句（依來源原則擬的）、「爭對錯不容易談下去」、「不是檢查了就要戴助聽器」、「要不要先跟有戴助聽器的朋友聊聊」、拿掉出處後沒有來源的「我想一直跟您好好聊天」。

### 審字清單的內容

內容就是 `screening/family_zone.py` 與 `family_guide.html`、`family/reluctant.html` 的固定句，查核日都是 2026/11/06。

## 驗收條件

| 驗收條件 | 結果 | 證據 |
|---|---|---|
| 訪客與新使用者首頁有家人卡片，主要按鈕順序不變 | 通過 | `FamilyZoneHomeTests.test_visitor_sees_the_family_card_under_the_guide_card`、`test_new_user_without_records_sees_the_family_card` |
| 老使用者沒有卡片，底部分頁不變 | 通過 | `test_returning_user_home_has_no_family_card_and_the_same_tabs` |
| 了解頁、頁尾、分享報告頁連得到專區 | 通過 | `test_entries_from_learn_footer_and_shared_report_reach_the_zone` |
| `/family` 不用登入，未上線批次沒有入口 | 通過 | `test_visitor_sees_the_zone_home_without_logging_in`、`test_entries_only_for_what_is_live` |
| 舊連結落在原段落，審定內文還在 | 通過 | `test_old_anchors_land_on_their_original_sections_with_the_reviewed_words`、`test_family_guide.py`、e2e `test_old_jump_link_lands_on_its_section`；主標題依決定 2 改名 |
| 依選定版面實作 | 通過 | 決定 1；`test_visitor_sees_the_zone_home_without_logging_in` 比對入口卡 |
| 情境題選了才有說明，沒有對錯與分數，可改選 | 通過 | e2e `FamilyScenarioTest.test_walks_from_the_zone_home_to_a_pick_and_changes_it`、`pick-explain.test.js`、`FamilyScenarioTests.test_no_form_score_or_verdict` |
| 說明寫進通知區塊，可用鍵盤操作 | 通過（實際朗讀未驗） | `test_each_scenario_has_one_polite_live_region`、e2e `test_keyboard_picks_and_changes`；自動測試只驗內容寫進 aria-live |
| 關 JavaScript 全部顯示 | 通過 | e2e `test_without_javascript_every_explanation_shows_and_fits_a_phone`、`test_without_javascript_everything_shows_and_fits_a_phone` |
| 減少動態效果時沒有動畫 | 通過 | e2e `test_explanation_appears_without_animation` |
| 每個選項有說明，內容有出處與查核日期 | 通過 | `FamilyContentDefinitionTests` |
| 長輩頁選狀況看到三類內容，頁尾有出處、查核日期、回專區 | 通過 | `FamilyReluctantTests.test_server_sends_every_situation_in_full_with_a_live_region`、`test_foot_has_sources_checked_date_and_the_way_back`、e2e `FamilyReluctantTest.test_walks_from_the_zone_home_to_a_situation_and_back` |
| 手機 200% 字級不左右捲，觸控至少 44px，字至少 1rem | 通過 | e2e `test_phone_at_double_text_fits_with_big_targets_and_readable_words`、`test_home_and_zone_fit_a_phone_at_double_text_size`、`test_new_user_home_card_is_big_enough_to_touch_and_read` |
| 唯一主標題、分頁標在了解，不用登入，不讀本人資料 | 通過 | `test_page_has_one_heading_its_title_and_the_learn_tab`、`test_signed_in_user_sees_the_same_zone_home_without_their_data`、`test_signed_in_user_gets_the_same_page_without_their_data`、`test_view_never_reads_the_user` |
| 未同意隱私權也能開長輩頁 | 通過 | `test_user_without_consent_can_read_it`（修前 302，先失敗再修） |
| 文字與出處由本人審過 | 通過 | 上方「文字審查」 |

## 自動測試

在最後一個程式 commit `85d3840` 上跑，每個都用結束碼確認：

- Django：1658 項通過。
- e2e：292 項通過。
- Ruff：`ruff check .`、`ruff format --check .` 都通過。
- 前端：371 項通過，在前一個合併 commit `f13ab13` 上跑；`85d3840` 沒有改前端程式。

## 自審

Standards 與 Spec 兩軸在合併後各跑一次（基準 `origin/main`）。修掉：`OPEN_PAGES` 漏列長輩頁、長輩頁標題跳級、導覽 aria-label 改「專區內容」、註解與變數名、首頁卡片 44px 與 1rem 的斷言、用有紀錄的帳號驗不讀本人資料、每年查核列入專區。

刻意不修：出處與聲明文字重複、出處和查核日期沒綁成一個型別、`next_steps` 用 tuple、家人 view 分在兩個檔。目前只有兩份內容，第三批再看。測試綁 class 是專案現有寫法。

## 已知限制

- 列印 `/family` 時，收起的說明不會印出來；規格沒要求，這次沒處理。
- 實際朗讀沒有自動測試；審字與操作驗收由本人回覆通過，紀錄沒有逐項列出本人操作了哪些步驟。
- 沒有操作真實資料，也沒有新增 migration。
- 代理開預覽伺服器被權限擋下，代理只用 e2e 臨時網站截圖看過手機畫面。
