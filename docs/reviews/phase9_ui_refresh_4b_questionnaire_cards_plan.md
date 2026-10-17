# 4b 問卷卡片與選擇引導：實作計畫

規格：`docs/specs/phase9_ui_refresh_4b_questionnaire_cards.md`（已確認）。第 4 步的計畫，等本人點頭才動手。

## 1. 順序（4.1、驗收 5）

- `screening/views.py` 的 `questionnaire_list`：查出來後在 Python 裡排序。
  - 排序規則：先照一個寫明的清單 `LIST_ORDER = ("hhie-s", IOI_HA)`，不在清單裡的問卷排在後面，再照編號（建立先後）。
  - 清單放在 view 旁邊：這是畫面順序，不是計分規則，所以不放進 `scoring.py`。
  - 不改 model 的預設排序：其他地方，例如 API、我的紀錄的分頁，各有自己的排序，這次不碰。

## 2. 模板（`templates/screening/questionnaire.html`）

- 標題下加引導說明框。
- 每張卡片：
  - `link-card` 裡最前面放圖示 `<span class="questionnaire-icon" aria-hidden="true">`。
  - 標題。
  - 適合對象，有的話才顯示。
  - 標籤列：`N 題`，有時間資料時再加 `約 M 分鐘`。
- 新增 `templates/screening/questionnaire_icon.html`：依問卷代碼畫三種 inline SVG（耳朵、助聽器、夾板）。夾板沿用導覽列「開始篩檢」的那個圖示。
- 作答頁上的「共 N 題，大約 M 分鐘。」不動（規格只改選擇頁）。

## 3. CSS（`styles.css`）

- `.questionnaire-guide`：淺藍底＋左側深藍粗線，跟趨勢圖的摘要框同一種樣子。
- `.questionnaire-icon`：3rem 圓形淺藍底，裡面的 SVG 是深藍線條。
- `.card-tags`／`.card-tag`：灰底圓角小標籤，可以換行。

## 4. 測試（先寫、先確認失敗）

- 新檔 `screening/tests/test_questionnaire_cards.py`，對應驗收 1–5。
  - 第 5 條的測試資料故意先建 IOI-HA、再建 HHIE-S、最後建另一份。
  - 檢查圖示時，用 `data-icon` 屬性分辨是哪一種，並確認有 `aria-hidden`。
- 驗收 6：沿用 e2e 既有的 320px 檢查。選擇問卷頁本來就在受檢的頁面清單裡，不用另外加。
- 既有測試要跟著改的有兩個，都在 `test_pages.py`：
  - `test_questionnaire_list_shows_info`：「共 10 題，大約 3 分鐘。」這句改成兩個標籤。
  - `test_question_count_is_not_hard_coded`：選擇頁這部分改成檢查「3 題」標籤；作答頁那部分不變。

## 5. 不做

依年齡推薦、新增問卷、改作答頁、4a／4c／4d。

## 6. 驗證

Django、前端、build 後跑 e2e、`ruff check .`。突變試驗：把排序拿掉，確認驗收 5 的測試會失敗。
