# #308 並列區塊上米色底、小標放大、聽力報告按問卷摺疊

日期：2026-10-24。規格：#308；票：#309–#316。基準：`origin/main` `36ae501`；整合分支：`feat/308-flat-readability`。決策：ADR 0024（修訂 ADR 0022 的平面區塊畫法）；本人在平面區塊可讀性比較頁選 A＋B＋D。

狀態：2026-10-24 本人實際操作後回覆「#308 passes acceptance」，驗收通過。自動測試與自審（Standards／Spec）都已通過。這次只改外觀與報告的顯示結構，沒碰計分、門檻、會動資料的 migration、權限，所以不需要交叉審查。分享報告露出的資料跟本人報告逐字相同（unit `test_family_report_folds_and_holds_the_same_as_the_owner_s`）。沒有操作真實資料，也沒有新增 migration。

## 測試結果（整合分支，修完自審後）

- 前端建置成功；`ruff check .` 通過。
- 單元測試 1343 項通過。
- 整套 e2e 166 項通過（`e2e.main_flow --parallel 4`）。
- 截圖比對：用 `e2e/screenshots.py` 在 `main` 和整合分支各拍 106 張，再用 `e2e/compare_shots.py` 比對。列印版 4 張（聽力報告、家人版報告，各 390 和 1024 寬）完全相同；有差異的 46 張都是螢幕版，是這次刻意改的頁面。手機寬的聽力報告從 5196px 縮到 2892px。

## 做了什麼

- 新增共用外觀：並列區塊的米色底（`#ece3d4`，沒有陰影、沒有邊框，塊裡分隔線 `#c9bba3`）、區塊標題（內文 1.35 倍）、粗體小標（內文 1.2 倍），都是標題色。
- 套用：結果頁的建議 1–3（HHIE-S、HHIA-S、THI 才有，合成一塊、條間一條線）、IOI-HA 每題、SADL 四個面向、SSQ12 分數最低的幾題、聽力圖詳情左右耳、分享設定步驟、戴與不戴比較、家人溝通頁每個主題。
- 選配指引各章不上底色，段距拉到段內的兩倍，小標放大；指引的白色小膠囊改成「圖示＋文字」清單；四份問卷作答說明的「常常／有時／從未」改成句子裡的粗體字。
- 聽力報告與分享報告的螢幕版：每份問卷收成一列摘要（名稱、最近一次日期、結果），預設全部收起，點了展開成米色塊，配戴比較收在它那份裡；重點摘要和聽力圖不收；列印全部展開。
- 報告表格：日期不斷行；放不下時（例如 320 寬，或字級 200%）每筆改成上下排的一塊，欄名當小標；螢幕閱讀器仍讀成表格。
- 白卡規則測試擴大：各頁任何白底元素都必須是可點或可操作的東西，否則測試失敗。

## 本人在實作中審定的判斷（2026-10-24）

- 米色塊裡的外框按鈕填白底（例如「取消分享」：紅字在米色上只有 3.56:1，白底上 4.53:1）。
- 家人頁緊急藍框裡「…請撥 119」那格、「建議您下一步」框裡的圖示方塊與「因為」那格：從白底改成深一階淡藍 `#d6e2f2`。
- 選配路線每站的數字圓圈：改成淡藍底、藍字，跟指引的步驟編號一樣。
- 頁首、底部導覽列、註冊頁橫幅上已完成的進度條段：白卡規則的永久例外（ADR 0012 的白色外框；細進度條不是一塊面）。

## 實作判斷（請本人驗收時留意）

- IOI-HA 題名、SADL 面向名是區塊標題，用 1.35 倍（22.5px → 24.3px）；SSQ12 最低分題原本是內文大小，用 1.2 倍（18px → 21.6px）。沒有任何標題變小。
- 報告摺疊裡，問卷原本的標題在螢幕上藏起來（摘要列已有名稱和日期），列印時照印。
- 報告表格的表頭欄名也不斷行。
- 手機 320 寬、一般字級時，報告表格也會改成上下排（四欄約需 290px，只有 248px）。
- 每份問卷的標題放在摺疊的摘要列裡（第三層標題）。有些螢幕閱讀器（例如 VoiceOver）可能不把它當標題，驗收時可以實際試一下。

## 驗收對照（#308）

勾選代表自動驗證，不代替本人操作確認。e2e＝`e2e/main_flow.py` 的 `WhiteCardRuleTest`；unit＝`screening/tests/`。

| # | 驗收條件 | 驗證 | 證據 |
|---|---|---|---|
| 1 | 各頁並列區塊是米色、沒有陰影；可點卡片仍是白卡 | ✅ 自動 | e2e `test_result_advice_is_one_tinted_block_with_links_that_look_like_links`（`:5237`）、`test_result_items_are_tinted_blocks_with_larger_titles`（`:6075`）、`test_ear_results_and_comparison_pairs_are_tinted`（`:6189`）、`test_share_steps_are_tinted_and_keep_their_buttons`（`:5583`）、`test_family_guide_topics_are_tinted_and_the_urgent_one_stands_out`（`:5463`）、`test_report_folds_by_questionnaire_closed_until_opened`（`:5670`，四份摺疊都量） |
| 2 | 米色塊上文字與連結對比 ≥4.5:1；分隔線看得到、比舊線深 | ✅ 自動 | 同上各測試的 `assert_readable_on_tint`；分隔線 `assert_lines_between` 量線對米色的對比並跟舊線 `#d9cdb9` 比 |
| 3 | 建議 1–3 同一塊米色、條間有線、沒有左線；連結看得出是連結 | ✅ 自動 | e2e `:5237` |
| 4 | 小標字級變大、標題色；卡片標題與題目字級不變 | ✅ 自動 | e2e `:5401`（指引小標）、`:5463`（家人頁技巧）、`:6075`（IOI-HA／SADL／SSQ12 標題，並斷言比改前大）、`test_card_titles_and_questions_keep_their_size`（`:6112`） |
| 5 | 指引各段沒有底色和分隔線，段距至少兩倍 | ✅ 自動 | e2e `test_guide_chapter_parts_stand_apart_with_larger_subheads`（`:5401`） |
| 6 | 報告與分享報告：重點摘要與聽力圖展開；六份問卷各一列收起的摘要列，結果正確 | ✅ 自動 | unit `test_report_parts.test_each_questionnaire_is_a_closed_fold_with_its_summary_row`（`:228`）、`test_ssq_summary_row_says_why_there_is_no_average`（`:293`），本人與家人兩邊都測 |
| 7 | 點（或 Tab 移過去按 Enter）只展開那份、米色底、比較在裡面；重新整理後全部收起 | ✅ 自動 | e2e `:5670` |
| 8 | 大段第二層、問卷第三層，沒有跳級 | ✅ 自動 | unit `test_parts_are_level_two_and_their_contents_level_three`（`:304`） |
| 9 | 部分展開時列印：全部展開，版面跟改之前一樣 | ✅ 自動＋截圖比對 | e2e `test_report_folds_open_on_paper_and_fit_a_phone_open`（`:5744`，只開一份再切列印）；列印截圖 4 張改前改後完全相同 |
| 10 | 指引膠囊變清單、作答說明是粗體字 | ✅ 自動 | e2e `test_guide_things_to_bring_are_plain_lists_with_icons`（`:5432`）、`test_answering_intros_bold_the_answers_in_the_sentence`（`:5969`） |
| 11 | IOI-HA 量尺空格透明加細框，灰格與藍點不變 | ✅ 自動 | e2e `test_ioi_ha_scale_cells_are_clear_with_a_thin_line`（`:6132`） |
| 12 | 各頁白底元素都是可點或可操作的 | ✅ 自動 | e2e `test_every_white_element_can_be_tapped`（`:5197`）；故意把米色塊改白時 10 頁失敗 |
| 13 | 一般字級時報告日期在同一行 | ✅ 自動 | e2e `test_report_table_dates_stay_on_one_line`（`:5787`） |
| 14 | 字級 200% 沒有橫向捲動、不被切掉；報告表格一筆一塊 | ✅ 自動 | e2e `test_report_table_records_stack_when_the_table_does_not_fit`（`:5809`，含無障礙樹仍是表格）、`:5744`、`:5300`、`:5518`、`:5951`、`:6224` |
| 15 | 首頁、帳號設定、選配路線跟改之前一樣 | ✅ 自動（本人核准的例外除外） | e2e `:5205`、`:5215`、`:5872`、`:5310`（選配路線數字圈依本人決定改淡藍） |

## 請本人操作確認

預覽：`http://localhost:8001`，從 `.claude/worktrees/308-integration` 開，跑的是整合分支，連的是本機開發資料庫。建議依序看：

1. 聽力報告：一進來是一排收起的摘要列，點一份展開成米色塊；按列印預覽，全部攤開、跟以前一樣。
2. 任一份 HHIE-S 結果頁：建議 1–3 是一塊米色；下面「建議您下一步」框裡只剩按鈕是白的。
3. IOI-HA 結果頁：每題一塊米色，量尺空格不是白的。
4. 了解 → 給家人看：每個主題一塊米色，技巧小標變大；緊急藍框裡 119 那格是淡藍。
5. 選配指引任一章：段落間距變大，「要帶的東西」是有圖示的清單。
6. 作答一份問卷：說明裡的「常常／有時／從未」是粗體字。
7. 手機把字放大到 200%，再看一次聽力報告（表格變成一筆一塊）。
