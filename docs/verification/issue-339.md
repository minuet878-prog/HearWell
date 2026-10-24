# #339 篩檢分頁：老使用者看目錄，推薦精靈改問想了解什麼

日期：2026-10-24。規格：#339；票：#345–#347。基準：`origin/main` `38416ec`；整合分支：`feat/screening-tab-wizard`。決策：ADR 0030（拷問 Q1–Q15；原編 0028，因按鈕回饋與 scroll 兩批分支也用 0028 而改號）。

狀態：等本人實際操作驗收。自動測試與自審（Standards／Spec）都已通過，自審找到的 7 項已修。這次的 #346 新增只讀 `request.user` 自己紀錄的查詢，依 AGENTS.md 應做交叉審查；2026-10-24 本人決定這次略過交叉審查，直接驗收。沒有操作真實資料，也沒有新增 migration。

## 測試結果（整合分支 `27355e3`）

- 前端建置成功；`ruff check .`、`ruff format --check .` 通過。
- 單元測試 1369 項通過（`--parallel 4`）。
- 前端測試 237 項通過。
- 整套 e2e 179 項通過（`e2e.main_flow --parallel 4`）。
- 截圖程式 `SHOTS_GROUPS=answering` 跑得完（截圖不進版控）；它的假使用者四條推薦規則都不符合，所以目錄截圖裡沒有推薦區塊。

## 做了什麼

- **老使用者點「篩檢」直接看問卷目錄**：六份照原順序；做過的卡片多「上次 YYYY/MM/DD」（台北日期、最近一筆）；最下面「不確定做哪一份？回答幾個問題，幫您挑」連到精靈（`?wizard=1`），從那裡進精靈，第 1 步的「上一步」回目錄。新使用者照舊進精靈。
- **目錄最上面的推薦問卷**「推薦您做這一份」，照順序挑第一個符合的：重測到期 → 上次那份；沒做過生活影響問卷 → 依年齡一份，看不出年齡時 HHIE-S、HHIA-S 都列；有戴著作答的紀錄＋可以分組的沒戴紀錄＋沒做過 IOI-HA → IOI-HA；都不符合就不放。
- **推薦精靈第 1 步改問「您最想了解什麼？」**（五個單選）。不再問有沒有戴助聽器；年齡只在結果是生活影響問卷、又看不出年齡時才問。選「助聽器」：有沒戴紀錄推 IOI-HA，沒有就先推沒戴時的生活影響問卷（作答頁預選「沒戴」）。結果頁的「如果您有耳鳴」連結拿掉。
- **生活影響問卷全站同一條**：做過就推上次那份，沒做過才看年齡。
- 問卷定義新增 `concern` 欄位，取代 `wizard_offer`；`WearingNowForm` 移除。推薦原因文字在 `scoring.py`（#339 的草稿）。

## 實作判斷（請本人留意）

- **步數**：規格寫「看不出年齡，第 1 步寫共 3 步」。實作改看「會不會真的問到年齡」：做過生活影響問卷的人永遠不會被問年齡，所以第 1 步寫「共 2 步」。沒有紀錄的人兩種寫法結果相同。
- **目錄標題**：老使用者的目錄標題沿用「自行選擇問卷」，緊接著是「推薦您做這一份」。規格沒寫標題文字。
- **兩份並列**時，「為什麼推薦」只寫一次，放在兩份問卷之前；兩個「開始作答」按鈕各帶一段只給螢幕閱讀器念的問卷名。
- **目錄裡的推薦區塊**也有「上次」日期標籤（目錄資料本來就帶日期）；精靈結果頁沒有。
- **「自己選問卷」連結**：每一步和結果頁都有（驗收 19）；原本結果頁沒有。
- **老使用者打開 `?choose=self`**，看到的跟目錄是同一個畫面（有推薦、日期和「幫您挑」）。
- **沒選就按下一步**：瀏覽器會先用內建提示擋下（單選有 `required`），伺服器的紅框和錯誤字平常看不到。這是沿用年齡題原本的做法。
- **「戴著作答」的判斷**：SADL 一律存「有戴」；IOI-HA 存的是空值，但規則 3 本來就要求沒做過 IOI-HA，所以不影響。
- 推薦原因的 9 句都是草稿，請審定。

## 驗收對照（#339）

勾選代表自動驗證，等本人實際操作確認。unit＝`screening/tests/test_recommendations.py`（另註明的除外）；e2e＝`e2e/main_flow.py`。

| # | 驗收條件 | 驗證 | 證據 |
|---|---|---|---|
| 1 | 老使用者點篩檢看到目錄（六份、原順序），分頁標示為目前所在 | ✅ 自動 | unit `test_a_returning_user_sees_the_catalogue_not_the_wizard`（`:554`）；e2e `test_screening_tab_shows_the_catalogue_with_last_dates`（`:814`） |
| 2 | 做過的卡片有「上次」台北日期、取最近一筆，其他沒有 | ✅ 自動 | unit `test_answered_questionnaires_show_the_taipei_date_of_their_latest_record`（`:567`）、`test_the_dates_come_in_one_query_however_many_cards_have_one`（`:589`）；e2e `:814` |
| 3 | 重測到期、過了 65 歲的 HHIA-S → 推 HHIA-S、重測文字、在卡片最上面、底下照列 | ✅ 自動 | unit `test_a_due_retest_recommends_the_last_life_impact_questionnaire_again`（`:703`） |
| 4 | 只做過 THI、70 歲 → 推 HHIE-S | ✅ 自動 | unit `test_without_a_life_impact_record_one_is_recommended_by_age`（`:722`） |
| 5 | 只做過 THI、沒填出生年 → 兩份都列、各寫年齡、各有按鈕 | ✅ 自動 | unit `test_without_a_life_impact_record_or_an_age_both_are_listed`（`:736`）；e2e `test_both_recommended_life_impact_questionnaires_fit_a_phone`（`:844`） |
| 6 | 沒戴 HHIE-S＋戴著的紀錄＋沒做過 IOI-HA → 推 IOI-HA | ✅ 自動 | unit `test_aided_and_unaided_records_without_ioi_ha_recommend_ioi_ha`（`:757`） |
| 7 | 都不符合 → 沒有推薦區塊；規則 1 先於規則 3 | ✅ 自動 | unit `test_no_rule_holding_leaves_no_recommendation`（`:773`）、`test_a_due_retest_comes_before_ioi_ha`（`:790`） |
| 8 | 「幫您挑」進精靈第 1 步，上一步回目錄 | ✅ 自動 | unit `test_help_me_choose_opens_step_one_whose_back_returns_to_the_catalogue`（`:602`）；e2e `:814` |
| 9 | 新使用者看到五個選項、沒有戴助聽器題 | ✅ 自動 | unit `test_step_one_asks_what_the_user_most_wants_to_know`（`:96`）、`test_a_new_user_still_gets_the_wizard_whose_back_goes_home`（`:622`） |
| 10 | 剛註冊同意後，招呼語在第 1 步上方 | ✅ 自動 | unit `test_greeting_only_on_the_first_screen_after_consent`（`:420`）；e2e `step3_choose_hhie_s`（`:632`） |
| 11 | 看得出年齡選 1 或 5 → 第 2 步／共 2 步，依年齡推，沒有也可以做 | ✅ 自動 | unit `test_life_impact_or_unsure_with_a_known_age_recommends_by_age_in_two_steps`（`:154`） |
| 12 | 耳鳴推 THI、吵雜推 SSQ12-TW，沒有也可以做、沒有耳鳴連結 | ✅ 自動 | unit `test_tinnitus_and_listening_recommend_thi_and_ssq12_alone`（`:171`）；`test_thi_wizard.test_no_result_links_thi_on_a_line_of_its_own`（`:35`） |
| 13 | 沒有沒戴紀錄選助聽器 → 先做沒戴的生活影響問卷、預選沒戴、也可以做 IOI-HA、SADL | ✅ 自動 | unit `test_hearing_aid_without_an_unaided_record_catches_one_up_first`（`:187`）、`test_after_catching_up_the_hearing_aid_answer_recommends_ioi_ha`（`:361`）；e2e `test_age_step_and_recommendation_without_javascript`（`:482`） |
| 14 | 有沒戴 HHIE-S 選助聽器 → IOI-HA，也可以做「戴著再做一次」HHIE-S、SADL | ✅ 自動 | unit `test_hearing_aid_with_an_unaided_record_recommends_ioi_ha`（`:208`）、`test_the_aided_retake_is_the_latest_life_impact_questionnaire`（`:228`） |
| 15 | 沒填出生年：共 3 步；耳鳴直接結果；聽不清楚先問年齡 | ✅ 自動 | unit `test_without_a_birth_year_only_a_life_impact_result_asks_the_age`（`:236`）；`test_thi_wizard.test_the_tinnitus_answer_never_asks_the_age`（`:60`） |
| 16 | 今年剛好 65 選不確定 → 問年齡 | ✅ 自動 | unit `test_turning_65_this_year_asks_the_age`（`:262`） |
| 17 | 做過 HHIA-S、剛好 65 → 不問年齡、推 HHIA-S | ✅ 自動 | unit `test_a_life_impact_record_is_recommended_again_without_asking_the_age`（`:270`）、`test_the_latest_life_impact_record_wins_over_the_age`（`:281`） |
| 18 | 沒選就送出 → 停在同一步、紅框與錯誤字 | ✅ 自動 | unit `test_nothing_chosen_stays_on_the_step_with_the_error`（`:292`）（見「實作判斷」：瀏覽器會先擋） |
| 19 | 上一步、自己選問卷；年齡步上一步保留答案；看其他問卷六份 | ✅ 自動 | unit `test_every_step_has_back_and_choose_yourself`（`:324`）、`test_back_to_step_one_keeps_the_answer_chosen`（`:352`）；e2e `:482` |
| 20 | 關掉 JavaScript 走得完 | ✅ 自動 | unit `test_wizard_walks_to_the_answer_page_with_forms_and_links_only`（`:501`）；e2e `:482` |
| 21 | 五個選項在名為「您最想了解什麼？」的群組 | ✅ 自動 | unit `:96`；e2e `:482` |
| 22 | 手機寬度、字級 200% 不左右捲動，日期標籤完整 | ✅ 自動 | e2e `test_first_visit_pages_fit_a_phone_at_double_text_size`（`:220`，精靈各步）、`:814`（目錄、日期、單份推薦）、`:844`（兩份推薦） |
| 23 | 測試、Ruff、建置、整套 e2e 通過 | ✅ 自動 | 見「測試結果」；截圖基準不進版控，截圖程式跑得完 |

## 本人操作確認

預覽在 worktree 開 `http://localhost:8001`（整合分支），用本人自己的帳號看：

1. 點底部「篩檢」：看到目錄、做過的卡片有「上次」日期、最上面的推薦問卷（或沒有）合不合理。
2. 點最下面「幫您挑」：五個選項各點一次看推薦與原因；按「上一步」回目錄。
3. 想看新使用者的精靈，可以另外註冊一個測試帳號（這會在本機資料庫新增一個帳號，由本人決定）。
4. 審定推薦原因的文字、目錄標題要不要改。

（等本人操作後填寫）
