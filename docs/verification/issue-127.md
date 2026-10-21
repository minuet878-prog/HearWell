# #127 公開頁與帳號頁改用 Tailwind 排版驗證

日期：2026-10-21；分支 `feat/127-public-pages`；母分支 `feat/tailwind-migration`。
狀態：自動驗證完成；本人 2026-10-21 實際操作驗收通過。子分支合回 `feat/tailwind-migration`；沒有 push、開 PR 或合併回 `main`。

## 範圍與參考

- [#127](https://github.com/minuet878-prog/HearWell/issues/127)、母規格 #119、ADR 0008、ADR 0009。
- 九頁模板：`index`、`login`、`register`、`privacy`、`family_guide`、`add_to_home`、`consent`、`account`、`delete_account`；加上註冊頁與刪除帳號頁共用的錯誤訊息片段 `field_messages.html`。
- `field_messages.html` 也被問卷頁（`questionnaire.html`、`screening.html`，屬 #128）引用。只改了一個 class（`text-body-emphasis` → `text-black`），#128 不用再改它。
- 有名字的元件 class（`btn`、`form-control`、`card`、`narrow-form`、`account-danger`、`text-danger` 等）都沒動。

## 對照表

Bootstrap 的間距 1–2 級和 Tailwind 同名同值；3 級以上同名不同值，要換數字。Bootstrap 的 utility 都有 `!important`，Tailwind 沒有，但 utilities 圖層本來就蓋過 components 和 base 圖層，結果相同。

| Bootstrap | 數值 | Tailwind | 出現在 |
|---|---|---|---|
| `mb-3`、`mt-3` | 1rem | `mb-4`、`mt-4` | 登入、註冊、家屬指南、同意書、帳號、刪除帳號 |
| `mt-4` | 1.5rem | `mt-6` | 隱私、家屬指南、加到主畫面、帳號（小標題與段落） |
| `mt-5` | 3rem | `mt-12` | 帳號「刪除帳號」區 |
| `pt-4` | 1.5rem | `pt-6` | 同上 |
| `w-100` | 100% | `w-full` | 首頁「開始篩檢」、註冊鈕 |
| `w-50` | 50% | `w-1/2` | 登入／註冊、我同意／不同意 |
| `d-flex` | display: flex | `flex` | 登入、同意書、刪除帳號 |
| `fw-normal`、`fw-bold` | 400、700 | `font-normal`、`font-bold` | 登入／註冊標題、家屬指南網址、帳號「刪除帳號」 |
| `text-body-emphasis` | #000（網站沒覆寫） | `text-black` | 首頁、登入提示、欄位說明 |
| `text-body-secondary` | #495057（網站把它覆寫成本文色） | `text-body` | 隱私權版本行 |
| `text-break` | 放不下才斷字 | `wrap-anywhere` | 家屬指南網址（和 #124 的頁首帳號同一種換法） |

沒換的：`mt-1`、`mt-2`、`mb-0`–`mb-2`、`px-0`、`px-1`、`gap-2`、`flex-wrap`、`align-baseline` 兩邊同名同值。

## 刻意的改動（本人 2026-10-21 同意並驗收）

1. **隱私權說明、家屬指南的文章外框加 `wrap-anywhere`**：`main` 上這兩頁在 320px、字級 200% 時就會左右捲動（隱私頁 email 連結右緣 545px，家屬指南英文出處右緣 405px），不是遷移造成的，但驗收條件 3 要求不能捲動。加了之後只有「一個字放不下一行」時才斷開，正常字級畫面一個像素都沒變（下方截圖 26 張相同），200% 時不再超出。

## 驗收條件對照

| 條件 | 證明 |
|---|---|
| 1. 截圖只比這群頁面（手機與桌機、登入前後），和 `main` 基準沒有超過反鋸齒的差異 | 截圖工具 public 群組：基準在 `origin/main`（`ef638a7`）用暫時的 worktree 拍，本分支再拍一次；**26 張全部逐像素相同，字型與基礎字級 0 頁不同**。涵蓋 13 種頁面狀態 × 390／1024 寬（首頁、隱私、家屬指南、加到主畫面各拍未登入與登入）。截圖在 `e2e-artifacts/shots/main-127`、`127`（不進版控） |
| 2. 模板裡沒有 Bootstrap 專屬的排版與間距 class | `screening/tests/test_tailwind.py:48`。改之前失敗、列出 18 處；改之後通過。限制：`mb-3` 這類同名不同值的間距，搜尋分不出模板指的是哪一套，靠條件 1 的截圖抓 |
| 3. 字級 200%、手機寬度，沒有左右捲動、元件不重疊 | `e2e/main_flow.py:800` `test_public_and_account_pages_fit_a_phone_at_double_text_size`：九頁（共 13 種登入狀態）在 320px、`html` 字級 225%（2 × 112.5%）下，`:830` 頁面寬不超過 320，`:843` 畫面上的按鈕、輸入框、民國年欄位前後的「民國」「年」任兩個不重疊（同一組欄位刻意共用 1px 外框，容許 1px）。改之前 9 種失敗（首頁 981px、登入 477px、註冊 927px、隱私 545px、家屬指南 405px、同意書 477px），改之後通過 |
| 4. 一般測試與這些頁面相關的 e2e 通過 | 見下方「自動驗證」；#125 記錄的兩個既有失敗（`test_home_step_cards_stack_on_a_phone`、`test_phone_width_needs_no_sideways_scrolling` 的 `/`）已轉綠 |

## 自動驗證

| 檢查 | 結果 |
|---|---|
| Django 全套 `manage.py test --settings=config.test_settings --noinput` | 646 個通過（多了 `test_tailwind`；7 個斷言舊 class 字串的測試改成新名稱：`test_accounts.py` 6 處、`test_pages.py` 1 處） |
| 前端 `npm test --prefix frontend` | 13 檔、190 個通過 |
| e2e `e2e.main_flow` 全套 | 42 個全部通過（#125 起的 2 個既有失敗已轉綠）；自審後擴大不重疊的檢查，該測試重跑通過 |
| `npm run build --prefix frontend`、`ruff check` | 通過；`ruff format --check` 只有 `docs/verification/issue-124.md` 不合格式，母分支上就是這樣，這次沒動 |

截圖工具固定的 8765 埠被本機另一個專案佔用，沒有停它；試驗時兩邊都暫時改成 8766 拍，拍完已還原。量測 200% 超出用的臨時腳本也已刪除。

## 自審

依 code-review 技能，以母分支 `feat/tailwind-migration` 為基準，Standards 與 Spec 分別由兩個子代理審查（只看 diff、規格與規範）。

- Standards：0 項硬性違規；7 項判斷題。
- Spec：class 換法數值逐條比過都正確，0 項要修；建議 2 項。

| 發現 | 處理 |
|---|---|
| 驗收條件 3「元件不重疊」只檢查按鈕（兩邊都提） | 已改：擴大到按鈕、輸入框和 `input-group` 的前後文字，重跑通過 |
| 文章外框加 `wrap-anywhere` 是新行為 | 本人已同意，列在上方「刻意的改動」，PR 說明也會列 |
| `field_messages.html` 也影響作答頁 | 列在上方「範圍與參考」；顏色同為 #000，作答頁畫面不變 |
| 家屬指南網址的 `wrap-anywhere` 和外框重複（會繼承） | 不改：它是原本 `text-break` 的一對一換名，外框那個是為了 200% 另外加的，各自拿掉都不影響另一個 |
| 隱私版本行的 `text-body` 沒有作用（本來就繼承本文色） | 不改：保留原本「次要文字」的標記，第 2a 階段改次要文字顏色時找得到 |
| `text-black` 沒做成有名字的 token | 不改：照 #125 處理 `#fff` 的做法，第 2a 階段改外觀時一起處理；`--color-emphasis` 這類名字也要先查會不會撞名（ADR 0009） |
| 新 e2e 的開瀏覽器步驟和 `open()` 很像 | 不改：`open()` 一定帶登入 cookie，這個測試要未登入、登入、未同意三種，改 `open()` 會動到其他 15 個測試 |
| 搜尋測試一行一行比，跨行的 `class` 會漏 | 不改：這幾頁沒有跨行寫法；記為限制 |

不需交叉審查：只改樣式 class，沒有修改計分、分級、門檻、資料 migration 或權限。

## 本人實際操作（2026-10-21 通過）

- [x] 首頁「開始篩檢」撐滿內容寬度（#126 驗收時發現的問題）。
- [x] 登入頁、同意書：兩個按鈕各佔一半、並排。
- [x] 註冊頁：「註冊」按鈕撐滿；欄位說明文字是黑色。
- [x] 隱私權說明、家屬指南、加到主畫面、帳號設定、刪除帳號：段落間距和之前一樣。
- [x] （可選）瀏覽器字級調大後，隱私頁 email、家屬指南英文出處會換行，不用左右捲動。
- [x] 接受上方「刻意的改動」第 1 項。
