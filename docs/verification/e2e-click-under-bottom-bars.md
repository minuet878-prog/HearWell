# e2e 點擊偶爾在手機畫面底部被「回到頂端」或分頁列吃掉（無 issue）

日期：2026-11-17。基準：`8408621e`（main，#690 合併後）；分支：`fix/e2e-click-under-bottom-bars`。

狀態：只改 e2e 測試（`e2e/main_flow.py`），產品程式沒動。沒碰計分、分級、門檻、資料 migration、權限，**不需交叉審查**。未操作真實資料，沒有啟動開發伺服器；重現和測試都在 e2e 的臨時測試資料庫上跑。

## 問題與根本原因

CI run 43984356597（`ec910db4` 合併 commit）的 `AudiogramReadingTest.test_longest_reading_fits_a_phone_at_double_text_size`（寬 390、字放大 200%）失敗：點了「用數值輸入」之後，等了 30 秒「左耳骨導 4000 Hz」還是看不到。重跑就過。

原因（看 CI 的 trace 和截圖確認）：

1. 「用數值輸入」在頁面很下面。Playwright 點之前會先把它捲進畫面，但只捲到剛好露出來，所以它落在畫面最底下（y 736–844）。
2. 這一捲超過兩個螢幕高，「回到頂端」（`back-to-top.js`）要出現了。它下一個畫面才會出來，所以 Playwright 點之前檢查時，按鈕還不在。
3. Playwright 的「按下」和「放開」是分兩步送的。CI 慢，按鈕剛好在兩步之間冒出來，蓋住點擊位置：按下落在「用數值輸入」，放開落在「回到頂端」。
4. 按下和放開落在不同元素上，瀏覽器就把 click 給它們的共同上層 `.site-page`，結果兩邊都沒反應。折疊區沒打開，Playwright 卻照樣回報「點完了」，下一步就等到逾時。

重現：每次點擊都讓「按下」和「放開」之間停 100 毫秒（模擬慢的 CI）。這樣跑，這一題 5 次全失敗；不停的話本機 15 次全過。

同一種問題還有哪些：在暫時的測試設定下（每個點擊都停 100 毫秒，並記錄按下、放開各落在哪個元素），整套 e2e 跑一遍，另外找到兩題。它們在 CI 上還沒失敗過，但原因一樣：

| 測試 | 點的東西 | 放開時蓋在上面的 |
|---|---|---|
| `AudiogramReadingTest.test_longest_reading_fits_a_phone_at_double_text_size`（320、390 字放大） | 「用數值輸入」 | 回到頂端 |
| `FamilyAdjustingTest.test_stages_link_to_the_talking_tips_and_the_reluctant_page` | 「怎麼跟聽損的家人說話」 | 底部分頁列（往上捲 1px，`tab-bar.js` 就把分頁列滑回來） |
| `HearingAidGuideTest.test_walking_the_route_from_the_audiogram_to_the_payout` | 「儲存」，修好後換「完成了」 | 底部分頁列、回到頂端 |

產品本身應該不受影響：真人點的是已經在畫面上的東西，按下去頁面不會自己再捲，所以不會有「點的時候自己捲出回到頂端」這一步。這是 Playwright 點擊前自動捲動造成的測試時序問題（推論，沒有在真的手機上另外驗證）。

## 做法

本人選做法 A「點之前先捲到畫面中間」。

- `OnAPhone` 加 `click_mid_screen(locator, **options)`：先用 `scrollIntoView({block: 'center', behavior: 'instant'})` 把目標放到畫面中間，再點。目標離底部遠，回到頂端和分頁列出現了也蓋不到。
- 用在掃描找到的四個點擊；其他點擊照舊。
- 新增重現測試 `test_table_opens_with_a_slow_press_at_double_text_size`：按下和放開之間停 100 毫秒，點「用數值輸入」，斷言表格有打開。

## 驗收對照

| 需求 | 驗證 | 證據 |
|---|---|---|
| 找出 CI 失敗的根本原因，並穩定重現 | ✅ 自動 | 重現測試 `e2e/main_flow.py:15983`。修正前用一般 `.click(delay=100)` 失敗：`Locator expected to be visible`；改用 `click_mid_screen` 後通過 |
| 原本失敗的那題不再受影響 | ✅ 自動 | `e2e/main_flow.py:15958` 改用 `click_mid_screen` |
| 同一個原因的其他地方一併處理 | ✅ 自動 | `e2e/main_flow.py:3533`、`:3563`、`:13422`；修正後在「每次點擊停 100 毫秒」下重掃整套 e2e，沒有任何按下和放開落在不同元素上（見下方） |
| CI 上穩定通過 | ⬜ CI | 開 PR 後看 CI |

## 測試結果

- 單元測試：`Ran 2864 tests … OK`
- e2e 整套（`--parallel 4`，一般設定）：`Ran 496 tests … FAILED (failures=1)`。唯一的失敗是 `FooterOneRowTest.test_a_phone_puts_three_links_a_row_icons_over_words`（寬 390 時頁尾第一排排了 4 個連結，應為 3 個：`[2319, 2319, 2319, 2319, 2398]`）。跟這次無關：這次沒動頁尾的樣式和模板；單獨跑 3 次都失敗；main 的 CI（Linux）這題通過。推測是這台 Mac 的字型比較窄，沒有另外查證，列為後續。
- 修正後的慢速重掃（每次點擊停 100 毫秒，暫時的 `config/probe_settings.py`，已刪除）：489 個測試跑完，沒有任何按下和放開落在不同元素上；進度列有 1 個 F，因為整輪中途停掉，沒印出是哪一題，推測是上面頁尾那題。
  - 掃描卡住的 `SlidingPillTest.test_loading_bar_shows_while_the_next_side_takes_a_while` 是試驗設定自己造成的：這題故意扣住下一頁的請求、用 `no_wait_after` 點擊，點完才放行；試驗設定在每次點擊後還會讀頁面（沒有逾時），等不到被扣住的頁面，兩邊互等。單獨跑同樣卡住；讓試驗設定略過 `no_wait_after` 的點擊後，同一題在慢速下 `Ran 1 test … OK`。一般設定下這題通過。
- 重現測試：修正前（一般 `.click(delay=100)`）失敗 `Locator expected to be visible`，修正後通過。
- Ruff：`ruff check`、`ruff format --check` 都通過

## 自審

- Standards：`CODING_STANDARDS.md` 的條目都跟這次（只改 e2e）無關，沒有違規。
- Spec（無 issue，對照父任務）：根本原因有 CI trace 為證、可穩定重現；修在源頭（點之前先把目標放到畫面中間，不靠加長等待或重試）；同一原因的其他地方用整套慢速掃描找過、一併處理。
- 沒改：其他點擊沒有全面換成 `click_mid_screen`。掃描下沒有出事的地方照舊，避免改動超出需求；以後若有新的底部點擊在 CI 偶發失敗，可以照同樣方式掃描。
