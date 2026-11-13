# 自動待辦改成清單最後的一句話（#479 選 C）

日期：2026-11-14。需求：本人看首頁第 2 步卡片，覺得自動待辦「把聽力圖記到聽伴」的空圈怪，四點都勾：像單選鈕、跟上面有框的兩列不搭、灰灰的像不能用、小字「做完就會往下一站」看不懂。從[比較頁](../planning/redesign/mockup-479-auto-todo-compare.html)選 **C**，字句同日定稿（[第 2 階段拷問決定](../planning/redesign/phase-2-grill-decisions.md)設計圖選定第三列）。沒有另開 issue。

基準：`main` `a5de494`；分支：`fix/auto-todo-sentence`。

狀態：自動測試全部通過，等本人驗收。只動畫面（模板、CSS、待辦的字與排序），沒碰計分、門檻、migration、權限，**不需要交叉審查**。沒有操作真實資料。

## 改了什麼

- 自動待辦一律排在清單最後：調整 `STOP_TODOS` 裡「去找聽力師之前」「種類與價格」「配戴之後」三站的順序（其他站本來就在最後）。清單仍照定義順序列出，沒有加排序邏輯。
- 畫面：前面有手動待辦時隔一條細線；空圈換成藍色箭頭（做完換成勾）；主句深色粗體，做完改成一般字重。沒有框、沒有白底（白底只給可以按的東西，ADR 0022）。
- 字：主句＝待辦原字＋結尾（一站的「，就會往下一站」、第 4 步的「，這一步就完成」、開始配戴日期不加）；小字三種：「不用自己勾，網站會知道」「不用自己勾，做完網站會幫您打勾」「網站已幫您打勾」。待辦本身的字沒改。
- 螢幕閱讀器照舊唸「，未完成。」「，已完成。」（#478 驗收 28），插在主句和小字之間。
- 文件：ADR 0047 加「後續」一段、GLOSSARY「待辦」補一句、第 2 階段拷問決定加一列。

## 自審（`/mattpocock-skills:code-review`，基準 `main`）

- 規範軸：沒有硬性違規。判斷項「`then` 名稱看不出意思」→ 已改成 `outcome`；配戴日期註解過時 → 已改。其餘（全形逗號放在常數、`then`／`hint` 成對、測試寫死 SVG 路徑）判斷為可不改。
- 規格軸：
  - **要修，已修**：第一版拿掉了螢幕閱讀器唸的「已完成／未完成」，違反 #478 驗收 28 → 補回，順便讓主句和小字之間有「。」停頓。
  - 測試名稱註解過時 → 已改。
  - 補 e2e 斷言：箭頭是主色藍、主句粗體。
  - 沒有補的（說明原因）：「只有自動待辦、沒有細線」（等待核定公文那站）沒有畫面測試，靠 CSS `.todo-manual ~ .todo-auto`，要在 e2e 多建一組資料才走得到那站；開始配戴日期「沒做完」只在資料層驗證，因為要走到配戴之後那站就一定填了日期，頁面上看不到沒做完的樣子。

## 測試結果（第二個 commit 之後）

- `python manage.py test --settings=config.test_settings`（`--parallel 4`）：2405 項通過。
- `screening.tests.test_journey_todos`：75 項通過（先改測試看到 5 項失敗，再改程式轉綠）。
- `npm test --prefix frontend` 通過；`npm run build --prefix frontend` 成功。
- `ruff check .`、`ruff format --check .` 通過。
- 整套 e2e（`e2e.main_flow --parallel 4`）：第一個 commit 時 422 項通過；第二個 commit 後再跑一次，422 項通過。

## 對照本人選定的 C

測試檔＝`screening/tests/test_journey_todos.py`（下稱 `t`）、`e2e/main_flow.py`（下稱 `e`）。

| # | 要點 | 驗證 | 證據 |
|---|---|---|---|
| 1 | 自動待辦一律在清單最後 | ✅ 自動 | `t` `test_every_list_puts_its_automatic_to_dos_last`（每份定義都檢查）；頁面上 `test_before_reading_before_you_go_its_chapter_waits_after_an_arrow` 的 `listed(card)[-1]` |
| 2 | 沒做完是藍色箭頭、做完是勾，不畫可以勾的框 | ✅ 自動 | `t` 同上一項的 `ARROW`／`TICK` 斷言、`test_a_done_automatic_to_do_is_a_tick_saying_so`；`e` `test_to_dos_sit_under_the_button_and_fit_a_phone_at_double_text_size`：`.todo-mark` 沒有框、顏色 `rgb(31, 78, 140)` |
| 3 | 前面有手動待辦時隔一條細線，沒有框、沒有白底 | ✅ 自動 | `e` 同上：上框 1px、左框 0、背景透明 |
| 4 | 一站的主句「……，就會往下一站」、第 4 步「……，這一步就完成」 | ✅ 自動 | `t` `test_each_to_do_is_read_by_its_words`、`test_step_4_s_own_automatic_to_do_says_it_finishes_the_step` |
| 5 | 三種小字 | ✅ 自動 | `t` `test_only_a_stop_s_whole_end_says_the_route_moves_on`（「網站會知道」「做完網站會幫您打勾」）、`test_a_done_automatic_to_do_is_a_tick_saying_so`（「網站已幫您打勾」） |
| 6 | 主句粗體 | ✅ 自動 | `e` 同 #2：`.todo-sentence` 字重 700 |
| 7 | 螢幕閱讀器唸出未完成／已完成，自動待辦不能聚焦操作 | ✅ 自動 | `t` #4、#5 的字句斷言含「，未完成。」「，已完成。」；`test_a_manual_to_do_is_a_checkbox_saying_its_state` 裡檢查自動待辦沒有按鈕、連結、表單、tabindex、role 的斷言沒改、照舊通過 |
| 8 | 手機 390px、200% 字級不橫向捲動 | ✅ 自動 | `e` 同 #2 的 `assert_fits_a_phone_at_double_text_size` |

## 預覽（本機 8001）

首頁第 2 步：兩列白框方框，下面細線、藍色箭頭、「把聽力圖記到聽伴，就會往下一站」＋「不用自己勾，網站會知道」，跟比較頁的 C 一樣。手機 375px 沒有橫向捲動，箭頭和方框對齊，字也和上面兩列的字對齊。Console 沒有錯誤。

## 本人實際操作

- [ ] 首頁第 2 步「要做的事」：自動待辦在最下面，看起來不像可以按的東西、字看得懂
- [ ] 我的選配指引「您在這裡」那張卡片，看到同一份清單
