# #677 診間 QR code 小卡

日期：2026-11-17。分支：`feat/677-clinic-cards`（還沒推送）。規格 [#677](https://github.com/minuet878-prog/HearWell/issues/677)，票 #678（設計圖）、#679（本人寫字）、#680–#682（實作）、#683（本人上線後實機掃碼）。

狀態：2026-11-17 本人在本機實際操作後回覆「看過了沒問題」，**驗收通過**；「不用註冊・免費」框本人決定留藍色。自動測試全過，交叉審查三輪後沒有要修。上線後本人做 #683（驗收 27–29）。

- 拷問決定：[clinic-card-grill-decisions.md](../planning/found-by-family/clinic-card-grill-decisions.md)；ADR 0066（小卡網址永久保留、轉到落點才計數，`/c/e`、`/c/f`）。
- 本人在設計圖選定（2026-11-17，#678）：卡片 C（大標題＋QR code 在右）、列印頁 P。
- 本人寫的字（2026-11-17，#679）：一題一題選定，原文在 [#679 的留言](https://github.com/minuet878-prog/HearWell/issues/679#issuecomment-6933319067)，放上 C 排法實際大小檢查過。
- 第 4 步自審（`/mattpocock-skills:code-review`，每張票各一次）：Standards 沒有要修；補了 Spec 指出的斷言缺口，並把「同時送出」換成真的抓得到錯的測試（第一版測試對「先讀再寫回」的錯誤寫法照樣通過，等於沒驗到）。
- 交叉審查（Codex，2026-11-17，三輪）：[第一輪與處理](https://github.com/minuet878-prog/HearWell/issues/677#issuecomment-6936212514)、[第二輪與處理](https://github.com/minuet878-prog/HearWell/issues/677#issuecomment-6936767806)；第三輪只差驗收 23 一個斷言（A4 紙張也不能有底圖），補上（`01a9d370`）後 Codex 確認通過。抓到一個真的 bug：801–825px 寬的視窗列印頁會左右捲（`0a972ff4`）。
- 沒有操作真實資料。測試都在臨時測試資料庫上。migration 0039 只在 `GuestMonth` 加兩個欄位、預設 0。

## 行為

| 項目 | 現在 |
|---|---|
| 小卡網址 | `/c/e`（長輩卡）→ 推薦精靈年齡那一步、`/c/f`（家屬卡）→ 家人專區首頁，轉頁時帶 `via=clinic-elder`／`via=clinic-family`。只收 GET、不讀參數、只轉到寫死的落點、本身不計數、不受同意書攔截、禁止收錄、不進 sitemap；`robots.txt` 不動 |
| 計數 | 落點頁在瀏覽器裡打開後，由 `arrival-count.js` 送一次 `POST /api/guest-counts/`，再拿掉網址上的標記；重新整理、轉傳都不會重算。資料庫直接加一（`UPDATE … SET x = x + 1`）。後台「訪客月計數」多「小卡：長輩卡」「小卡：家屬卡」兩欄。登入的人掃也算 |
| 列印頁 `/clinic-cards` | 不用登入；沒有頁首、頁尾、底部分頁；上方切換長輩卡／家屬卡（是連結，沒有 JavaScript 也能切）、列印要點；下面整張 A4 預覽 |
| 印出來 | 一頁 A4、兩欄五列 10 張、每張 9×5.5 cm、淡灰裁切線；標題、切換、列印要點不印 |
| 卡上 | 聽伴 logo 與名字、本人的字（標題 16pt、「不用註冊・免費」框、說明 11pt）、QR code（連白邊 2.8 cm）、「用手機相機掃」、`tingpal.tw` |
| QR code | `segno` 在自己的伺服器畫成 SVG，中等錯誤更正、4 格白邊；內容是設定的正式網址（`SITE_URL`）加小卡路徑，不看這次打開的網址；沒設 `SITE_URL` 時不畫，紅框寫明原因 |
| 手機上 | 832px 以下只顯示一張卡，寫「手機上只顯示一張卡的樣子；要印整張請用電腦」；320px 時卡片縮到 80% |
| 後台首頁 | 最上面多一個「列印診間小卡」連結；站上其他頁面都沒有連到列印頁 |

跟規格或設計圖不一樣、或規格沒寫到的地方（請本人驗收時一起看）：

1. **規格驗收 2 的「問卷目錄」不夠精確**：已登入但還沒有任何紀錄的人，掃長輩卡看到的是「幫我選」精靈；有紀錄的人才是問卷目錄（ADR 0030 原本的規則）。小卡網址就是轉到「篩檢」分頁那一頁，跟按分頁看到的一樣。
2. **「不用註冊・免費」框是藍框藍字**（設計圖 C 的畫法），跟拷問 Q12「主色只用在 logo 與標題」不同；本人 2026-11-17 驗收時決定**留藍色**。
3. **卡上的字用 `pt`、比 1rem 小**（10–12pt）：本人在設計圖 C 選定，登記在 `CODING_STANDARDS.md` 第 16 條「負責人選過的小字」；列印頁螢幕上的預覽也照紙上的大小、不跟著字級放大（交叉審查後本人決定）。小字檢查改成認得 `pt`（1rem＝13.5pt），別處用 `pt` 寫小字會被擋。
4. **QR code 的黑白格子部分約 2.1 cm**：規格寫「至少約 2.5 cm 見方，四周有白邊」，現在是連白邊 2.8 cm（設計圖 C 的大小）。
5. **關掉 JavaScript 的人掃了不會被算到**（拷問 Q15，跟第 5 項同一種做法）。
6. **計數 API 與落點腳本是小卡先建的**：第 5 項（#655）的兩個門、「從傳給他打開」之後加在同一支 API（多加種類）和同一支腳本（多認 `via=send`）。
7. **列印頁的 `@page { margin: 0 }` 寫在頁面裡**（不是 `site.css`）：其他頁面印出來都留 1.5cm 邊，只有這頁要滿版。
8. **`requirements.txt` 多了 `segno==1.6.6`**，部署時會跟著安裝；本機的 `py313` 已經裝好。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。「頁面」＝`screening/tests/test_clinic_cards.py`，「端對端」＝`e2e/main_flow.py`，「前端」＝`frontend/src/arrival-count.test.js`。

| # | 驗收條件（簡寫） | 驗證 | 證據 |
|---|---|---|---|
| 1 | 兩個小卡網址轉到各自落點、帶標記 | ✅ 自動 | 頁面 `CardAddressTests`；端對端 `ClinicCardArrivalTest`（落點畫面有「您目前的實際年齡？」「家人專區」） |
| 2 | 已登入轉到同一個網址 | ✅ 自動 | 頁面 `CardAddressTests`（未同意者、已同意者跟按「篩檢」分頁同一頁）、`ReturningUserLandingTests`（有紀錄者看到「選問卷」）；見上面第 1 點 |
| 3 | 多帶的參數不帶過去 | ✅ 自動 | 頁面 `test_anything_added_to_the_address_is_dropped`（兩種卡） |
| 4 | 打開小卡網址本身不計數 | ✅ 自動 | 頁面 `test_opening_the_address_counts_nothing` |
| 5 | 禁止收錄、不在 sitemap 與公開頁面清單、`robots.txt` 不變 | ✅ 自動＋diff | 頁面 `CardAddressTests.test_kept_out_of_search_and_the_sitemap`；這個分支沒有改 `screening/views/crawlers.py` |
| 6 | 標記不是 `from=card`、跟 `via=send` 不同 | ✅ 自動 | 頁面 `CardAddressTests`（`via=clinic-elder`／`clinic-family`）；前端「`via=send` 不送」 |
| 7–8 | 瀏覽器打開後該格加一、標記拿掉 | ✅ 自動 | 端對端 `ClinicCardArrivalTest`；前端前兩項 |
| 9 | 重新整理、再打開不加一 | ✅ 自動 | 端對端 `ClinicCardArrivalTest`（重新整理後還是 1）；前端「標記拿掉後不再送」 |
| 10 | 兩種各加自己那格、其他格不變；認不得回 400 | ✅ 自動 | 頁面 `ScanCountTests` |
| 11 | 同時送出兩次都算到 | ✅ 自動 | 頁面 `SimultaneousScanTests`（兩條執行緒同時送）、`ScanCountTests`（資料庫直接加一）；兩個都拿「先讀再寫回」的錯誤寫法試過會失敗 |
| 12 | 資料表只有月份與數字、後台兩欄 | ✅ 自動 | `test_guest_counts.py`（`OnlyTheCountsTests`） |
| 13 | 同意書與隱私權說明沒變 | ✅ diff＋自動 | 這個分支沒有改隱私權說明模板、`CONSENT_VERSION`、`PRIVACY_UPDATED_ON`；`test_consent.py` 照舊通過 |
| 14 | 列印頁不用登入、預設長輩卡、可切家屬卡 | ✅ 自動 | 頁面 `PrintPageTests` |
| 15 | 卡上有哪幾樣、沒有姓名單位 | ✅ 自動 | 頁面 `test_every_card_says_only_its_words_with_its_own_code`（兩種卡各 10 張逐張比對看得到的字；試著加「王小明」會失敗） |
| 16 | QR code 是正式網址＋小卡路徑，跟打開的網址無關 | ✅ 自動 | 頁面 `QrCodeTests`（兩種卡、換 `SITE_URL`、從 localhost 打開） |
| 17 | 沒設正式網址時寫明、不畫 | ✅ 自動 | 頁面 `test_without_the_live_sites_address_it_says_so_and_draws_none` |
| 18 | 列印頁禁止收錄、站上沒有連結 | ✅ 自動 | 頁面 `PrintPageReachTests` |
| 19 | 後台首頁有連結 | ✅ 自動 | 頁面 `test_the_admins_home_links_to_it` |
| 20 | 列印時 9×5.5 cm、10 張一頁、裁切線、要點不印 | ✅ 自動 | 端對端 `test_printed_it_is_one_a4_sheet_of_ten_real_size_cards`（含瀏覽器產出的 PDF 剛好一頁 A4） |
| 21 | QR code 至少約 2.5 cm、有白邊 | ✅ 自動 | 端對端同上（10 個、寬高）；頁面 `test_each_code_has_its_white_border`；見上面第 4 點 |
| 22 | 手機 200% 字級不左右捲 | ✅ 自動 | 端對端 `test_it_fits_a_phone_at_double_text_size`、`test_a_window_a_little_wider_than_a_phone_does_not_scroll_sideways`（801–840px） |
| 23 | 白底深色、對比 4.5:1、沒有大片底色 | ✅ 自動 | 端對端 `test_printed_it_is_one_a4_sheet_of_ten_real_size_cards`（字到紙之間每一層沒有底色底圖、7 段字和 QR 黑格都至少 4.5:1；試著讓標題加深藍底會失敗） |
| 24 | 多了 `segno`、不呼叫外部服務 | ✅ 自動 | 頁面 `test_drawn_here_by_segno_without_calling_out` |
| 25 | 用本人的原文；沒定稿前不開工 | ✅ 自動＋紀錄 | 頁面 `CardWordsTests`；端對端 `test_printed_the_owners_words_keep_their_lines_inside_the_card`。#679 在 2026-11-17 08:07（台灣時間）關閉，#682 的 commit 在 09:35 之後 |
| 26 | 照設計圖選定的排法 | ✅ 本人 | 2026-11-17 本機操作，下面的清單 |
| 27–29 | 實機三種掃法、月計數增加、黑白印表機掃得到 | ✅ 部分＋本人略過 | #683：iPhone 相機、iPhone 的 LINE 兩張卡都對、月計數各加 2；Android 與黑白卡本人 2026-11-19 決定略過，見下方「上線後實機掃碼」 |
| 30 | 驗證紀錄逐條打勾、附交叉審查結果 | ✅ | 本文件 |
| 31 | roadmap 第 6 項標成完成 | ✅ | `docs/roadmap.md` |

## 測試

- 後端：2895 個測試通過（`python manage.py test --settings=config.test_settings --parallel 4`）。
- 前端：755 個測試通過（`npm test --prefix frontend`）。
- 端對端：500 個測試通過（`e2e.main_flow --parallel 4`，`4767b970`）；之後只改測試，小卡的 5 個端對端在 `01a9d370` 重跑通過。
- Ruff：`ruff check .`、`ruff format --check .` 都通過。

## 本人實際操作驗收（本機）

在終端機開 worktree 的網站（會用您本機的資料庫：`migrate` 會在訪客月計數加兩個欄位；掃小卡的計數會存進本機資料庫）。前面加 `SITE_URL` 才畫得出 QR code，QR code 連的是正式站的 `/c/e`、`/c/f`，上線前掃了會看到正式站的「找不到這一頁」：

```bash
cd /Users/huangweizhe/HearWell/.claude/worktrees/677-clinic-cards && /Users/huangweizhe/HearWell/py313/bin/python manage.py migrate && SITE_URL=https://tingpal.tw /Users/huangweizhe/HearWell/py313/bin/python manage.py runserver 8001
```

- [x] 打開 http://localhost:8001/clinic-cards ：長輩卡 10 張、排法跟設計圖 C 一樣、字是您 #679 的原文
- [x] 按「家屬卡」：整張換成家屬卡
- [x] 印一張（A4、實際大小 100%）：量一張是 9×5.5 cm，剛好一頁 10 張，裁切線看得到，標題與列印要點沒印出來
- [x] 用手機掃印出來的 QR code：掃得到（上線前會開到正式站的「找不到這一頁」）
- [x] 手機寬度打開列印頁：只有一張卡和「要印整張請用電腦」
- [x] 打開 http://localhost:8001/c/e ：到年齡那一步，網址列沒有 `via=`
- [x] 打開 http://localhost:8001/c/f ：到家人專區首頁，網址列沒有 `via=`
- [x] 後台（http://localhost:8001/admin/）：首頁最上面有「列印診間小卡」；「訪客月計數」這個月的小卡兩欄各加了一
- [x] 不用 `SITE_URL` 重開一次（拿掉指令裡的 `SITE_URL=https://tingpal.tw `）：列印頁有紅框「沒有設定正式網址，印出來的 QR code 不能用。」、沒有 QR code
- [x] 決定「不用註冊・免費」框留藍色還是改黑字（上面第 2 點）：留藍色

## 上線後實機掃碼（#683，正式站）

2026-11-17，`https://tingpal.tw/clinic-cards` 用一般印表機印長輩卡、家屬卡各一張（A4、實際大小 100%）。掃之前後台「訪客月計數」2026/11 小卡兩欄是 0、0。

| 卡 | 掃法 | 落點 | 結果 |
|---|---|---|---|
| 長輩卡 | iPhone 相機 | 「幫您找適合的問卷」年齡那一步 | ✅ |
| 長輩卡 | iPhone 的 LINE 掃描 | 同上，在 LINE 裡打開 | ✅ |
| 家屬卡 | iPhone 相機 | 家人專區首頁 | ✅ |
| 家屬卡 | iPhone 的 LINE 掃描 | 同上，在 LINE 裡打開 | ✅ |
| 長輩卡、家屬卡 | Android 相機 | — | ➖ 本人沒有 Android 手機，2026-11-19 決定略過 |
| 黑白雷射印表機印的卡 | 任一手機 | — | ➖ 2026-11-19 本人決定略過 |

- 驗收 27：iPhone 相機與 LINE 掃描都打得開、落在對的頁面 ✅；Android 本人決定略過。
- 驗收 28：掃完後台長輩卡 0 → 2、家屬卡 0 → 2，跟掃的次數一樣 ✅。
- 驗收 29：本人決定略過；沒有用黑白雷射印表機實測過。
- 2026-11-19 本人決定結案 #683。
- 這 4 次是本人測試，看階段結束的數字時要扣掉（見 [階段結束時要回答的問題](../planning/found-by-family/phase-end-questions.md)）。

