# #655 三個家屬頁面、兩個門、傳給他

日期：2026-11-17。分支：`feat/655-family-pages`（還沒開 PR）。規格 [#655](https://github.com/minuet878-prog/HearWell/issues/655)，票 #669（設計圖）、#670（骨架）、#671（本人的字）、#672–#675（實作）、#676（本人實機驗收）。決策來源：[拷問決定](../planning/found-by-family/family-pages-grill-decisions.md) Q1–Q12、[研究](../planning/found-by-family/family-pages-research.md)、本人定稿的字在[骨架檔](../planning/found-by-family/family-pages-skeleton.md)。

狀態：2026-11-17 本人在預覽（埠 8001）實際操作後回覆「看過了，沒問題」，**驗收通過**。自動測試全過。手機分享到 LINE 等實機項目要 https，部署後在 #676 做。

- 設計圖（#669，2026-11-16）：本人五處都照建議選（兩個門 A、專區兩組 A、條列 A、「蛤」結尾 A、傳給他 B）。
- 本人的字（#671，2026-11-17）：逐段由代理擬稿、本人點選或修改；「長輩不肯去怎麼說」的傳給他段落（2026-11-17）照頁面一、實心按鈕。
- 第 4 步自審（`/mattpocock-skills:code-review`，基準 `origin/main`）：Standards 硬性 1 項（預設訊息用「你」，本人決定保留、`CODING_STANDARDS.md` 第 18 條加例外）、判斷題 6 項；Spec 11 項。本人決定：出處用「美國聽語學會」、查核日期沿用「內容查核於」、回饋頁名用頁面大標。測試缺口與判斷題都處理了。
- 交叉審查（Codex，2026-11-17）：[審查與處理](https://github.com/minuet878-prog/HearWell/issues/655#issuecomment-6940218668)。合併阻擋 1 項（migration 撞號，已合併 `main`、改成 `0041`）、要修 3 項已修、驗收證據 8 條已補；不同意 4 項附理由。**Codex 複核因額度用完略過，本人 2026-11-17 同意。**
- 沒有操作真實資料。測試都在臨時測試資料庫上；畫面檢查用的臨時截圖檔看完即刪，沒有進版控。

## 行為

| 情況 | 現在 |
|---|---|
| 沒登入的首頁 | 第一眼兩塊淡藍色塊：「我想了解自己的聽力／大約 3 分鐘，不用註冊」到推薦精靈年齡那一步；「我擔心家人的聽力／看看可以怎麼幫他」到家人專區。下面是登入、兩個文字連結、聽力師那句。按門會計數 |
| 已登入、沒有紀錄 | 照舊「從一份問卷開始」，沒有門 |
| 已登入、有紀錄 | 照舊照顧旅程 |
| 家人專區首頁 | 兩組：「先看看是不是聽力的問題」三頁、「確定聽力不好之後」五列；傳給家人、急症框、出處照舊 |
| `/family/signs`、`/family/loud-tv`、`/family/huh` | 本人的字；急症用問答小助手那一塊；出處 CHSA（ASHA）、內容查核於 2026/11/17；公開頁面、進 sitemap |
| 傳給他（三頁＋長輩不肯去怎麼說） | 灰框寫出預設訊息與 `…/questionnaire_list?via=send`；有分享選單時「傳給他做篩檢」送出一整段文字；沒有時「複製訊息」→「✓ 已複製」；沒有 JavaScript 時只有灰框。「蛤」頁是外框按鈕 |
| 打開傳出去的網址 | 推薦精靈年齡那一步；在瀏覽器裡打開計一次、標記從網址列拿掉；已登入沒同意的人先到同意書頁再回來 |
| 訪客月計數 | 多三格：門：了解自己、門：擔心家人、從傳給他打開（migration `0041`，接在第 4 項的 `0040_retestreminder` 後） |

跟規格或設計圖不一樣、或規格沒寫到的地方（請本人驗收時一起看）：

1. **沒登入首頁有一個看不見的大標「聽伴」**：給讀螢幕軟體，每頁都要有一個大標題。
2. **門的計數在按下時送出**（不是到了目的地才算），規格本文已寫明原因（搜尋引擎會跑首頁的 JavaScript 但不按連結）。
3. **出處的機構名寫「美國聽語學會」**，跟家人專區其他 ASHA 出處一致（本人決定）。
4. **意見回饋表單上三頁的名稱**用頁面大標（本人決定）。
5. **合併 `main` 後**，#693 的「沒登入首頁連到家人專區」測試改成檢查「我擔心家人的聽力」這個門。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。都在 `screening/tests/`、`frontend/src/`、`e2e/main_flow.py`。

| # | 驗收條件（簡寫） | 驗證 | 證據 |
|---|---|---|---|
| 1 | 三頁 200、本人的字、急症、出處、查核日期 | ✅ 自動 | `test_family_pages.py`（`FamilyPageChecks`） |
| 2 | 依場合分組條列、沒有勾選框與判定 | ✅ 自動 | `test_family_pages.py`（各組條列、`test_no_score_and_no_verdict`） |
| 3 | 前兩頁唯一的實心按鈕是傳給他 | ✅ 自動 | `test_family_pages.py`（`test_the_one_solid_button_is_send_to_him`、`test_the_share_button_says_send_to_him_in_its_pages_style`） |
| 4 | 「蛤」頁先聽損模擬再怎麼說話，傳給他外框 | ✅ 自動 | `test_family_pages.py`（`HuhPageTests`） |
| 5 | 公開頁面、sitemap、沒有禁止收錄、LINE 預覽、確認過的標題描述 | ✅ 自動 | `test_public_pages.py`、`test_search_titles.py`、`test_sitemap.py`、`test_line_preview.py`、`test_family_pages.py`（`test_a_public_page_in_the_sitemap_with_its_line_preview`） |
| 6 | 每年查核清單寫到三頁 | 👀 人工 | `docs/roadmap.md` 每年查核那一條 |
| 7 | 三頁 200% 字級不左右捲 | ✅ 自動 | e2e `FamilyDoorsAndSendTest.test_the_pages_with_send_to_him_fit_a_phone_at_double_text_size` |
| 8 | 專區首頁兩組與順序 | ✅ 自動 | `test_family_pages.py`（`FamilyZoneHomeGroupsTests`） |
| 9 | 專區首頁傳給家人、急症、出處照舊，沒有傳給他 | ✅ 自動 | `test_family_redesign.py`、`test_send_to_him.py`（`WhereSendToHimIsNotTests`） |
| 10 | 沒登入首頁兩個門，舊標題、三步、開始篩檢、我是家人拿掉 | ✅ 自動 | `test_home_doors.py`、`test_home.py` |
| 11 | 門下面留登入、兩個文字連結、聽力師那句 | ✅ 自動 | `test_home_doors.py`、`test_add_to_home.py`、e2e |
| 12 | 兩個門各到對的頁面 | ✅ 自動 | e2e `test_each_door_goes_to_its_page_and_its_press_counts` |
| 13 | 訪客結果那一塊在兩個門上面 | ✅ 自動 | `test_home_doors.py`、e2e `GuestHomeTest` |
| 14 | 已登入沒有紀錄照舊 | ✅ 自動 | `test_home_doors.py`、`test_home_journey.py` |
| 15 | 已登入有紀錄照舊 | ✅ 自動 | `test_home_doors.py`、`test_home_journey.py` |
| 16 | 沒登入首頁 200% 不左右捲 | ✅ 自動 | e2e `test_first_visit_pages_fit_a_phone_at_double_text_size` |
| 17 | 四頁有傳給他、專區首頁與聽損模擬沒有、不肯去內文不變 | ✅ 自動 | `test_send_to_him.py`、`test_family_pages.py`、`test_family_zone.py` |
| 18 | 分享選單送出「訊息＋網址」一段，四頁相同 | ✅ 自動 | `share-button.test.js`、`test_family_pages.py`、`test_send_to_him.py` |
| 19 | 沒有分享選單時「複製訊息」→「✓ 已複製」 | ✅ 自動 | `copy-link.test.js`（send-to-him copy button） |
| 20 | 沒有 JavaScript 時寫出訊息與網址、沒有按鈕 | ✅ 自動 | e2e `test_without_javascript_the_message_and_address_are_there_to_copy` |
| 21 | 網址只有人人相同的標記 | ✅ 自動 | `test_send_to_him.py`、`test_family_pages.py` |
| 22 | 打開傳出去的網址到年齡那一步；已登入也到得了 | ✅ 自動 | e2e `test_the_sent_address_counts_once_and_loses_its_mark`、`test_send_to_him.py`（`SignedInOpensTheSentAddressTests`） |
| 23 | 按門各加一 | ✅ 自動 | `door-count.test.js`、e2e、`test_family_counts.py` |
| 24 | 從傳給他打開加一、標記拿掉 | ✅ 自動 | `arrival-count.test.js`、e2e |
| 25 | 重新整理、再轉傳不再加 | ✅ 自動 | `arrival-count.test.js`、e2e（另一個瀏覽器打開清掉的網址） |
| 26 | 沒執行 JavaScript 的請求不加 | ✅ 自動 | `test_family_counts.py`（`test_opening_a_page_or_the_api_counts_nothing`） |
| 27 | 不認得的種類回 400、不加 | ✅ 自動 | `test_family_counts.py` |
| 28 | 只有月份與數字、後台看得到三格 | ✅ 自動 | `test_guest_counts.py` |
| 29 | 隱私權說明與同意書沒變 | 👀 人工 | 這個分支沒有改 `privacy.html`、`CONSENT_VERSION`、`PRIVACY_UPDATED_ON` |
| 30–34 | 本人實機（LINE、Android、隔天、月計數） | ✅ 部分＋本人略過 | #676：iPhone 的 30、32、34 通過；31、32 的 Android 保存、33 本人 2026-11-19 決定略過，見下方「上線後實機」 |
| 35 | 本紀錄 | ✅ | 本檔 |

## 測試

- 後端 3,108 個、前端 764 個、e2e 508 個全部通過（2026-11-17，本機，合併 `main` 之後）。
- Ruff 檢查與格式都通過。

## 本人驗收

- 2026-11-17：本機開發資料庫先套用 `0041`（本人同意），本人在預覽（埠 8001）看過沒登入首頁的兩個門、家人專區兩組、三個家屬頁面、「長輩不肯去怎麼說」的傳給他、電腦上的「複製訊息」與後台月計數，回覆「看過了，沒問題」。
- 待部署後（#676，需要 https 的分享選單）：iPhone、Android 分享到 LINE；家人在 LINE 裡點開做完 HHIE-S；Android 在 LINE 裡用 LINE 保存；關掉 LINE 隔天結果還在不在；月計數三格增加。結果補在這裡。

## 上線後實機（#676，正式站）

2026-11-17 07:39（UTC）部署 `2bfc03cd`（含 #726 的 migration 合併）後，本人用 iPhone 操作。部署時三格是新欄位，從 0 開始。

| 驗收 | 做法 | 結果 |
|---|---|---|
| 兩個門 | iPhone 沒登入首頁，按「我想了解自己的聽力」「我擔心家人的聽力」 | ✅ 分別到推薦精靈年齡那一步、家人專區 |
| 30 | iPhone 在「長輩不肯去怎麼說」按「傳給他做篩檢」，分享選單選 LINE | ✅ 聊天室收到預設訊息與網址，網址有預覽 |
| 31 | Android 同一件事、Android 的 LINE 裡看到「複製訊息」 | ➖ 本人沒有 Android 手機，決定略過 |
| 32 | 在 iPhone 的 LINE 裡點開傳來的連結 | ✅ 第一個畫面問幾歲，不用註冊做完 HHIE-S、看到結果；後台「訪客完成」加 1 |
| 32 | Android 的 LINE 裡用 LINE 保存 | ➖ 本人決定略過 |
| 33 | iPhone：LINE 裡做完、完全關掉 LINE，隔天點同一個連結看首頁 | ➖ 本人決定略過（拷問 Q11 本來就只記錄、不影響驗收） |
| 33 | Android 同上 | ➖ 本人決定略過 |
| 34 | 後台訪客月計數 | ✅ 門：了解自己 0 → 1、門：擔心家人 0 → 1、從傳給他打開 0 → 1 |

- 2026-11-19 本人決定結案 #676；Android 與隔天的檢查沒有做。
- 這幾次是本人測試，看階段結束的數字時要扣掉（見 [階段結束時要回答的問題](../planning/found-by-family/phase-end-questions.md)）。

