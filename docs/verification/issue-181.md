# #181 字型改由網站自己提供、修正隱私權說明

日期：2026-10-22；分支 `feat/181-self-hosted-font`（從 `main` 的 `0dc64e9` 開出）。
狀態：本人 2026-10-22 合併 PR #205，視為下面三項驗收都通過（含第 7 條的字型下載量）。這份紀錄合併時還沒打勾，依本人指示在 #182 的 PR 補記。

## 範圍

- [#181](https://github.com/minuet878-prog/HearWell/issues/181)、ADR 0014、拷問 Q41（`docs/planning/branch-pages/grill-decisions.md`）。
- 字型：`@fontsource/noto-sans-tc` 5.3.0（2026-07 發布，OFL-1.1；沒用 11 天前才出的 5.3.1），只引入 400／500／600／700，打包進 `site.css`。Vite 改用相對路徑（字型檔跟 `site.css` 放在一起），並關掉把小檔塞進 CSS 的功能。
- 版型拿掉 Google Fonts 的三行。
- 隱私權說明刪掉 cdnjs 那條，修訂日期改成 2026/10/22，同意版本維持第 1 版。**上線日如果不是 10/22，合併前要改 `PRIVACY_UPDATED_ON`。**
- 截圖工具原本擋 Google Fonts，改成擋自己的字型檔，截圖照舊用系統字型。
- 不需要交叉審查：沒有碰計分、門檻、資料 migration 或權限。

## 驗收條件對照

| 條件 | 證明 |
|---|---|
| 1. 沒有請求送往 Google Fonts、cdnjs | e2e `StyleInBrowserTest.test_body_font_comes_from_our_own_host`：首頁、註冊、我的紀錄，所有請求的主機只有本站；Django `test_pages` 的 `_assert_site_stylesheets`：每一頁只有 `site.css`、沒有 Google 的網址 |
| 2. 本文是 Noto Sans TC，四種粗細照常 | 同一個 e2e：本文字型第一順位是 Noto Sans TC；四種粗細各自載入，而且**載入的就是那個粗細**（瀏覽器缺粗細時會改用最接近的，所以逐一比對）；字型檔都回 200 |
| 3. 全站截圖比對 | 見下方「截圖比對」 |
| 4. 隱私權說明 | `test_consent.PrivacyPageTests.test_lists_only_services_the_site_still_uses`：沒有 cdnjs、沒有 Google，Render、Neon、Sentry 照舊，版本仍是 1；`test_anyone_can_read_it_with_version_and_date`：頁面日期跟 `PRIVACY_UPDATED_ON` 一致 |
| 5. 已同意第 1 版的人不用重新同意 | 版本沒變（上一列）；`test_consent` 既有的 `test_already_consented_is_sent_on`、`test_minor_revision_does_not_ask_again` |
| 6. 字型載入失敗時用系統字型 | 截圖工具就是在擋掉字型檔的情況下拍的：430 張都正常顯示（見下方），字型堆疊的系統字型退路沒改 |
| 7. 首頁載入不明顯變慢 | 見下方「下載量」，**請本人判斷** |

## 先看到失敗（試驗，做完已還原）

- e2e 字型測試：把版型和 `site.css` 換回 `main` 的版本、重建，測試失敗在「請求的主機多了 fonts.googleapis.com、fonts.gstatic.com」；換回後通過。
- 粗細檢查：拿掉 500 那一行、重建，測試失敗（只拿到 400、600）；還原後通過。
- Django 測試：先改斷言，`test_pages` 的三個樣式表測試與隱私權測試失敗，改程式後通過。

## 截圖比對

`e2e/screenshots.py` 在 `main`（暫時的 worktree）和本分支各拍一次，430 張：

- 422 張相同。
- 隱私權頁 4 張不同：少了 cdnjs 那一行、日期改了，是預期的。
- 聽力圖輸入、修改、比較、IOI-HA 我的紀錄（390 寬）4 張，各 11–22 個像素差 1/255 的顏色，都在圖表卡片右邊圓角的反鋸齒上。查原因：
  - `main` 自己拍兩次相同，本分支自己拍兩次也相同，所以不是偶發。
  - 把字型的 `@font-face` 拿掉、其他改動都留著再拍，跟 `main` 完全相同。
  - 結論：頁面多了字型規則，瀏覽器去要（被截圖工具擋掉的）字型檔，多重畫了一次，圓角的反鋸齒差一點點。版面沒有變。
- 圖表裁切（`parts`）沒有出現在差異裡。

## 下載量（第 7 條）

同一台電腦、全新瀏覽器、390 寬，量字型檔（`main` 從 Google，本分支從本站）：

| 頁面 | main | 本分支 |
|---|---|---|
| 首頁 | 11 個檔、704,654 bytes | 25 個檔、807,520 bytes（+15%） |
| 註冊頁 | 10 個檔、632,108 bytes | 20 個檔、648,176 bytes（+2.5%） |

- 字型的 CSS 規則：本分支 20,260 bytes（brotli），Google 的樣式表 20,405 bytes；網站自己的樣式 9,509 bytes，跟 `main` 的 9,498 幾乎一樣。`bundle.test.js` 把兩者分開設上限。
- 本機時間沒有意義（本機比 Google 近），沒量。字型用 `font-display: swap`：字型還沒到時先用系統字型顯示文字，不會擋住畫面。
- 檔案比較多，是因為 Fontsource 切字的方式跟 Google 不同；Render 用 HTTP/2，多個小檔可以同時下載。

## 自動驗證

| 項目 | 結果 |
|---|---|
| Django 全部 | 799 個通過 |
| 前端（Vitest） | 201 個通過（含 CSS 體積上限） |
| e2e `e2e.main_flow` 全套 | 83 個通過（在粗細檢查加嚴之前跑的；加嚴後的字型測試另外單獨通過） |
| Ruff | 通過 |

## 自審（`/mattpocock-skills:code-review`）

| 發現 | 處理 |
|---|---|
| Spec：粗細檢查會被「最接近的粗細」騙過 | 已改：逐一比對粗細，並做了拿掉 500 的試驗 |
| Spec：日期要等於上線日 | 寫在上方範圍，合併前確認 |
| Standards：截圖工具註解寫了歷史、常數名稱不清楚 | 已改 |
| Standards：建置同時輸出 `.woff`（現代瀏覽器只用 `.woff2`），靜態檔變多 | 沒改：套件的寫法，改要自己寫 `@font-face`；只影響部署時的檔案數 |
| Standards：版本 1 的斷言和帳號設定測試重複 | 沒改：兩者守的是不同的事 |

## 請本人驗收

- [x] 第 7 條：上面的下載量可以接受嗎？
- [x] 打開首頁、註冊頁、我的紀錄，字看起來跟現在一樣（Noto Sans TC）。
- [x] 隱私權說明「會交給誰」只剩 Render、Neon、Sentry，日期正確。
