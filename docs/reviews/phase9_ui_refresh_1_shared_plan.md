# 前端設計重整 第 1 輪：實作計畫

規格：`docs/specs/phase9_ui_refresh_1_shared.md`（已確認）。第 4 步的計畫，等本人點頭才動手。

## 1. 寬度（4.1）— 只改 CSS

- `styles.css` 加一條 `.container { max-width: 40rem; }`。共用版型裡頁首、導覽列、主要內容、頁尾都用 `.container`，所以一行就全站生效；其他模板沒有用 `.container`（查過）。
  - Bootstrap 的 `.container` 在各寬度有自己的上限（540～1320px），寫在它的檔案裡；我們的 CSS 載入在後面、權重一樣，所以會蓋過去。
- 頁首、導覽列的底色本來就在外層（`.site-header`、`.site-nav`），會照樣滿版；內容自動對齊 40rem。
- 登入表單（30rem）、聽力圖輸入（32rem）比 40rem 窄，不受影響。

## 2. 頁尾（4.3）— 改共用版型＋CSS

- `layout.html` 的 `<footer>` 換成 `<footer class="site-footer"><div class="container">…</div></footer>`：三個連結、免責聲明、`mailto:` 信箱。還是 `<footer>` 標籤，所以既有的列印規則（聽力報告列印不印 `footer`）照樣有效。
- CSS：淺灰底、深灰字、上方間距 3rem、內距 1.5rem，說明文字小一級。
- 手機：現在是 `body` 底下留 5rem 給固定的分頁列，留白會是白色、接在灰色頁尾下面很突兀。改成把這 5rem 加在頁尾的下內距，灰色一路延伸到分頁列後面。
- `my_hearing.html` 拿掉「給家人看」連結。首頁不動。

## 3. 程度標籤（4.4）

- **對應表放 Python**（分級規則只用程式碼，規則 9）：`screening/audiogram.py` 加 `DEGREE_LEVELS`（正常→normal、輕度／中度→mild_to_moderate、中重度／重度／極重度→severe），用問卷分級已有的 level 名稱，顏色就能共用同一組 CSS。資料不足（`None`）→ unknown。
- `templatetags/custom_filters.py` 加一個 filter `degree_level`，模板裡把程度轉成 level 名稱。
- 新增 `templates/screening/level_badge.html`（一行：`<span class="level-badge level-badge-{{ level }}">{{ text }}</span>`），三頁都 include 它，樣子只寫一次。
- CSS `.level-badge` 和四個顏色（數值和結果頁色塊相同）。
- 套用：`my_hearing.html` 每筆分級（原本的 `text-{{ level|level_to_color }}` 文字顏色換掉）；`audiogram_list.html`、`audiogram_detail.html` 左右耳程度。
- `level_to_color` filter 換掉後就沒人用了：查證後一起刪（`scoring.get_color` 若也沒人用一併刪），避免留兩套顏色。

## 4. 可點擊卡片（4.5）

- CSS 新增 `.link-card`：整張是 `<a>`、flex 排列、右側 `<span class="link-card-arrow" aria-hidden="true">›</span>`、hover／active 淺藍底＋主色邊框、`:focus-visible` 外框。
- 三個模板改成同一種結構：
  - `questionnaire.html`：原本的 `stretched-link`（Bootstrap 讓連結蓋滿整張卡的作法）換成 `a.link-card`。
  - `my_hearing.html`：每筆變成 `a.link-card`，內容是日期、總分、助聽器、分級標籤（IOI-HA：日期、問卷名、常模組別）；拿掉「查看結果」按鈕。
  - `audiogram_list.html`：原本已經是 `<a class="card">`，改成 `a.link-card`＋箭頭＋標籤。

## 5. 按鈕層級（4.6）

- `my_hearing.html`：「聽力報告」`btn-primary` → `btn-outline-primary`。
- `report_share.html`：「產生分享連結」的 summary `btn-primary` → `btn-outline-primary`。

## 6. 間距（4.2）

- 新寫的 CSS 只用 0.25／0.5／1／1.5／3rem（頁尾手機下內距是 1.5＋5rem，5rem 是原本給分頁列的值）。
- 原本頁尾前的大空白來自 `main` 的下邊距＋舊頁尾按鈕的內距，換成新頁尾後一起消失。

## 7. 測試（先寫、先確認失敗）

- 新檔 `screening/tests/test_layout.py`（Django，看 HTML）：驗收 3–10。資料用 `test_report` 的假資料方法（在 class 裡引用，不在模組層級綁類別）。另外直接測 `DEGREE_LEVELS`／`degree_level`：六級＋資料不足的對應。
- `e2e/main_flow.py` 新增一個測試類別（自己開瀏覽器視窗）：
  - 驗收 1：1920px 寬，量主要內容寬度 ≤ 40rem（720px）、置中；頁首與頁尾寬度＝視窗寬。
  - 驗收 2：320px 寬，五頁的 `scrollWidth` 不大於視窗寬（不用左右捲）。
  - 驗收 11：聽力報告列印樣式下，頁尾、導覽列、分享區塊都看不到。
  - 資料：直接在測試資料庫建假帳號和紀錄，把登入 cookie 放進瀏覽器（不走註冊流程，省時間）。
- 既有測試要改的（因為規格改了畫面，不是放寬）：
  - `test_pages.py` `test_history_button_label`：原本斷言「查看結果」按鈕，改成斷言整張卡片連結（這個按鈕依規格拿掉）。
  - `e2e/main_flow.py` step6：原本用「查看結果」找卡片，改成找連到結果頁的卡片連結。
  - 其他（`test_consent.py` 頁尾隱私連結等）預期照樣通過。
- 驗收 12–14 人工：要你 `npm run build` 不需要（這輪沒改 React），只要 runserver 後看畫面、跑 axe。

## 8. 不做（照規格）

首頁內容、帳號設定頁、分段控制、圖表內部、列印樣式、主色字型字級、新增套件。

## 9. 驗證

- `python manage.py test --settings=config.test_settings`、`npm test --prefix frontend`、`npm run build` 後跑 e2e、`ruff check .`。
- 突變試驗：拿掉寬度那一行、把某一級的對應改錯，確認測試會失敗。
