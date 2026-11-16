# 可讀性第 2 批：九號表、家人專區、說話方法（小改動，無 issue）

日期：2026-11-16。基準：`feat/readability-batch1`（`9bbce269`，PR #572 還沒合併，這個分支疊在它上面）；分支：`feat/readability-batch2`。依據：[可讀性檢查](../planning/readability-review-2026-11-16.md)「第 2 批選定」「第 2 批定稿的字」、[第 2 批設計圖](../planning/redesign/mockup-readability-batch2.html)。

狀態：本人實際操作驗收通過（2026-11-16）。

- 本人在設計圖選定：問卷分組 A、九號表 A、家人專區 A、說話方法 A（2026-11-16）。問卷分組 11/14 已上線，本人決定維持現狀，這次不做。
- 本人定稿的字：家人專區開頭「想幫聽力不好的家人，可以從這裡開始。」；六條提醒的摺疊標題保留「陪伴配戴助聽器」；六條提醒先原文搬過去；九號表收起來的那一行「看每一步的說明」。
- 走小改動流程（跳過拷問、規格、拆票）。不需要交叉審查：沒改計分、分級、門檻，沒有 migration，沒碰權限。
- 沒有操作真實資料。測試在臨時測試資料庫上。

## 行為

| 項目 | 現在 |
|---|---|
| 九號表「要怎麼辦？」 | 六個步驟的編號、標題、時限一直看得到；每一步的說明要按清單上面的「看每一步的說明」才顯示，出處在清單下面一直看得到。「先拿到核定通知再買，沒核定就先買的不補助。」只在第 4 步裡出現一次。原本標題下那一句提醒拿掉。第一張重點卡的小字縮成「沒核定就先買的不補助。」（大字「先核定，再買」不變）。時限標籤不再對螢幕閱讀器隱藏（說明收起時它就是時限）。從選配路線跳到這一段、或沒有 JavaScript 時，一開始就是打開的 |
| 家人專區首頁 | 開頭改成一句「想幫聽力不好的家人，可以從這裡開始。」；只剩五個可以點進去的列，「陪伴配戴助聽器」那一列拿掉 |
| 助聽器頁「陪長輩適應」 | 三個階段選項下面多一個摺疊「陪伴配戴助聽器」，六條提醒原文搬過來；出處的兩筆也跟著搬到這一頁的出處 |
| 分享報告 | 「陪伴配戴助聽器」的連結改跳到助聽器頁的這個摺疊，跳過去時打開、亮框 |
| 怎麼跟他說話 | 九個方法的線條圖縮成 96px 放在左邊、字在右邊（標題、說明不改），側排時線條稍細；字放大到清單不到 15rem 寬時（例如 200%），圖回到字上面 |

跟設計圖不一樣的地方：

- 九號表：設計圖點開後是另一份完整清單；實作只用一份清單，說明藏在每一步裡、點開就出現，避免同樣的步驟出現兩次、跳轉時對到藏起來的那一份。
- 九號表：「看每一步的說明」放在清單**上面**，設計圖畫在下面。自審發現放下面時，用螢幕閱讀器的人按了之後，新出現的說明在焦點上方，往下讀聽不到；放上面，按了往下讀就是展開的步驟。出處原本在摺疊裡，改成清單下面一直顯示。**驗收時請本人確認這個位置**，想照設計圖放下面可以改回。
- 舊的 `/family#aid-title`（書籤或舊訊息裡）會落在家人專區首頁頂端，因為那一段搬走了；分享報告的連結是即時產生的，已經改好。
- 助聽器頁上方的「陪長輩適應」連結，點了也會打開這個摺疊：選配指引原本就是「跳到哪一段，打開那一段的摺疊」，判斷合理，沒改。
- 助聽器頁原本的出處每筆都寫更新日期；搬過來的兩筆照 2026-10-17 審定的寫法，沒有日期。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。

| 需求 | 驗證 | 證據 |
|---|---|---|
| 九號表整章文字照順序，提醒在第 4 步的說明之後 | ✅ 自動 | `screening/tests/test_guide_form_9.py:115` |
| 一份清單、六步、每一步一段說明、摺疊在清單後面且含出處、提醒只出現一次且在第 4 步、沒有 tip-box | ✅ 自動 | `screening/tests/test_guide_form_9.py:195` |
| 時限標籤：六步的標籤照舊，五個都不再 aria-hidden | ✅ 自動 | `screening/tests/test_guide_form_9.py:219`；e2e 五個標籤都看得到 `e2e/main_flow.py:14431` |
| 提醒和二十五號表連結在「要怎麼辦？」裡、出處緊跟著 | ✅ 自動 | `screening/tests/test_guide_form_9.py:182`、`:135` |
| 第一張重點卡「先核定，再買 沒核定就先買的不補助。」 | ✅ 自動 | `screening/tests/test_guide_redesign.py:172` |
| 一進來看得到六個標題、時限、第 4 步提醒，說明看不到；點「看每一步的說明」後看得到 | ✅ 自動 | `e2e/main_flow.py:14431` `test_form_9_steps_in_sight_their_words_behind_the_fold` |
| 從選配路線跳到 #steps-title 時打開、看得到第 2 步的說明；沒有 JavaScript 時全部顯示 | ✅ 自動 | `e2e/main_flow.py:14408` `test_a_jump_lands_on_its_part_open`（改用說明文字，標題收起時本來就看得到） |
| 程式收合摺疊之前，說明不會先閃出來 | ✅ 自動 | `e2e/main_flow.py:14462` `test_form_9_steps_words_do_not_flash_before_the_folds_settle`（擋住 guide.js，等待期間說明看不到） |
| 審定字句的防護：九號表的字改動經本人在設計圖選定，更新檢查碼 | ✅ 自動 | `screening/tests/test_family_zone.py:554` `ReviewedPagesTests` |
| 家人專區首頁：一句開頭、舊開頭已拿掉、五個連結列、沒有原地展開的列 | ✅ 自動 | `screening/tests/test_family_zone.py:150`、`:187`；`screening/tests/test_family_guide.py:178` |
| 家人專區首頁沒有 aid-title，也不再載入摺疊用的程式 | ✅ 自動 | `screening/tests/test_family_zone.py:187`；`screening/tests/test_family_redesign.py:458` |
| 六條提醒逐字搬到助聽器頁「陪長輩適應」的摺疊、標題「陪伴配戴助聽器」、在三個階段之後、問卷那一行之前 | ✅ 自動 | `screening/tests/test_family_redesign.py:172`；`screening/tests/test_family_adjusting.py:155`；`screening/tests/test_family_guide.py:195` |
| 第四條提醒仍連到「怎麼跟他說話」 | ✅ 自動 | `screening/tests/test_family_redesign.py:440` |
| 兩筆出處搬到助聽器頁、家人專區不再列 | ✅ 自動 | `screening/tests/test_family_guide.py:161`；`screening/tests/test_family_redesign.py:227`；`screening/tests/test_family_hearing_aids.py:204`（整份出處清單） |
| 分享報告的連結指到 `/family/hearing-aids#aid-title` | ✅ 自動 | `screening/tests/test_shared_report_highlights.py:186` |
| 從分享報告點過去：打開、看得到提醒；直接開助聽器頁時收著；沒有 JavaScript 時顯示 | ✅ 自動 | `e2e/main_flow.py:14576` `test_a_jump_to_the_aid_row_opens_it` |
| 從分享報告點過去會亮框 | ✅ 自動 | `e2e/main_flow.py:9937` `test_family_topic_lights_from_the_shared_report` |
| 320px、200% 字級：家人專區、助聽器頁（摺疊打開）不超出 | ✅ 自動 | `e2e/main_flow.py:14525` |
| 說話方法：九個方法的字照舊 | ✅ 自動 | `screening/tests/test_family_redesign.py:81` |
| 說話方法：320、390 寬圖在左、寬約 96px、字在右，線條從 2.4 調細成 1.8 | ✅ 自動 | `e2e/main_flow.py:10454` `TalkTipsSideBySideTest` |
| 說話方法：200% 字級圖回到字上面、線條恢復 2.4、不超出 | ✅ 自動 | 同上 `test_double_text_size_puts_the_drawing_back_over_the_words` |
| 實際走起來 | ✅ 本人 | 見下方「人工驗收」 |

## 測試與審查

- 單元測試 `manage.py test --settings=config.test_settings --parallel 4`：2609 項全過。
- 前端 `npm test --prefix frontend`：564 項全過。
- 端對端（先 `npm run build --prefix frontend`）`e2e.main_flow --parallel 4`：440 項全過。
- `ruff check .`、`ruff format --check .`：全過。

自審（`/mattpocock-skills:code-review`，基準 `feat/readability-batch1`，兩個代理分別看規範與規格，只看 diff、設計圖和檢查文件）：

- Standards：1 項硬性——第 4 步提醒的 `.step-warning` 只用一次，規範第 21 條要直接寫 Tailwind，已改。判斷題改了 4 項：家人專區出處測試只剩一個元素、排序檢查驗不到東西（拿掉）；只剩一個元素的迴圈；新測試在迴圈裡重複抓同一頁；`family_zone.py` 註解寫「這一頁」看不出是哪頁。沒改：六條提醒寫在模板、出處在 Python（照原本寫法搬過來）。
- Spec：三項都有做到、沒有範圍外的改動。改了：說明會先閃出來再收起（兩個代理都抓到，已讓說明在等待期間也藏著，並補 e2e）；螢幕閱讀器按「看每一步的說明」後聽不到新內容（移到清單上面）。補了 4 個證據：五個時限標籤、跳轉用說明文字驗、首頁舊開頭已拿掉、線條變細。沒改：助聽器頁上方「陪長輩適應」連結也會打開摺疊（見上方「跟設計圖不一樣」）。
- 第一次完整跑時，`test_family_hearing_aids` 逐筆列出助聽器頁出處的測試沒跟著改（當時只搜了「陪伴配戴助聽器」「aid-title」，沒搜出處清單），已補上那兩筆。
- 審定字句的防護 `ReviewedPagesTests`：九號表的三句字（重點卡小字、第 4 步提醒、「看每一步的說明」）是本人在設計圖選定的，照 #467 的前例更新檢查碼並在測試說明寫明。**驗收時請本人再確認這三句。**

改了的既有測試（刻意改變內容或位置，不是行為壞掉）：

- `screening/tests/test_guide_form_9.py`、`test_guide_redesign.py`：九號表的新結構與縮短的兩句。
- `screening/tests/test_family_zone.py`：首頁開頭（原本那句改名 `TALK_INTRO` 留給說話方法頁）、首頁沒有摺疊列、審定頁面的檢查碼。
- `screening/tests/test_family_guide.py`、`test_family_redesign.py`、`test_family_adjusting.py`、`test_shared_report_highlights.py`、`test_family_hearing_aids.py`：「陪伴配戴助聽器」和它的出處改在助聽器頁。
- `e2e/main_flow.py`：家人專區的 6 個類別跟著搬家（列數、連結、跳轉的網址）。

## 人工驗收

8001 開在這個分支的 worktree（前端已建置）：

```bash
cd /Users/huangweizhe/HearWell/.claude/worktrees/readability-batch2 && /Users/huangweizhe/HearWell/py313/bin/python manage.py runserver 8001
```

用手機寬度操作（看到舊樣子先按 Cmd＋Shift＋R，本機的樣式檔沒有版本碼）：

1. 「了解」→ 選配指引 →「九號表：申請助聽器補助」→「要怎麼辦？」：六個步驟的標題和時限看得到、第 4 步有灰底提醒、說明看不到；按清單上面的「看每一步的說明」，每一步下面出現說明；出處在清單下面。**請確認三句字**（第一張重點卡小字、第 4 步提醒、「看每一步的說明」）**和「看每一步的說明」放在清單上面這個位置**。
2. 「我的選配指引」選配路線上「等待核定公文」那一站的「看申請流程」：跳到「要怎麼辦？」時說明已經打開。
3. 家人專區首頁：開頭一句「想幫聽力不好的家人，可以從這裡開始。」，下面五個列都是點進去的頁面。
4. 「助聽器」→「陪長輩適應」：三個階段選項下面有「陪伴配戴助聽器」，打開是原本那六條。
5. 「怎麼跟他說話」：九個方法圖在左、字在右；字放大到 200% 時圖回到字上面。
6. （有分享連結才做，不另外產生）分享報告「您可以怎麼幫忙」的「陪伴配戴助聽器」：跳到助聽器頁那一段、打開、亮框。

結果：2026-11-16 本人在 8001 實際操作，回覆「全部通過」。九號表的三句字和「看每一步的說明」放在清單上面的位置一併確認，維持現在的做法。
