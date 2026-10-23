# #297 只有可點的卡片是白卡，每個結果頁都有建議下一步

日期：2026-10-23。規格：#297；票：#298–#304。基準：`origin/main` `6d2886f`；整合分支：`feat/297-white-cards`。決策：ADR 0022、0023；本人選定：`flat-block-comparison.md`。

狀態：自動測試與自審（Standards／Spec）都已通過，**等本人實際操作驗收**。這次只改外觀和結果頁的建議下一步（沿用首頁的挑法），沒碰計分、門檻、會動資料的 migration、權限，所以不需要交叉審查。沒有操作真實資料，也沒有新增 migration。

## 測試結果（整合分支，修完自審後）

- 前端建置成功；前端測試 220 項通過。
- 單元測試 1340 項通過。
- 整套 e2e 153 項通過（`e2e.main_flow --parallel 4`）。
- 列印比對：用 `e2e/screenshots.py` 在 `origin/main` 和分支各拍一次，再用 `e2e/compare_shots.py` 比對。列印版 4 張（聽力報告、家人版報告，各 390 和 1024 寬）完全相同；有差異的 6 張都是螢幕版，原因是變平面後版面變矮。

## 做了什麼

- 全站只有可點的卡片是白卡。其他白卡都改成平面區塊，畫法照 #298 本人選定，對照表在 #297。
- 例外：
  - 登入、註冊的填寫區保留白卡。
  - 圖表繪圖區改成白底、細框、小圓角，沒有陰影。
  - 選配路線的每一站保留淡色細框。
  - 新訪客首頁的大標題維持置中，不加藍條。
- 家人溝通頁「什麼時候要馬上就醫」保留藍框和淡藍底，拿掉陰影。
- 六份問卷的結果頁都在可點卡片區最上面加了「建議您下一步」。這個框跟首頁共用 `next_step.html`，下面的卡片另成一組「其他您可以做的」。推「印報告」時，底下的「看／印聽力報告」不顯示。
- 新增 `WhiteCardRuleTest`：走遍各頁，只要有元素是白底加暖色陰影、卻不是連結，就讓測試失敗。以後新頁面不小心做成白卡也會被抓到。

## 本人審定過的實作判斷（2026-10-23）

- 結果頁框的標題用 h2（首頁仍是 h3），標題層級才不會跳級。
- SSQ12 選填卡移到「其他您可以做的」這一組。
- 首頁結果示意的標題加藍條；聽力師審定行平面、沒有線。
- 作答頁題與題的間距是 2.5rem。
- 推薦問卷卡的標題自動帶藍條。
- 帳號設定：「下載我的資料」整列可點，所以是白卡，但沒有「›」，因為它是下載、不是換頁。「刪除帳號」維持紅框。
- 左右耳結果的標題不加藍條，保留耳朵顏色的上線。
- 指引各段的間距是 1.5rem，小標題也加藍條。

## 驗收對照（#297）

勾選代表自動驗證或本次對話的檢查，不代替本人操作確認。e2e＝`e2e/main_flow.py` 的 `WhiteCardRuleTest`；unit＝`screening/tests/test_result_next_step.py`。

| # | 驗收條件 | 驗證 | 證據 |
|---|---|---|---|
| 1 | 各頁的白底＋暖色陰影元素都是連結（登入註冊填寫區除外） | ✅ 自動 | e2e `test_every_white_card_is_a_link`（`:5038`），頁面清單是 `WHITE_CARD_PAGES_*` 五組；指引各章用沒登入和登入兩種狀態各開一次 |
| 2 | 結果頁建議 1–3 平面，連結仍看得出是連結 | ✅ 自動 | e2e `test_result_advice_is_flat_with_links_that_look_like_links`（`:5077`） |
| 3 | 登入後首頁歡迎回來平面、按鈕照舊、「您還可以」仍是白卡 | ✅ 自動 | e2e `test_returning_home_welcome_is_flat_and_more_cards_stay_white`（`:5056`） |
| 4 | 沒登入首頁步驟、結果示意、審定行平面 | ✅ 自動 | e2e `test_first_visit_home_blocks_are_flat`（`:5046`） |
| 5 | 作答頁題目平面、選項白底灰框 | ✅ 自動 | e2e `test_answering_questions_are_flat_and_choices_stay_white`（`:5346`），有 JavaScript 和沒 JavaScript 兩種都測 |
| 6 | 圖表繪圖區白底、有邊框、沒有陰影、圓角較小 | ✅ 自動 | e2e `test_chart_drawing_areas_are_white_paper_with_a_small_radius`（`:5423`），涵蓋趨勢圖、IOI-HA 圖（在我的紀錄頁）、聽力圖 |
| 7 | 登入、註冊填寫區照舊是白卡 | ✅ 自動 | e2e `test_login_and_register_form_cards_stay_white_cards`（`:5376`） |
| 8 | 結果頁的建議下一步跟首頁完全相同 | ✅ 自動 | unit `test_every_result_page_suggests_what_the_home_page_does`（`:68`），六份問卷 × 五種情況 |
| 9 | 推「印報告」時底下沒有「看／印聽力報告」 | ✅ 自動 | unit `test_suggesting_the_report_leaves_out_the_report_card`（`:102`） |
| 10 | 舊作答依現在的狀況挑 | ✅ 自動 | unit `test_an_old_result_suggests_by_the_user_s_state_now`（`:117`） |
| 11 | 家人看的「您可以怎麼幫忙」外框平面、三張卡仍是白卡 | ✅ 自動 | e2e `test_family_help_is_flat_and_its_three_cards_stay_white`（`:5200`） |
| 12 | 字級 200% 沒有橫向捲動、內容不被切掉 | ✅ 自動 | e2e 四個 `..._fit_a_phone_at_double_text_size` 測試（`:5103`、`:5237`、`:5317`、`:5506`）加上 `:5366`。每個都檢查沒有橫向捲動，也檢查沒有內容被切掉（`assert_fits_uncut`）；六份問卷的結果頁都在內 |
| 13 | 列印版跟改之前一樣 | ✅ 自動＋截圖比對 | e2e `test_printed_report_parts_stay_unframed`（`:5272`）；另外用截圖比對改前改後，列印版 4 張完全相同（見上方「測試結果」） |
| 14 | 平面區塊照本人選定的做 | ✅ | `flat-block-comparison.md`；例外由本人審定，見上方和 #297 |

## 請本人操作確認

預覽：`http://localhost:8001`，從 `.claude/worktrees/white-cards` 開，跑的是整合分支，連的是本機開發資料庫。建議依序看：

1. 首頁（登入後）：歡迎回來是平面，「您還可以」裡只有卡片是白的。
2. 任一份結果頁：建議 1–3 左邊有細線；往下捲，「建議您下一步」框和首頁推的是同一項，下面是「其他您可以做的」。
3. 作答一份問卷：只有選項是白的。
4. 我的紀錄、聽力圖詳情：圖是白底的紙，作答紀錄卡片是白卡。
5. 了解 → 選配指引、任一章、家人溝通頁。
6. 帳號設定：資料列是平面，連結列是白卡。
7. 手機把字放大到 200%，再看一次首頁和結果頁。
