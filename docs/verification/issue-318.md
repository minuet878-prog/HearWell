# #318 選配指引的每一段放進段落框

日期：2026-10-24。規格：#318；票：#319–#321。基準：`main` `e940c48`；整合分支：`feat/318-guide-section-boxes`。決策：ADR 0025（修訂 ADR 0024「指引不上底色」那一條）；本人在指引風格比較頁選 M（標題列框），拷問 Q1–Q9。

狀態：2026-10-24 本人實際操作後回覆「驗收通過」。自動測試與自審（Standards／Spec）都已通過。這次只改外觀與兩個段落標題，沒碰計分、門檻、會動資料的 migration、權限，所以不需要交叉審查。沒有操作真實資料，也沒有新增 migration。

## 測試結果（整合分支，驗收時的改動之後）

- 前端建置成功；`ruff check .` 通過。
- 單元測試 1347 項通過。
- 整套 e2e 171 項通過（`e2e.main_flow --parallel 4`）。
- 沒有做改前改後的截圖比對：列印樣子這次本來就會變（多了灰色細框），由列印 e2e 斷言驗證。

## 做了什麼

- 新增共用外觀：段落框（框身 `#f5efe5`、頂端標題列 `#e0d2b8`，沒有陰影、沒有外框）。標題在標題列裡，用內文 1.35 倍、標題色、粗體，沒有藍色左線。框裡原本的淡線（重點清單分隔線、步驟連接線、路線連接線）自動換成深米色 `#c9bba3`。
- 套用：指引六章有標題的每一段、章尾「看完了嗎？／已記下」；我的選配指引的「問卷結果」「聽力圖」「要不要找聽力師評估」「身障鑑定門檻」，以及選配路線整條。
- 框外：章名、導言、單獨的藍色提醒框、章尾資料來源與查核日期、我的選配指引上方說明與按鈕、「看我的路線」。
- 新增兩個段落標題：「配戴之後」的「剛開始戴助聽器」、「二十五號表」的「誰要做、怎麼做」。
- 選配路線：各站拿掉細框；目前這一站保留藍框淡藍底；估算未達門檻、不適用的站原本的白色小標記改成標題列的深米色。跳到路線標題時，標題列裡有 3px 藍色焦點框。
- 列印：段落框不印米色，印成灰色細框，標題加一條底線。

## 本人在驗收時審定的改動（2026-10-24）

- 選配路線各站：從比較截圖選 G，目前這一站以外的每一站都是並列區塊的米色底（`#ece3d4`），沒有外框。ADR 0025 與 GLOSSARY 已一併更新。#318 第 4 條「目前這一站以外的站沒有邊框」仍成立，多了米色底。
- 段內緊貼金額的「來源：…」小字（九號表、身障鑑定）留在段落框裡；規格說的「資料來源在框外」指章尾的資料來源。
- 橫條（四頻平均、雙耳障礙比率）黑線左邊的白縫：#260 就有，不是這次造成的，另開任務處理，不放進這個 PR。

## 實作判斷（請本人留意）

- 段落標題統一用 1.35 倍內文：手機上比原本的段落標題大一點，桌機上比原本稍小。
- 九號表步驟之間的連接線也換成深米色，否則在米色框裡看不到。
- 跳到路線標題的焦點框寫在 `:focus`：用滑鼠點「看我的路線」後也會出現，這樣才符合「焦點在標題上且看得到焦點框」。
- 規格寫「還沒到的站的淺灰底」是筆誤：那個淺灰底其實屬於「估算未達門檻」的站。實作以程式的意思為準。
- 列印時底部導覽列也會印出來，是原本就有的狀況，這次沒動。

## 驗收對照（#318）

勾選代表自動驗證，本人已實際操作確認。e2e＝`e2e/main_flow.py`（`WhiteCardRuleTest` 從 `:4844` 起、`HearingAidGuideTest` 從 `:1945` 起）；unit＝`screening/tests/`。

| # | 驗收條件 | 驗證 | 證據 |
|---|---|---|---|
| 1 | 六章每個有標題的段落是段落框，章名、導言、單獨提醒、資料來源在框外 | ✅ 自動 | e2e `test_guide_chapter_parts_are_section_boxes_with_their_links`（`:5540`，登入與沒登入都跑） |
| 2 | 我的選配指引四段是段落框，橫條、連結、按鈕、「怎麼算的」照舊；「看我的路線」在框外 | ✅ 自動 | e2e `test_guide_parts_and_route_are_section_boxes_with_their_links`（`:5419`） |
| 3 | 沒登入、有問卷沒聽力圖：說明與按鈕在框外；聽力圖段與路線是段落框 | ✅ 自動 | e2e `test_guide_note_and_buttons_stay_outside_and_the_audiogram_part_is_boxed`（`:5659`）、`test_guide_route_is_one_section_box_signed_out_and_with_every_kind_of_stop`（`:5517`） |
| 4 | 路線一個段落框；其他站沒有邊框（本人加選：米色底）；目前這一站藍框；連接線看得到；小標記不是白色 | ✅ 自動 | e2e `assert_route_box`（`:5459` 起），由 `:5419`、`:5517` 呼叫 |
| 5 | 按「看我的路線」跳到路線標題、焦點框看得到 | ✅ 自動 | e2e `test_jump_to_the_route_lands_on_its_heading_with_focus`（`:2519`） |
| 6 | 框上文字、連結、標題對比 ≥4.5:1；框裡分隔線看得到 | ✅ 自動 | e2e `assert_section_box`（`:5184` 起）、`test_guide_chapter_boxes_stand_apart_with_subheads_and_visible_lines`（`:5592`）；路線各站 `assert_readable_on_tint` |
| 7 | 段落標題 ≥1.35 倍、標題色、粗體、沒有藍色左線；章名有藍色左線 | ✅ 自動 | e2e `assert_section_box` 裡的 `assert_block_title`；`:5540`（章名藍線） |
| 8 | 配戴之後、二十五號表開頭清單在新標題的段落框裡，其他文字不變 | ✅ 自動 | unit `test_guide_form_25.test_the_four_points_are_a_titled_part`（`:177`）、`test_the_five_facts_are_a_titled_part`（`:94`）；e2e `:5540` |
| 9 | 章尾「看完了嗎？」與「已記下」在段落框裡，按鈕與連結照舊 | ✅ 自動 | e2e `:5540`（章尾部分） |
| 10 | 下拉框、縣市選單與查詢照舊能用；九號表錨點落在標題上 | ✅ 自動 | e2e `test_pages_fit_a_phone_at_double_text_size`（`:2372`，打開每個下拉框）、`test_route_from_home_card_to_form_9`（`:2012`）、`test_form_9_anchors_jump_to_their_sections`（`:2539`）；unit `test_guide_form_9.test_reapply_and_without_certificate_anchors_land_on_their_headings`（`:122`） |
| 11 | 章名第一層、段落第二層，沒有跳級 | ✅ 自動 | unit `test_guide.test_every_chapter_titles_its_parts_one_level_below_without_skipping`（`:171`）、`test_guide_summary.test_my_guide_titles_its_parts_one_level_below_without_skipping`（`:318`） |
| 12 | 列印：不印米色，灰色細框，標題加底線 | ✅ 自動 | e2e `test_printed_guide_chapter_boxes_are_grey_frames`（`:5624`）、`test_printed_guide_status_boxes_are_grey_frames`（`:5638`，含路線） |
| 13 | 手機寬度、字級 200%：沒有橫向捲動、不被切掉，長標題在標題列裡換行 | ✅ 自動 | e2e `test_guide_part_titles_wrap_in_their_bars_at_double_text_size`（`:5690`，我的選配指引與六章逐頁）、`test_learn_pages_fit_a_phone_at_double_text_size`（`:5861`） |
| 14 | 白卡規則頁面（含指引首頁、六章與兩種新狀態）的白底元素都可點或可操作 | ✅ 自動 | e2e `test_every_white_element_can_be_tapped`（`:5305`） |
| 15 | 首頁、家人溝通頁、結果頁、聽力報告不變 | ✅ 自動 | 沿用現有 e2e：`test_home_and_result_pages_fit_a_phone_at_double_text_size`（`:5408`）、`test_family_guide_topics_are_tinted_and_the_urgent_one_stands_out`（`:5750`），以及整套 e2e 171 項通過 |

## 本人操作確認

預覽：`http://localhost:8001`，從 `.claude/worktrees/318-integration` 開，跑的是整合分支，連的是本機開發資料庫。本人看過指引六章、我的選配指引（狀況段落與選配路線）、列印預覽與 200% 字級，驗收時提出的路線分隔方式已改成 G，2026-10-24 回覆驗收通過。
