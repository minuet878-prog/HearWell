# #126 網站自訂 class 搬到 Tailwind 元件層驗證

日期：2026-10-21；分支 `feat/126-custom-classes`；母分支 `feat/tailwind-migration`。
狀態：自動驗證完成，等本人實際操作驗收。沒有 push、開 PR 或合併回 `main`。

## 範圍與參考

- [#126](https://github.com/minuet878-prog/HearWell/issues/126)、母規格 #119、ADR 0008、ADR 0009。
- 舊 `styles.css`（1141 行）的規則搬進 `frontend/src/site.css` 最後一個 `@layer components` 區塊：名稱、選擇器、順序、所在 media query 都照舊；顏色、圓角、陰影、觸控尺寸、表單寬度改引用主題 token，只有 `#fff` 和圓形的 `50%` 照寫。
- 依資料拼接的 class 直接寫在區塊裡，不靠掃描：`level-badge-*`、`result-banner-*`（四種分級代碼）、`ear-right`／`ear-left`、`compare-legend-left`。
- 舊 `styles.css` 已刪除，`layout.html` 不再載入。
- **選擇器對照清單**：[`issue-126-mapping.md`](issue-126-mapping.md)（176 列，PR 說明會附上）。

### 新增的主題 token

| token | 值 | 用在 |
|---|---|---|
| `--color-ear-right`／`--color-ear-left` | #c0392b／#1f4e8c | 聽力圖符號按鈕、左右耳結果卡片上緣、比較圖例實線 |
| `--color-ear-right-old`／`--color-ear-left-old` | #e8a59d／#9db5d6 | 比較圖例虛線 |
| `--color-masking` | #b35900 | 遮蔽開關（開）與圖表虛線框 |
| `--radius-small` | 0.25rem | IOI-HA 說明框、常模帶、趨勢圖色塊、報告分級框、聽力圖縮圖 |

左耳藍和主色同值，但另取名字：左藍右紅是聽力圖慣例，第 2a 階段換主色時不該跟著變。名稱都查過不會生出模板裡用到的 class（ADR 0009）。

## 刻意的改動（本人 2026-10-21 接受第 1、2 項）

1. **沒搬 `.text-success`、`.text-warning`、`.text-secondary`**：模板、React、Python 都沒有用到（roadmap 原本就記著「可能已沒人用，確認後再清」）。`.text-danger` 有 8 處在用，照搬，連 `!important` 一起（「刪除帳號」這種 `btn-link` 滑過時才不會變藍）。
2. **`layout.html` 導覽清單加 `px-0`**：舊的 `.site-nav ul { padding: 0 }` 不在圖層裡，蓋得過 Bootstrap 的 `.container`。現在 `container` 是 Tailwind 的 utility，utilities 圖層一定蓋過 components 圖層，導覽清單會多出左右各 13.5px 的內距。只載入建置後 `site.css` 的最小頁面實測：沒有 `px-0` 是 13.5px，有 `px-0` 是 0（遷移前的值）。
3. **`@page { margin: 1.5cm }` 放在圖層外**：它是列印頁面的規則，不是元素樣式，放進圖層沒有意義。
4. `.ssq-scale > label:last-child` 的 `gap: .5rem` 寫成 `0.5rem`，跟檔案其他地方一致，數值相同。

延後的引用：`AGENTS.md:89` 還寫著 Bootstrap 與 `styles.css`。#119 規定 `AGENTS.md` 在合併時同步改成 Tailwind（#131），這張票不動。`docs/accessibility/accessibility_baseline.md` 與舊驗證紀錄提到 `styles.css` 是歷史紀錄，不改。

## 怎麼確認「和之前一樣」

**逐條比對數值**：用 postcss 把新舊 CSS 拆成「media query ＋ 選擇器 → 屬性值」，新檔的 `var(--token)` 換回主題數值後比較，也檢查新檔沒有多出屬性。舊檔 176 組裡 165 組相同；7 組由 #124／#125 接手；3 組沒人用沒搬；`.ssq-scale` 那條只差 `.5rem`／`0.5rem` 的寫法。反過來，新區塊 167 個選擇器 = 165 組相同的 + `.text-danger` + `.ssq-scale`，沒有多搬。

**全站截圖**（#122 的工具）：比對本票之前的母分支 `8716467`（舊檔還在、不在圖層裡）和本分支，364 張。

| 比對 | 結果 |
|---|---|
| `8716467` → 本分支 | 363 張相同；首頁（未登入、390 寬）11 個像素不同 |
| 本分支 → 本分支再拍一次（public 群組） | 同一張首頁也是 11 個像素不同 |
| `8716467` → 本分支再拍的那次（public 群組） | 26 張全部相同 |

那 11 個像素在「開始篩檢」按鈕右端圓角，是 #125 記錄的 `w-100` 按鈕超出畫面（右緣在 491px）時邊緣反鋸齒不穩定，同一個 commit 拍兩次就會不同。所以 364 張都和本票之前一樣，字型與基礎字級也零差異。

截圖工具固定用的 8765 埠被本機另一個專案（Newborn Hearing Screening 的 uvicorn）佔用，沒有停它；試驗時兩邊都暫時改成 8766 拍，拍完已還原。母分支是用暫時的 worktree 拍的，拍完已移除。截圖在 `e2e-artifacts/shots/pre-126`、`126`、`126-again`（不進版控）。

## 自動驗證

| 檢查 | 結果 |
|---|---|
| Django 全套 `manage.py test --settings=config.test_settings --noinput` | 645 個通過（多了 `test_old_stylesheet_is_deleted`） |
| 前端 `npm test --prefix frontend` | 13 檔、190 個通過 |
| e2e `e2e.main_flow` 全套 | 41 個中 39 個通過；2 個是 #125 已記錄的既有失敗（首頁 320px 寬時可以捲到 491px，`w-100` 屬於 #127），數值相同 |
| `npm run build --prefix frontend`、Ruff | 通過 |
| CSS brotli | `site.css` **7,422 bytes**（之前 `site.css` 4,742 ＋ `styles.css` 5,489 ＝ 10,231），上限 28,459 |

先紅後綠：拿掉 `layout.html` 的 `styles.css`、還沒搬規則時，新的徽章測試四種分級全部失敗（例如「正常」量到主色 rgb(31, 78, 140)，不是 rgb(30, 123, 85)），`components.test.js` 的新測試也失敗；搬完後都通過。徽章測試在舊檔還在時先跑過一次，確認通過，表示期望值是遷移前的樣子。

## 驗收條件對照

| 條件 | 證明 |
|---|---|
| 1. 舊檔每個選擇器都有對應、數值相同 | [`issue-126-mapping.md`](issue-126-mapping.md)（程式逐條比對，176 列）；全站截圖 364 張和本票之前相同（上方）；依資料拼接的 class 有定義：`frontend/src/components.test.js:58` |
| 2. 四種分級的徽章與結果橫幅通過顏色檢查 | 橫幅：`e2e/main_flow.py:1507`（文字色）、`:1508`（底色，自審後把「無法判讀」的底色也納入）；徽章：`:1525`（文字色）、`:1526`（底色）。「無法判讀」的徽章在聽力圖檢視頁量（沒有點的聽力圖，兩耳都是「資料不足」），其他三種在「我的紀錄」量 |
| 3. 健康報告模擬列印通過列印檢查 | `e2e/main_flow.py:1548` 起：頁首、導覽、頁尾、列印按鈕都隱藏，`:1570` 報告裡沒有陰影；另有 `test_report_print_hides_footer_nav_and_sharing`（`:641`） |
| 4. 舊檔已刪除、沒有引用 | `screening/tests/test_pages.py:919`（靜態檔案找不到）、`:915`（每一頁都沒有連到它）；`AGENTS.md` 延後到 #131，見上方 |

## 自審

依 code-review 技能，以母分支 `feat/tailwind-migration` 為基準，Standards 與 Spec 分別由兩個子代理審查（只看 diff、規格與規範）。

- Standards：0 項硬性違規；5 項判斷題。
- Spec：數值與順序逐條比過一致；指出 4 項（含驗收條件 1 還沒有清單）。

| 發現 | 處理 |
|---|---|
| 驗收條件 1 沒有對照清單 | 已補 `issue-126-mapping.md` |
| 「無法判讀」橫幅的底色沒有斷言（#123 原本略過） | 已補；徽章測試改用同一組數值 |
| 三個文字色 class 沒搬、`px-0` 改模板、`AGENTS.md` 還提到舊檔 | 列在上方「刻意的改動」與「延後的引用」；本人接受前兩項，`AGENTS.md` 留到 #131 |
| `--radius-small` 照大小命名，其他圓角 token 照用途 | 不改：五個用到的地方（說明框、色塊、常模帶、分級框、縮圖）沒有共同用途，照大小命名才誠實；不用 Tailwind 內建的 `--radius-sm`，數值只定義在 `@theme` 一處 |
| 耳朵顏色同時寫在 token、`AudiogramChart.jsx`、`audiogram_thumbnail.html` | 不改：本票之前就是這樣（SVG 屬性用不到 CSS 變數），token 旁註解已寫明；要共用另開票 |
| `#fff` 出現約 20 次沒做成 token | 不改：照 #125 的做法，第 2a 階段改外觀時一起處理 |
| `components.test.js` 的分級代碼和 Python 各一份 | 不改：跨語言，新增分級時兩邊一起改 |

不需交叉審查：只改樣式，沒有修改計分、分級邏輯、門檻、資料 migration 或權限。

## 本人實際操作（待驗收）

- [ ] 首頁、問卷目錄、我的紀錄：卡片、分頁籤、分級徽章、趨勢摘要框和之前一樣；滑過卡片會變淡藍。
- [ ] 作答頁：大選項按鈕選中時有外框和底色。
- [ ] 結果頁：橫幅顏色（可看任一種分級）。
- [ ] 新增聽力圖：左右耳符號按鈕、遮蔽開關按下變橘色、圖表出現橘色虛線框。
- [ ] 聽力報告：按「列印或存成 PDF」，預覽沒有頁首、導覽、頁尾。
- [ ] 手機寬度：底部導覽列照舊，圖示和字沒有往內縮。
- [x] 接受上方「刻意的改動」第 1、2 項（2026-10-21）。
