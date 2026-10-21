# #138 頁首漸層與一個分頁只播一次的聲波驗證

日期：2026-10-22；分支 `feat/138-header-wave`（從 2a 功能分支開出，#139、#140 接著它開）；母分支 `feat/120-warm-shell`。
狀態：自動驗證完成，**等本人驗收**。子分支合回 `feat/120-warm-shell`；沒有 push、開 PR 或合併回 `main`。

## 範圍

- [#138](https://github.com/minuet878-prog/HearWell/issues/138)、母規格 #120、ADR 0006；聲波數值照 [`issue-136.md`](issue-136.md) 選定的 F。
- 頁首改成由上往下的漸層：#1f4e8c → #3a6bb0（設計數值 `--gradient-brand`）。App 版頁首用的是同一個元素。
- 聲波：版面模板直接寫 28 根長條，沒有 JavaScript 也看得到，並對螢幕閱讀器隱藏。
  - 長條各自跳動，同時有一道柔光掃過，約 3.7 秒後停成平坦一排。
  - 停住的樣子就是長條本來的樣式，所以「沒有動畫」時（減少動態效果、同一分頁的後面幾頁）直接是平坦一排。
- 一個分頁只播一次：頁面裡一小段 script，把「這個分頁播過了」記在 sessionStorage（瀏覽器每個分頁各自的暫存，關掉分頁就清掉）。
  - 第二頁起，在畫面畫出來之前就加上 `header-wave-played` 標記，CSS 看到標記就不播。
  - 沒有 JavaScript 時沒有這個標記，所以每頁都播，仍是 4 秒內停住。
- 和比較頁不同的地方：比較頁用 sin 函數算出 28 條各自不同的跳動高度；網站改成 7 組高度、5 種延遲輪流套用，所以每隔 7 條高度相同、延遲不同。

## 驗收條件對照

| 條件 | 證明 |
|---|---|
| 1. 頁首是由上往下的漸層、最上緣 #1f4e8c，聲波對螢幕閱讀器隱藏 | `e2e/main_flow.py:1875` `test_header_is_a_blue_gradient_with_a_hidden_wave`：首頁與問卷目錄，漸層值、`aria-hidden="true"`、28 根長條 |
| 2. 新分頁第一頁播、4 秒內停住；同一分頁換頁不播；開新分頁又播；沒有無限循環 | `:1887` `test_header_wave_plays_on_a_tabs_first_page_only`：第一頁動畫最晚 4000ms 結束，4.2 秒時沒有在播的動畫、28 根一樣高；換到下一頁時聲波沒有動畫；開新分頁又播一次；全頁沒有無限循環的動畫 |
| 3. 沒有 JavaScript 時頁首有長條，每頁都播並停成平坦一排 | `:1905` `test_header_wave_plays_on_every_page_without_javascript`：同一分頁連開兩頁都播、都停平。開著 JavaScript 時第二頁不會播，所以這個測試分得出差別 |
| 4. 減少動態效果時頁面沒有任何動畫 | `:1913` `test_reduced_motion_keeps_the_header_still`：全頁 0 個動畫、長條仍在 |
| 5. 手機與桌機的頁首排法和 #118 相同；聲波是比較頁選的那一種 | 既有 `:972` `test_logout_shares_the_first_header_line_on_phones`、`:994` `test_header_is_one_line_on_wide_screens` 照樣通過。截圖：全站對照頁 `e2e-artifacts/shots/140-diff/gallery.html`（不進版控），每頁的頁首都是停住後的平坦一排 |

圖表裁切和 `main` 比對：和 #137 已接受的 5 張相同差異，沒有新增（見 [`issue-137.md`](issue-137.md)）。

## 連帶修改的測試

每頁多了一段頁面內 script，以下兩個既有測試跟著改：

- `screening/tests/test_pages.py` 的 `test_only_expected_scripts`：每頁的 script 清單多了這一段。檢查方式從「有沒有頁面內 script」改成「有幾段」，作答頁原本那段才不會被聲波這段蓋過去。
- `screening/tests/test_answering.py` 的 3 個判斷：原本用「頁面有沒有 `<script>`」代表作答頁那段，改成找內容提到 `answer-loading` 的那段。
  - 我在 #138 commit 前只跑了頁面測試，第一個 commit（`91aa471`）是在這 3 個測試失敗的狀態下 commit 的，下一個 commit 修好。之後改成全套通過才 commit。

## 自動驗證（#138–#140 一起跑）

| 檢查 | 結果 |
|---|---|
| Django 全套 | 646 個通過 |
| 前端 | 13 檔、190 個通過（含 CSS 下載量上限） |
| e2e `e2e.main_flow` | 60 個通過（#138 新增 4 個、#139 新增 4 個、#140 新增 3 個） |
| `ruff check .`、`ruff format --check .` | 通過 |

## 自審（#138–#140 一起）

`/mattpocock-skills:code-review`，基準 `feat/120-warm-shell`，Standards 與 Spec 各由一個子代理審查。

- Standards：1 項硬性違規；判斷題 7 項。
- Spec：2 項要修；判斷題 6 項。

| 發現 | 處理 |
|---|---|
| 主要按鈕按下的深藍寫死，主題已有同值（Standards，硬性） | 已改引用 `--color-primary-hover` |
| 焦點框和光暈分不出來，測試只比兩個寫死的常數（Spec，要修） | 本人 2026-10-22 看過對照圖，選「柔和光暈」；測試改讀頁面實際值。詳見 [`issue-139.md`](issue-139.md) |
| 聽力圖符號按鈕不是膠囊形（Spec，要修） | 規格衝突：#120 明文把它列在中圓角 0.75rem，#137 照做並驗收；#139 寫「所有按鈕一律膠囊形」。保留中圓角，當成 #120 明列的例外，測試註明 |
| 同一個漸層寫了 7 次（Standards） | 改成設計數值 `--gradient-brand` |
| 主要按鈕的舊變數被新寫法蓋掉（Standards） | 邊框與停用顏色改由按鈕變數設定，刪掉被蓋掉的寫法 |
| 對比斷言比的是常數（Standards） | 改讀元素實際的文字色與背景 |
| 停用狀態的內框沒驗（Spec） | 已補 |
| e2e 另寫一個幾乎和 `open()` 相同的函式；漸層字串重複（Standards） | `open()` 加 `motion` 參數；常數移到 class 開頭 |
| 柔光掃過長條時對比短暫降低（Standards） | 寫進 CSS 註解；#136 已記錄、本人知情 |
| 導覽項目新增滑過變藍（Spec，範圍） | 保留：#140「滑過、按下只變色」，原本滑過沒有任何變化。見 [`issue-140.md`](issue-140.md) |
| 7 組高度輪替、減少動態效果只測首頁、換頁只查聲波的動畫（Spec，判斷題） | 不改：記在上方範圍；全站沒有其他動畫 |
| 模板用 28 個字的字串跑迴圈產生長條（Standards，判斷題） | 不改：旁邊有註解寫明 28 根 |
| 比較頁的新色碼直接寫（Standards，判斷題） | 不改：照 #136 紀錄的值，檔案裡已有直接寫顏色的前例 |

不需交叉審查：只改樣式、版面模板裡的裝飾和測試，沒有修改計分、分級、門檻、資料 migration 或權限。

## 本人實際操作（待驗收）

- [ ] 新開分頁進首頁：聲波跳動約 4 秒後停成平坦一排；換到其他頁不再播；開新分頁又播。
- [ ] 手機與桌機：頁首排法和以前一樣，文字清楚。
