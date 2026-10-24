# #326 全站按鈕與控制項的互動回饋

日期：2026-10-24。規格：#326；票：#328–#337。基準：`origin/main` `4431f97`；整合分支：`feat/326-button-feedback`（PR #349）。決策：ADR 0028（補充 ADR 0006；ADR 0007 指向它）。項目來自本人在[互動盤點示意頁](https://claude.ai/artifact/JEwiGtMcQRn3Roenf3oAHJ)挑的 21 項。

狀態：2026-10-24 本人在 worktree 的 8001 預覽實際操作後回覆「驗收通過」。自動測試與自審（Standards／Spec）都已通過，自審找到的 12 項已修完或經本人決定保留。這次 #336 在 session 存「剛完成的站」、#337 只讀目前帳號的草稿，依 AGENTS.md 應做交叉審查；2026-10-24 本人決定這次略過交叉審查。沒有操作真實資料，也沒有新增 migration。

## 測試結果（整合分支，CI 抓到「慢的時候藥丸淡出」並修正之後）

- `ruff check .`、`ruff format --check .` 通過；前端建置成功。
- 單元測試 1393 項通過（`--parallel 4`）。
- 前端測試 319 項通過。
- 整套 e2e 214 項通過（`e2e.main_flow --parallel 4`）；`SlidingPillTest` 另外連跑 4 次都通過。

## 做了什麼

- **只變色的按下回饋**（#328）：問卷分頁、「問卷｜聽力圖」、「右耳｜左耳」、底部導覽、文字連結、作答選項，手指按下就變色、位置不動；選中的答案深藍底白字加勾；打開的下拉框左邊藍邊。
- **作答頁**（#329、#330、#331）：上一題／下一題／送出有方向圖示；沒選答案按下去提示「請先選一個答案」；送出成功變綠「✓ 已送出」停 0.6 秒；選答案時進度格填入、旁邊「✓ 已儲存」；換題時題目淡入。聽力圖存檔成功「✓ 已存檔」。
- **小元件**（#332、#333）：複製連結按鈕本身變「✓ 已複製」；密碼顯示鈕加眼睛；註冊出生年、確認密碼填對出現綠勾；遮蔽改成開關。
- **頁面**（#334、#335、#336、#337）：二選一切換時藍色藥丸滑過去；長頁面「回到頂端」；選配路線回答完成一站時打勾；首頁與篩檢分頁提示「接著答」。

## 本人決定與實作判斷（請本人留意）

- **綠色**：「剛完成的那一刻」（已送出、已存檔、已複製、完成一站）用成功綠填滿，寫進 ADR 0028 當 ADR 0007 的例外；`CODING_STANDARDS.md` 第 23 條也補了這個例外。
- **進度格**在選答案的當下填入（不是按下一題時），#326 驗收 12 的文字已改。
- **註冊紅框**：出生年改對時收掉紅框和錯誤字；確認密碼只收「兩次密碼不一致」那句，密碼強度的錯誤和紅框留著（依錯誤代碼辨識，不比對文字）。
- **回到頂端**用灰色陰影，不用卡片的暖色陰影（ADR 0022：白卡＝可點）。
- **遮蔽開關**拿掉舊的「（△ □ [ ]）」提示，補上滑過、按下與鍵盤焦點樣式（原本沒有焦點外圈）。
- **二選一按下**用深一級的淺藍 `brand-soft-deep`，因為底軌本來就是淺藍。
- **路線綠勾**只在回答完轉回的那一頁出現，重新整理後回到一般已完成的樣子。
- **接著答**的問卷名稱寫成「主題（代碼）」；首頁只讀草稿、不刪別人的草稿（刪除仍只在打開作答頁時）。
- **藥丸滑動**：Safari 有沒有 `pageswap` 事件沒能核實；如果沒有，從有藥丸的頁面去別頁時藥丸可能淡出。請用 iPhone 實機看。
- **慢的時候不滑**（PR 開出後 CI 抓到，本人決定）：新頁畫第一個畫面時藥丸還沒解析好（手機或網路慢），原本只剩舊藥丸淡出；現在 `switch-reveal.js` 在 `<head>` 取消這次轉場，直接換頁。MDN 建議的 `<link rel="expect" blocking="render">` 實測 Chromium 156 不生效，所以沒用。
- **已知、沒修**：聽力圖比較頁的選擇卡在 200% 字級、320px 寬時超出外框右側約 21px（原本就有，加勾後更明顯），建議另開票。

## 驗收對照（#326）

勾選代表自動驗證，本人已實際操作確認。e2e＝`e2e/main_flow.py`。

| # | 驗收條件 | 驗證 | 證據 |
|---|---|---|---|
| 1 | A2 分頁、二選一滑過／按住變色，位置大小不變 | ✅ 自動 | e2e `ColourOnlyFeedbackTest.test_tabs_and_switches_change_colour_when_hovered_or_pressed` |
| 2 | A3 底部導覽按住藥丸變色 | ✅ 自動 | e2e `ColourOnlyFeedbackTest.test_navigation_items_change_colour_when_pressed` |
| 3 | A4 文字連結滑過底線變粗、按住淺藍底 | ✅ 自動 | e2e `ColourOnlyFeedbackTest.test_text_links_thicken_when_hovered_and_tint_when_pressed` |
| 4 | A6 方向圖示，名稱不變 | ✅ 自動 | `AnswerApp.test.jsx`（圖示位置與 aria-hidden）；e2e `AnswerIconsHintTest.test_icons_and_the_choose_first_hint`（箭頭左右方向） |
| 5 | B1 作答頁「✓ 已送出」、0.6 秒後換頁 | ✅ 自動 | `AnswerApp.test.jsx`（假計時器 599／600 毫秒）；e2e `SentMomentTest.test_answering_shows_sent_then_opens_the_result` |
| 6 | B1 聽力圖頁「✓ 已存檔」 | ✅ 自動 | `AudiogramApp.test.jsx` |
| 7 | 失敗、過期不出現綠色 | ✅ 自動 | `AnswerApp.test.jsx`（五種錯誤）、`AudiogramApp.test.jsx`（四種錯誤） |
| 8 | B3 複製後「✓ 已複製」2 秒、每次重唸 | ✅ 自動 | `copy-link.test.js`；e2e `CopyPasswordRegisterFeedbackTest.test_copy_button_turns_green_with_a_tick_then_back` |
| 9 | B4 存成功才「✓ 已儲存」 | ✅ 自動 | `draft.test.js`、`AnswerApp.test.jsx`；e2e `ProgressSavedTest.test_saved_shows_beside_the_progress_for_a_moment`、`test_no_saved_when_the_draft_cannot_be_kept` |
| 10 | C1 選中深藍白字加勾，200% 字級不溢出 | ✅ 自動 | e2e `ColourOnlyFeedbackTest.test_chosen_answers_turn_dark_blue_with_a_tick`、`test_chosen_answer_fits_a_phone_at_double_text_size` |
| 11 | C2 按住選項變淺藍 | ✅ 自動 | e2e `ColourOnlyFeedbackTest.test_answers_turn_light_blue_while_pressed` |
| 12 | C3 只有新答的那格填入 | ✅ 自動 | `AnswerApp.test.jsx`；e2e `ProgressSavedTest.test_new_segment_fills_and_another_question_fades_in` |
| 13 | C4 換題淡入、焦點在題目 | ✅ 自動 | `AnswerApp.test.jsx`；e2e `ProgressSavedTest.test_new_segment_fills_and_another_question_fades_in` |
| 14 | C5 未作答按下一題／送出出現提示、焦點回題目 | ✅ 自動 | `AnswerApp.test.jsx`（下一題、送出、SSQ12 分數題）；e2e `AnswerIconsHintTest.test_icons_and_the_choose_first_hint` |
| 15 | D1 打開的下拉框藍邊、標題列淺藍 | ✅ 自動 | e2e `ColourOnlyFeedbackTest.test_open_dropdowns_get_a_blue_edge_and_keep_their_bar_tinted` |
| 16 | D3 藥丸滑動；不支援時照常換頁；其他換頁不轉場；慢的時候直接換頁、不淡出 | ✅ 自動 | e2e `SlidingPillTest`（七項，含 `test_browser_without_view_transitions_just_changes_page`、`test_no_other_change_of_page_transitions`、`test_slow_page_changes_page_without_fading_the_pill`：CPU 慢 6 倍，拿掉修正時這項會失敗）；`switch-slide.test.js`、`switch-reveal.test.js` |
| 17 | D4 遮蔽開關，滑鼠與空白鍵切換，唸成開關 | ✅ 自動 | e2e `MaskingSwitchTest.test_mouse_and_space_bar_switch_masking`；`AudiogramApp.test.jsx` |
| 18 | D5 密碼眼睛圖示 | ✅ 自動 | `password-toggle.test.js`；e2e `CopyPasswordRegisterFeedbackTest.test_show_password_has_an_open_then_a_slashed_eye` |
| 19 | D6 出生年、確認密碼綠勾，密碼欄沒有 | ✅ 自動 | `register-checks.test.js`、`test_accounts.py`；e2e `CopyPasswordRegisterFeedbackTest` 的三項 register 測試 |
| 20 | E1 回到頂端：四種長頁面、一個畫面後出現、回頁首焦點在標題、手機不擋導覽 | ✅ 自動 | `test_back_to_top.py`、`back-to-top.test.js`；e2e `BackToTopTest`（四項） |
| 21 | E5 剛完成那站打勾一次；重新整理、修改、章節頁、不適用都不播 | ✅ 自動 | `test_route_checkmark.py`（十一項，含登出與換帳號不殘留）；e2e `RouteCheckmarkTest` |
| 22 | E7 接著答只給目前帳號、未過期的草稿 | ✅ 自動 | `continue-notice.test.js`（別人帳號、過期、儲存丟錯）、`test_continue_notice.py`；e2e `ContinueNoticeTest` |
| 23 | 減少動態效果時不動 | ✅ 自動 | e2e `ProgressSavedTest.test_reduced_motion_neither_fills_nor_fades`、`SlidingPillTest.test_reduced_motion_changes_page_without_sliding`、`MaskingSwitchTest.test_knob_slides_only_without_reduced_motion`、`BackToTopTest.test_scrolls_smoothly_or_jumps_with_reduced_motion`、`RouteCheckmarkTest` |

## 請本人實際操作

建議用手機（iPhone 優先）：

1. 底部導覽、我的紀錄的問卷分頁、「問卷｜聽力圖」：手指按下時有沒有變色。
2. 「問卷｜聽力圖」與比較頁「右耳｜左耳」：藥丸有沒有滑過去；從這兩頁去首頁時藥丸有沒有淡出。
3. 做一份問卷：選答案時進度格與「✓ 已儲存」、換題淡入、沒選就按下一題的提示、送出後的綠色「✓ 已送出」。
4. 答到一半離開，回首頁看「接著答」。
5. 聽力圖輸入頁的遮蔽開關、存檔後「✓ 已存檔」。
6. 分享報告頁複製連結；註冊頁出生年與確認密碼綠勾。
7. 選配指引：回答「您在這裡」那站的問題後的打勾；長頁面的「回到頂端」。
