# e2e 可刪、可合併的測試候選（2026-11-17）

範圍：`e2e/main_flow.py` 全部 90 個類別、501 個測試。三個子代理分段只讀掃描，主代理抽查 4 條高信心項目，證據都成立
（頁尾複製按鈕、SlidingPill、T363 字重、訪客無 JavaScript）。秒數是 `e2e/durations.json`（CI 量的）的類別秒數；
單一測試的秒數是「類別秒數 ÷ 測試數」或「開頁次數」推估。行號是 `main` 上的 `e2e/main_flow.py`。

## 先看結論

- **幾乎沒有「過時」的測試**：前端改版時，測試都跟著就地改了。真正過時的只有 2 個（A 表的 ColourOnly、FamilyScenario）。
- **多的是「重複」**：同一頁的 200% 字級、同一組顏色，被好幾個類別各測一次；有些 e2e 測的東西，後端（不開瀏覽器）早就測過。
- **CI 時間省得不多**：全部做完約省 250 秒機器時間（總量 1,944 秒的 13%），三台各 4 個程序分攤後，**整輪 CI 約只快 20 秒**。
  e2e job 現在約 4 分半，其中約 1 分半是每台的準備時間。
- **主要好處是維護**：以後改前端時，要跟著改的測試變少；同一件事只在一個地方測。

## A. 高信心：直接刪（31 個測試，約 115 秒）——已做，見 `docs/verification/e2e-prune-duplicates.md`

刪之前主代理逐條核對過下表的證據，有兩條調整：ColourOnly :7217 改歸「重複」（表格在摺疊內由 StyleInBrowser :5482
驗得更嚴，只剩已拿掉的藍邊沒人守）；WhiteCard :8294 的「已登入的家人專區」只有它用 CUT_OFF 量，所以把那一頁加進
`WHITE_CARD_PAGES_LEARN` 再刪。

| 類別.測試 | 種類 | 已由誰測過 |
|---|---|---|
| SharedLayoutTest.test_result_level_is_exposed_as_a_heading（:1825） | 後端已有 | `test_accessibility.py:32`、`:51` |
| SharedLayoutTest.test_history_exposes_older_records_outside_the_chart_summary（:1836） | 後端已有 | `test_accessibility.py:90` |
| SharedLayoutTest.test_share_page_and_add_to_home_without_javascript（:2413） | 後端已有 | `test_share_page.py:175`、`test_add_to_home.py:72` |
| SharedLayoutTest.test_home_steps_fit_a_phone_at_double_text_size（:2637） | 重複 | WhiteCardRuleTest :7862、同類別 :2647 |
| LearnPageTest（整類，2 個） | 重複 | WhiteCardRuleTest :8350、BottomTabsTest :4652、`test_learn.py:41–57` |
| FamilyZoneHomeTest.test_home_and_zone_fit_a_phone_at_double_text_size（:4372） | 重複 | :7862、:2647、:8294、:8350 |
| BottomTabsTest.test_records_and_learn_fit_a_phone_at_double_text_size（:4652） | 重複 | WhiteCardRuleTest :9112、:8350 |
| BottomTabsTest.test_records_switch_changes_page_without_javascript（:4743） | 後端已有 | `test_records_switch.py:57`、`:70` |
| SlidingPillTest.test_pill_slides_between_questionnaires_and_audiograms、…_between_ears（:3122、:3132） | 重複 | 同類別 :3083 慢手機版（同兩個切換器，各來回 3 次）✔ 已抽查 |
| StyleInBrowserTest.test_masking_switch_keeps_its_orange（:6005） | 重複 | MaskingSwitchTest :2760 |
| StyleInBrowserTest.test_clickable_cards_are_rows_between_thin_lines（:5991） | 重複 | WhiteCardRuleTest :8865 |
| NewUserScreeningTest.test_family_guide_marks_the_urgent_one（:664） | 重複 | `test_family_redesign.py:153`、WhiteCardRuleTest :8228 |
| ColourOnlyFeedbackTest.test_open_dropdown_contents_start_clear_of_the_blue_edge（:7217） | **過時** | 藍邊在 #465（ae0f1878）拿掉，測試已沒在測藍邊 |
| WhiteCardRuleTest.test_ear_results_share_steps_and_comparison_fit_a_phone_at_double_text_size（:9099） | 重複 | RecordsT465 :14444、同類別 :8750 |
| WhiteCardRuleTest.test_family_guide_fits_a_phone_at_double_text_size（:8294） | 重複 | :8350、:14892、SharedLayout :2647 |
| ResultPagesT363Test.test_ssq12_lowest_questions_are_in_normal_weight（:11476） | 重複 | WhiteCardRuleTest :8969 ✔ 已抽查 |
| SpeechBananaReminderTest 的 3 個測試（:12365、:12376、:12386） | 後端已有 | `test_speech_banana.py:384`、`:418`、`:424`、`:428` |
| ContentAndContact576Test.test_no_button_without_java_script（:10657） | 後端已有 | `test_layout.py:295–315` ＋ `site.css` 的 `[hidden]` ✔ 已抽查 |
| FamilyAndAccountT361Test.test_address_without_javascript（:11643） | 後端已有 | `test_family_guide.py:254` |
| FamilyReluctantTest／FamilyHearingAidsTest.test_zone_home_fits_with_the_new_entry（2 個） | 重複 | WhiteCardRuleTest :8294、T469 :14895、:4331 |
| FamilyHearingAidsTest.test_jump_link_lands_on_the_section、…_guide_link_opens_the_types_and_prices_chapter | 後端已有 | `test_family_hearing_aids.py:185–204` |
| FamilyAdjustingTest.test_jump_link_lands_on_the_section | 後端已有 | `test_family_adjusting.py:114–116` |
| FamilyDeadlinesTest.test_all_three_dates_still_ahead_say_nothing_has_passed | 後端已有 | `test_family_deadlines.py:55`、`:111`、`:237` |
| GuestWithoutJavaScriptTest（整類） | 後端已有 | `test_guest.py:503–513` ✔ 已抽查 |
| FeedbackTest.test_sent_from_a_footer_without_javascript_and_back_to_that_page | 後端已有 | `test_feedback.py:40`、`:82–143` |

## B. 中信心：先把獨有的檢查搬過去再刪，或合併（約 25 項，約 100 秒）

- **把一兩行斷言併進別的測試，再刪**：
  - SharedLayout :2022 ＋ NewUserScreening step7 的列印 → 把 `#report-share` 併進 StyleInBrowser :5807。
  - NewUserScreening :304 顯示密碼 → 把 `type` 屬性併進 :1205。
  - WhiteCard :9112 → 把 `/audiograms` 加進 RecordsT465 :14456。
  - HearingAidGuide :4119 → 把 `#without-certificate` 併進 :4130。
  - T469 :14975 → 把白底斷言併進 :13311。
- **同一件事測了好幾次**：
  - StyleInBrowser 的等級顏色測了三次（:5615、:5646、:5669），留 :5688（7:1 對比）和 :5040 就夠。
  - StyleInBrowser :6455、:6493、:6275 和 ColourOnly 重疊，可以併進去。
  - 鍵盤操作：家人專區四頁共用同一個模板，只留 FamilyScenario :12486，其他頁的鍵盤測試可刪。
- **減少重跑**：
  - NewUserScreening :288 為了驗一行字，重跑了整段註冊加作答，可以改成直接建紀錄。
  - GuestHomeTest 也多跑一次作答，可以併進 GuestSaveFromCard。
  - NarrowOverflowsT668 和 LastResultT649 的設定相同，可以合成一個。
- **WhiteCardRuleTest 少開約 30 次頁面**：learn 頁清單拿掉 9 頁、報告兩頁、作答頁，都是別處已用同樣的 CUT_OFF 檢查過的。
  另外幾項（首頁和結果頁、了解頁）要先把 T461、T469 改用 CUT_OFF（WhiteCardRuleTest 抓「區塊被裁掉」的檢查，
  比只量頁面寬度嚴格），才能拿掉。

## C. 待確認：要你判斷值不值得守

- **瀏覽器原生行為**：EnterNextFieldTest :16636（沒有 JavaScript 時按 Enter 送出），後端只能驗屬性。
- **焦點**：FeedbackTest :16781（防機器人欄位按 Tab 不會停到）。照規則，焦點屬於 e2e 該守的範圍。
- **200% 字級分工**：SharedLayout :2437、:2647 會先打開摺疊、檢查控制項有沒有重疊，WhiteCard 不做這兩件事。要先決定由誰負責。
- **改成靜態檢查**：
  - `:7748` 的 `OLD_BEIGES`：防的是已經刪掉的米色回來。
  - `:5040` 的 token 快照：可以改讀 `site.css`，代價是不再驗證建置後的 CSS。
- **改成後端作答**：NewUserScreening :399、:571（沒有 JavaScript 作答），要先確認後端有整份 POST 到結果頁的測試。

## 確定該保留

這些類別在測 JavaScript 時間軸、焦點、動畫、上一頁還原、列印或 OIDC 回呼，沒有可刪的：

- 動態與時間軸：JumpHighlightTest、PlayInViewTest、WearMotionTest
- 登入與註冊：GuestSavesFromTheCard（Google／LINE）、CopyPasswordRegisterFeedbackTest
- 聽力圖：AudiogramReadingTest、AudiogramDemoTest
- T357、T359–T367 這批版面類別的大部分
- 其他沒列在上面的測試

## 順手發現（無關，只提出）

- `e2e/main_flow.py:5297` 引用一個已不存在的 `test_primary_button_states_follow_choice_c`（現在叫 `test_primary_button_states_are_solid_blues`）。
- `:6203` 的註解還寫「every button is a pill」，但 ADR 0043 之後按鈕是圓角方形。
