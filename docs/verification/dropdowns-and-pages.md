# 下拉框統一與其他頁面整理

日期：2026-10-23；分支 `feat/dropdowns-and-pages`（從 `main` 的 `a1f2f0d` 開出，在 worktree `.claude/worktrees/dropdowns` 實作：主資料夾當時有別的 session 在跑測試）。
狀態：自動驗證完成；**不需交叉審查**（只改畫面；配戴比較只改「同一組時顯示幾張卡」，不碰計分、門檻、資料或權限）；**本人實際操作驗收通過**（2026-10-23）。

## 範圍

PR #250 之後盤點「還沒看過的頁面」（子代理逐頁看 20 張手機截圖，主要問題由我親眼確認）。小改動，沒有開 issue。本人在兩頁比較頁做了 7 個決定。

| 項目 | 本人的選擇 | 改了哪裡 |
|---|---|---|
| 下拉框 | B：頁面上的一律白框（`.dropdown-box`，由 `.phone-choice` 改名）；卡片裡改成上方細線＋箭頭（`.dropdown-line`），不框中框。共 11 處 | `site.css`、`result`／`ssq12_result`／`audiogram_detail`／`audiogram_compare`／`questionnaire`／`add_to_home`／`guide/chapter`、`guide/index`、`comparisons/average_card`、`AudiogramApp.jsx` |
| 首頁「結果長這樣」 | #247 漏網：示意卡不是 `.card`，標題被加了藍條，加進排除清單 | `site.css` |
| 隱私權＋同意頁 | A：版次小字；cookie 句提醒框；同意頁「重點」放進跟隱私權頁一樣的藍框卡片，「按不同意會登出」提醒框。句子裡的連結：原本用按鈕樣式湊 44px 觸控高度，把整行撐高；改成 `.inline-link`（上下內距撐出 44px、負外距抵銷，行距不變）。同一原因的刪除帳號頁、註冊頁一併改 | `privacy.html`、`consent.html`、`delete_account.html`、`register.html`、`site.css` |
| 註冊頁 | B：標籤粗體、說明改內文灰色小一級（`.field-help`，對比 7.6:1）、密碼規則提醒框、「顯示」跟標籤同一行；**「已經有帳號？登入」移到表單下面——本人改掉 #151 的決定** | `register.html`、`field_messages.html`（可傳 `help_class`，其他表單不變）、`site.css` |
| 新訪客首頁 | A：步驟卡數字、圖示、文字一列（字放大時文字換到下一行）；「內容由台灣執業聽力師…」不再斷在「聽／力師」（`text-wrap: balance` 平均分行時切到中間；包成 `break-keep`） | `index.html`、`site.css` |
| 聽力圖比較＋修改 | A：卡片只留數據和圖，圖例小字；三句提醒集中到「看懂這張比較」提醒框（**新加小標**；改掉 #203 把提醒放在卡片裡的做法）。修改頁的說明從步驟條上方移到右耳、左耳步驟（有圖的地方），提醒框 | `audiogram_compare.html`、`audiogram_new.html`、`AudiogramApp.jsx` |
| 配戴比較 | A：「目前查看的兩筆」就是「聽力報告裡的組合」時只顯示後者一張，加「這一組已經在聽力報告裡」 | `hhi_comparison.html` |
| 聽力報告＋家人報告 | A：螢幕版卡片化——重點摘要藍框、每份量表／聽力圖／比較一張卡、分級用全站顏色標籤、分數標籤、逐題回答白框下拉、手寫姓名欄只在列印出現、「更換或移除比較」改按鈕；家人報告螢幕上只留「先看重點」，「重點摘要」只在列印出現。全部寫在 `@media screen`，列印另外還原下拉框 | `health_report.html`、`report_content.html`、`report_graded_section.html`、`site.css` |

## 自動驗證

| 檢查 | 結果 |
|---|---|
| `python manage.py test --settings=config.test_settings` | 1063 個全部通過 |
| `npm test --prefix frontend` | 全部通過 |
| `ruff check .` | 通過 |
| `e2e.main_flow` | 101 個全部通過（新增 1 個） |
| 列印截圖比對（`e2e/screenshots.py` ＋ `e2e/compare_shots.py`） | 聽力報告、家人報告 × 390／1024 寬共 4 張，跟改動前**逐像素相同** |

e2e 抓到、已修的真問題（都是字放大 200%、320px 寬）：

- 首頁步驟卡排成一列後，數字＋圖示＋內距就快 290px，文字放不下，頁面撐到 352px → 文字可以換到下一行。
- 下拉框改白框後內容左右各內縮 1rem（2 倍字級時 36px），聽力圖輸入的數值表、結果頁的數值表放不下 → 表格和欄位組貼齊白框邊。
- 「聽力師」一開始用不換行，字放大後連同圖示超寬 → 改成「盡量不拆，真的放不下才拆」。

改過的測試（畫面改了，斷言跟著改，要保護的內容照舊確認）：

- 註冊（`test_accounts`）：說明的 class、登入連結改在表單之後（仍帶 `next`）。
- 首頁信任列（`test_pages`、`test_layout`、`test_account_settings`）：去掉標籤後比對整句；只看順序的用前半句。
- 聽力圖比較（`test_audiogram`）：提醒不在卡片裡、在卡片後的提醒框裡，三句逐字確認。
- 報告（`test_report`、`test_thi_report`）：分級標籤多了顏色 class。
- SSQ12 配戴比較（`test_ssq12_comparisons`）：下拉框有 class 了。
- `test_add_to_home`、`test_guide`、e2e：`.phone-choice` 改名 `.dropdown-box`。
- e2e：「下載我的資料」不再是按鈕，從按鈕測試移出，改驗行內連結：藍色底線、觸控高度 ≥ 44px、所在段落高度是整數行（沒被撐高）。表格寬度改跟白框內寬比。配戴比較改驗同一組只出現一張。新增：報告螢幕上沒有手寫欄、分級有底色、家人報告不顯示重點摘要；列印時三者都恢復。

## 預覽確認

- 在 worktree 開 runserver 8001（主資料夾的預覽伺服器先停掉）。聽力報告手機寬度：重點摘要藍框、分級顏色標籤；「中度障礙」一開始被斷成兩行，改成標籤整塊換行。
- 瀏覽器會快取舊的 `site.css`（檔名沒有版本號），驗收時頁面看起來沒變就重新整理（Cmd+Shift+R）。

## 本人驗收

- [x] 下拉框（結果頁、SSQ12、聽力圖結果與比較、問卷清單、選配指引、加到主畫面、聽力圖輸入）
- [x] 隱私權、同意頁、刪除帳號頁的行內連結
- [x] 註冊頁
- [x] 新訪客首頁
- [x] 聽力圖比較、修改
- [x] 配戴比較
- [x] 聽力報告、家人報告（螢幕和列印）
