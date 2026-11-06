# 聽力圖看語言香蕉區（#436，票 #440–#443）

日期：2026-11-06。分支：`feat/436-speech-banana`。規格：[#436](https://github.com/minuet878-prog/HearWell/issues/436)；拷問決定：[speech-banana](../planning/speech-banana/grill-decisions.md)；判斷依據：[ADR 0040](../adr/0040-speech-banana-judged-against-the-hearing-line.md)。

狀態：自動測試、自審、交叉審查都已完成。**還沒通過：本人實際操作、手機實測、雅文使用許可（#439）。**

## 本人決定

1. 判斷規則、六群、字句和例字都由本人審定；來源用雅文基金會〈聽力圖和語言香蕉區〉海報。
2. 實作時的三項決定：聽力圖的標記畫在框上面；這一頁拿掉綠色的正常範圍帶，圖上唯一的色帶是香蕉區；選到的框一律實心深藍，只有沒選到的「可能不容易聽到」是虛線。
3. 報讀文字照實作的寫法。
4. 2026-11-06 豁免兩條驗收條件的測試斷言，改用下面「豁免的條件」的核對當證據。

## 自動測試

提交 `0fd6272`（已合入最新的 `main`），2026-11-06：

| 項目 | 結果 |
|---|---|
| Django 測試 | 1820 項通過 |
| 端對端測試 | 348 項通過 |
| 前端測試 | 393 項通過 |
| 前端建置、`ruff check`、`ruff format --check` | 通過 |

## 交叉審查

Codex 審查 `ad56f8a`，結果在 [#436 的留言](https://github.com/minuet878-prog/HearWell/issues/436#issuecomment-6680742105)：Standards 0 項；Spec 1 項「要修」，就是下面豁免的兩條；沒有功能錯誤。之後只合入 `main`，解了 `docs/roadmap.md` 和 `e2e/main_flow.py` 的衝突，兩邊都保留，語言香蕉區的程式沒有改。

## 驗收條件

下面的測試名稱：**規則**、**頁面**在 `screening/tests/test_speech_banana.py`，**瀏覽器**在 `e2e/main_flow.py`，**元件**在 `frontend/src/SpeechBananaApp.test.jsx`。

### 判斷規則

- [x] 1000 Hz 30 dB、2000 Hz 50 dB，第 2 群寫可能聽得到，聽力線約 35 dB。規則 `test_group_above_the_line_between_two_marks_may_be_heard`、`test_the_line_of_the_specs_example_is_about_35_db_at_1200_hz`
- [x] 聽力線剛好等於 44 dB，第 4 群寫可能不容易聽到。規則 `test_a_group_exactly_on_the_line_may_be_hard_to_hear`
- [x] 只標 500–4000 Hz，第 1、5、6 群無法估計，第 2、3、4 群有結果。規則 `test_only_500_to_4000_leaves_groups_1_5_6_without_an_estimate`
- [x] 2000 Hz 有值、4000 Hz 無反應，第 3、4 群無法確定。規則 `test_a_no_response_mark_breaks_the_line_on_both_sides`
- [x] 最高標記 4000 Hz 無反應，第 5 群無法估計。規則 `test_past_a_highest_mark_with_no_response_there_is_no_estimate`
- [x] 只有骨導，六群無法估計，沒有斜線片段。規則 `test_only_bone_marks_give_no_estimate_and_no_stretches`
- [x] 有沒有標遮蔽，結果相同。規則 `test_masking_does_not_change_the_result`
- [x] 無反應把聽力線分兩段，無反應的點不在其中，只有一個標記的段不回傳。規則 `test_a_no_response_mark_splits_the_stretches_and_is_in_neither`、`test_a_stretch_of_one_mark_is_not_returned`

### 進入與權限

- [x] 任一耳有氣導標記，有「看語言香蕉區」卡片，連到這一張。頁面 `test_card_links_to_this_audiogram_when_either_ear_has_air_marks`
- [x] 只有骨導沒有卡片。頁面 `test_no_card_with_only_bone_marks`
- [x] 沒登入轉到登入頁。頁面 `test_signed_out_goes_to_the_login_page`
- [x] 別人的聽力圖回 404。頁面 `test_someone_elses_audiogram_is_404`
- [x] 回應禁止快取，`test_standards` 通過。頁面 `test_the_response_must_not_be_cached`

### 畫面與操作

- [x] 打開時是右耳、沒選任何一群、有提示。瀏覽器 `test_card_opens_the_page_with_nothing_picked`
- [x] 點第 5 群附近的空白處選到第 5 群，框變深，圖下寫說明、例字和兩耳各一句。瀏覽器 `test_a_finger_on_empty_space_picks_the_nearest_group`
- [ ] 手指往下滑是捲動頁面，不會選到。瀏覽器 `test_a_swipe_on_the_chart_scrolls_the_page_and_picks_nothing` 通過，**實機等本人確認**
- [x] 切到左耳不換頁，選的群不變，斜線和虛線框換成左耳的。瀏覽器 `test_switching_stays_put_and_keeps_the_group`、`test_switching_ears_draws_that_ears_hatching`
- [x] 只有沒選到的「可能不容易聽到」是虛線，選到時實心深藍。瀏覽器 `test_only_hard_boxes_are_dashed_in_the_same_blue`、`test_a_picked_hard_box_is_solid_dark_blue`
- [x] 只標 500–4000 Hz，500 Hz 以下和 4000 Hz 以上沒有斜線。瀏覽器 `test_hatching_stays_over_the_line_inside_the_banana`
- [x] 手機寬度六個框不重疊、不超出圖框。瀏覽器 `test_boxes_do_not_overlap_and_stay_in_the_frame`

### 無障礙

- [x] 只用鍵盤選得到，焦點框看得到，焦點留在按的按鈕上。瀏覽器 `test_the_keyboard_alone_picks_a_group_and_focus_stays_on_the_button`、`test_the_keyboard_alone_switches_ears`
- [x] 結果會被唸出來（`role=status`），圖有文字替代說明。元件 `picking from the list darkens that box and writes the group and both ears`、`draws only the right ear's marks, with a text alternative for the chart`
- [x] 320px 寬、200% 字級沒有左右捲動，字都放大，按鈕至少 44 像素。瀏覽器兩組 `test_narrow_phone_at_double_text_size`、`test_the_words_follow_the_text_size_on_a_narrow_phone`

### 提醒與頁尾

- [x] 圖下有提醒、警報提醒、出處和查核日期，圖上沒有火警或煙霧警報。頁面 `test_the_reminders_and_source_are_in_the_page_below_the_chart`；瀏覽器 `test_the_reminders_are_under_the_chart_and_no_alarm_is_on_it`
- [x] 達到現有條件才有選配指引卡，斜線多寡不影響。頁面 `test_over_the_existing_limit_the_foot_has_the_guide_card_and_the_way_back`、`test_under_the_existing_limit_the_foot_has_only_the_way_back`、`test_how_much_is_hard_to_hear_does_not_change_the_foot`

### 字句與資料

- [x] 用本人審定的字句。規則 `test_the_six_groups_are_the_reviewed_ones`、`test_the_result_says_which_of_the_four_it_is`；頁面 `test_the_reminders_and_source_are_in_the_page_below_the_chart`
- [x] 沒有 migration，分數、分級、門檻和現有聽力圖判讀都沒變。見下面「豁免的條件」；既有的 `screening/tests/test_scoring.py`、`screening/tests/test_audiogram.py` 都通過

## 豁免的條件

交叉審查指出這兩條沒有測試斷言。本人決定豁免，因為它們是這次交付的一次性事實：「這次沒有 migration」寫成長期測試，下一張票合法新增 migration 就會誤報；綁 roadmap 字句的測試，改字就會變紅。

- **沒有 migration：** `git diff --name-only origin/main...HEAD` 沒有 migration 檔；`makemigrations --check --dry-run` 回報 No changes detected。
- **#443 的每年查核：** `docs/roadmap.md` 的每年查核條目有語言香蕉區，寫明對照的海報、改哪個檔案、改完更新哪個日期。

## 等本人確認

- [ ] 實際操作：下面的操作步驟
- [ ] 手機實測：手指滑動不會誤選、點得到想要的群
- [ ] 雅文基金會同意使用海報，並確認資料來源（#439）：**沒有同意不合併**

### 操作步驟

1. 打開一張有氣導標記的聽力圖，「接下來」有「看語言香蕉區」卡片，點進去。
2. 看到右耳、沒有選任何一群、圖下寫「點圖上的注音，看那一群。」
3. 點圖上靠近高頻的地方，選到附近那一群，框變深藍，圖下寫說明、例字和兩耳各一句。
4. 切到左耳：頁面不跳，選的群不變，斜線和虛線框換成左耳的。
5. 打開「用清單選」選一群，畫面跟點圖選到的一樣。
6. 讀圖下的提醒、警報提醒和出處，字句是不是您審定的。
7. 頁尾的「回這張聽力圖」和「看我的選配指引」卡（有達到條件時才有）都連得對。
8. 手機上：手指放在圖上往下滑，頁面捲動，沒有選到任何一群。
