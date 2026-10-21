# #125 Bootstrap 元件改成自己定義的有名字 class 驗證

日期：2026-10-21；分支 `feat/125-component-classes`；母分支 `feat/tailwind-migration`。
狀態：自動驗證完成，等本人實際操作驗收。沒有 push、開 PR 或合併回 `main`。

## 範圍與參考

- [#125](https://github.com/minuet878-prog/HearWell/issues/125)、母規格 #119、ADR 0008、ADR 0009。
- `frontend/src/site.css` 的元件層定義 27 個 class：按鈕一族 9 個、表單一族 9 個、`card`、`card-body`、`table`、`alert`、`alert-warning`、`alert-danger`、`visually-hidden`、`visually-hidden-focusable`、`list-unstyled`。模板、React、Python 都沒改。
- 數值照 Bootstrap 5.3.8 原始 CSS（#124 下載、核對過版本的那一份），再把舊 `styles.css` 對這些元件的覆寫（`btn-primary`、`btn-outline-primary` 的顏色、`.btn` 的最小尺寸與圓角、`.form-control:focus`）合進去。舊 `styles.css` 照分票留到 #126 刪除，那幾條覆寫在 #126 對照時直接對到這裡的定義。
- 只搬實際用到的部分：沒有 `btn-sm`、`form-switch`、`card-header`、驗證樣式、`table-striped` 等。用到的狀態（hover、focus、active、disabled、`fieldset:disabled` 裡的按鈕、勾選框勾選、日期欄位的內部排版）都有搬。

### 數值放哪裡

- 主題已有的數值直接引用：主色與 hover／active 色、本文色、`--color-border-subtle`、`--radius-button`、`--spacing-touch`、`--color-focus-ring`、`--shadow-input-focus`。
- 新增四個主題數值，給多個元件共用、網站從沒覆寫過的 Bootstrap 預設：`--radius-field`（0.375rem，欄位、卡片、提示框）、`--radius-field-lg`（0.5rem）、`--color-field-focus`（#86b7fe）、`--shadow-field-focus`。名稱已確認不會和模板裡的 class 撞名（ADR 0009）。
- 其餘 Bootstrap 預設色（按鈕各變體的紅、灰、淺色，勾選框的藍，提示框的黃與紅）直接寫在元件裡，沒有另外取 token：這些值只屬於該元件家族，第 2a 階段改外觀時會整組換掉；而且 `--color-danger`、`--color-secondary` 這類直覺的名字會生出 `.text-danger` 等和模板撞名的 class（ADR 0009）。`btn-outline-secondary` 的 #6c757d 剛好和 `--color-input-border` 同值，但用途不同，沒有共用。

### 刻意照舊、看起來像 Bootstrap 藍的地方

網站原本只改了部分顏色，下面這些在遷移前就是 Bootstrap 的藍色，這次照樣保留，沒有統一成主色（改外觀屬於第 2a 階段）：

- 下拉選單和勾選框取得焦點時的外框（#86b7fe）與光暈。
- 勾選框勾選後的底色（#0d6efd）。
- `btn-link` 的焦點光暈（rgba(49, 132, 253, 0.5)）。
- `btn-outline-primary` 停用時的文字與外框色（#0d6efd，例如 SSQ12 分數到 0 時的「減少 1 分」）。

## 本人決定（2026-10-21）

驗收條件 3 寫「按鈕與表單元件觸控區至少 44×44px」，但在遷移前的版本實際量到：一般大小的輸入框與下拉選單高 42.5px，聽力圖數值表的「遮蔽」勾選框 18×18px（包住它的整個標籤 166.5×27px 都可以點）。按鈕都在 49.5px 以上。

本人選擇**表單元件照遷移前的尺寸**，不在這次加大（WCAG AA 最小觸控尺寸 24×24px，現有尺寸都達到；44×44 是 AAA）。因此本票的驗收改成：按鈕至少 44×44px；表單元件尺寸和遷移前相同。加大表單元件留到第 2a 階段改外觀時一起處理。

## 怎麼確認「和遷移前一樣」

期望數字是依 Bootstrap 原始 CSS 推算的獨立數值，不是從新 CSS 抄來的。把同一組新測試放到遷移前的版本（`c229719`，與 `origin/main` 的版型和樣式相同，載入 Bootstrap CDN）跑：

| 版本 | 結果 |
|---|---|
| 遷移前 `c229719`（Bootstrap） | 新增 5 個瀏覽器測試＋`test_text_primary_and_error_colours`，6 個全部通過（自審後補的斷言也在參考版重跑通過） |
| 母分支 `28d3790`（本票之前） | 同一組 6 個中 6 個失敗（11 項子測試，只有「登出」按鈕本來就定義過所以通過） |
| 本分支 | 6 個全部通過 |

過程中參考版抓到兩個測試本身的問題，已修正：按鈕有 0.15 秒的顏色漸變，量太快會量到一半的值，所以 `StyleInBrowserTest` 改成在「減少動態效果」模式下量（`.btn` 等元件在這個模式下本來就沒有漸變）；「註冊」在導覽列也有一個，改成只在主要內容區找。

## 自動驗證

| 檢查 | 結果 |
|---|---|
| Django 全套 `manage.py test --settings=config.test_settings --noinput` | 644 個通過 |
| 前端 `npm test --prefix frontend` | 13 檔、189 個通過（含新的 `components.test.js` 2 個） |
| e2e `e2e.main_flow` 全套 | 40 個中 38 個通過；2 個是母分支既有的失敗，見下方 |
| `npm run build --prefix frontend`、Ruff | 通過 |
| CSS brotli | `site.css` 4,742 ＋ `styles.css` 5,489 ＝ **10,231 bytes**，上限 28,459 bytes |

「沒有多搬」的檢查不是空測試：暫時在 `site.css` 加一個沒用到的 `.btn-sm`，`components.test.js` 的第二個測試就失敗並列出 `btn-sm`；試驗後已還原。

## 驗收條件對照

| 條件 | 證明的測試與斷言 |
|---|---|
| 1. 列出的 class 用到的都有定義、沒用到的沒搬 | `frontend/src/components.test.js:41`（用到的都有定義）、`:46`（`btn`／`form-`／`input-group`／`card`／`table`／`alert`／`visually-hidden`／`list-` 開頭的定義都要有地方用到） |
| 2. #123 的顏色檢查（主要按鈕、文字色）通過 | `e2e/main_flow.py:1472`（登入按鈕底色是主色）、`:1478`（錯誤文字色），`test_text_primary_and_error_colours`（#124 記錄的預期失敗，現在通過） |
| 3a. 按鈕觸控區至少 44×44 | `e2e/main_flow.py:1209`，涵蓋 7 種按鈕（primary、outline-primary、outline-light、danger、link、outline-danger、停用的 outline-secondary） |
| 3b. 焦點外框和遷移前一樣 | 按鈕：`e2e/main_flow.py:1214`（每種按鈕的光暈顏色與 4.5px 寬，並確認是 `:focus-visible`）；輸入框：`:1263`–`:1264`；下拉選單：`:1310`；勾選框：`:1321` |
| 3c. 表單元件尺寸和遷移前相同（本人決定） | 輸入框 42.5px `:1249`、輸入框群組三段等高與接縫、下拉選單 42.5px `:1305`、勾選框 18×18 `:1312` 與標籤 27px、日期欄位與大號下拉選單 ≥ 44px（`test_form_fields_keep_their_size_and_focus_ring`，`:1237`） |
| 4a. 只給螢幕閱讀器的文字畫面上看不到 | `e2e/main_flow.py:1448`（1×1、絕對定位、裁切） |
| 4b. 螢幕閱讀器讀得到 | `e2e/main_flow.py:1461`（問卷卡片連結的名稱含隱藏的「，」） |
| 4c. `visually-hidden-focusable` 取得焦點時看得到 | `e2e/main_flow.py:1436`（未聚焦 1×1）、`:1441`（Tab 聚焦後大於 44×44、不再裁切） |

另外 `test_button_hover_and_press_colours`（`:1217`）量網站自己覆寫過的兩種按鈕（`btn-primary`、`btn-outline-primary`）滑過與按下的顏色；`test_cards_tables_alerts_and_lists_look_as_before`（`:1344`）量卡片、表格、兩種提示框、無樣式清單。

## 已知的既有失敗（不是本票造成）

`SharedLayoutTest.test_home_step_cards_stack_on_a_phone`、`SharedLayoutTest.test_phone_width_needs_no_sideways_scrolling`（`path='/'`）：首頁在 320px 寬時可以左右捲動到 491px。母分支 `28d3790`（沒有本票改動）單獨跑這兩個，同樣失敗、數值相同。首頁還在用 Bootstrap 的排版 class，屬於 #127–#129 的範圍；本票沒有查原因，也沒有修。#124 的驗證紀錄只跑了瀏覽器樣式測試，沒有記錄這兩個。

第一次跑 e2e 全套時另有 `NewUserScreeningTest` 兩個點擊逾時：當時同時跑了 Django 全套，兩邊用同一個測試資料庫名稱互相干擾。單獨重跑 `NewUserScreeningTest`（8 個）與再跑一次 e2e 全套都通過。

## 自審

依 code-review 技能，以母分支 `feat/tailwind-migration` 為基準，Standards 與 Spec 分別由兩個子代理審查（只看 diff、規格與規範）。

- Standards：0 項硬性違規；5 項可考慮。
- Spec：27 個 class 和 Bootstrap 原檔加舊覆寫逐條比過，數值一致、無範圍蔓延；1 項要修、3 項可考慮。

處理：

| 發現 | 處理 |
|---|---|
| 要修：勾選框的焦點外框沒有斷言 | 已補（`:1321`），參考版與本分支都通過 |
| 規格寫按鈕「含 hover、active…」，只量了主要按鈕 | 已補 `btn-outline-primary`（網站覆寫過的另一種）的滑過與按下；其他變體的狀態照 Bootstrap 原值，交給 #131 截圖比對 |
| `.btn:hover` 與 `.btn:focus-visible` 重複三行 | 已合併 |
| 驗證紀錄行號指到函式開頭、「只出現在單一元件」說法不精確 | 已修正 |
| 十六進位色沒抽成 token | 不改，理由見上方「數值放哪裡」；請本人確認 |
| `--radius-field` 也用在卡片、提示框 | 不改；token 旁的註解已寫明共用範圍 |
| `components.test.js` 的清單和前綴正則重複；清單外的 Bootstrap class 不會被抓 | 不改：本票範圍就是清單裡的 class；改成「前綴相符就要有定義」會把 `card-tag` 等 #126 才搬的自訂 class 誤判。HTML 的 `<table>` 標籤也算「有用到」，`.table` 本來就有用，影響不大 |
| e2e 裡「登出」的特例、大號按鈕期望值重複 | 不改，只有一處特例，抽常數得不到什麼 |
| 舊 `styles.css` 不在 CSS 圖層裡，會蓋過元件層 | 留給 #126：目前沒有互相衝突的規則，#126 搬舊規則時要留意 |

不需交叉審查：沒有修改計分、分級、門檻、資料 migration 或權限。

## 等本人實際操作

- [ ] 登入頁：按 Tab 到輸入框與「登入」按鈕，焦點外框看得到；滑過、按下按鈕顏色會變深。
- [ ] 註冊頁：出生年的「民國／年」框和輸入框接在一起。
- [ ] 新增聽力圖：「用數值輸入」裡的下拉選單和遮蔽勾選框；不標點直接存檔，出現紅色提示框。
- [ ] 每頁按 Tab，第一站「跳到主要內容」出現。
- [ ] 中間狀態的版面（首頁卡片、間距等）可能還不對，那是 #127–#129 的範圍。
