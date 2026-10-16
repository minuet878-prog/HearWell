# Phase 6-4 網頁版作答連按兩次：實作計畫

規格：[phase6_web_double_submit.md](../specs/phase6_web_double_submit.md)

## 要改的檔案

| 檔案 | 改什麼 |
|---|---|
| `screening/views.py` 的 `screening` | GET 產生收據編號給頁面；POST 先查重複、存檔時帶編號 |
| `screening/templates/screening/screening.html` | 表單裡加隱藏的收據編號、看不見的狀態文字（給螢幕閱讀器）、載入按鈕回饋的 JS |
| `screening/static/screening/submit-button.js`（新增） | 按鈕「送出中…」、10 秒恢復、上一頁回來恢復 |
| `screening/templates/screening/layout.html` | 顯示 Django 內建「一次性訊息」（messages）的地方 |
| `screening/tests.py` | 新增 `WebDoubleSubmitTests`；`test_only_expected_scripts` 的作答頁預期多一支 JS |
| `frontend/src/submit-button.test.js`（新增） | 按鈕行為的測試（驗收 10–12） |

不改：資料庫（`Submission.idempotency_key` 和「同一人＋同一編號只能一筆」的限制，寫入 API 已經建好）、`AnswerFormSet`、API、React 作答頁。

## 伺服器端（`views.py`）

- **GET**：產生一個新的收據編號（UUID），放進頁面的隱藏欄位。每次打開作答頁都是新的（驗收 2）。
- **POST**：
  1. 讀隱藏欄位的收據編號；缺少或格式不對 → 當成沒有編號（驗收 9）
  2. 有編號、而且**這個人**已經有用這個編號的紀錄 → 不管答案是什麼，加一則一次性訊息，轉到那一筆的結果頁（驗收 1、7）。只查 `request.user` 自己的紀錄（規則 8，驗收 4）
  3. 沒有 → 照舊驗證；驗證沒過，重新顯示頁面時**沿用同一個編號**（驗收 3）
  4. 存檔時帶上編號（`formset.save(..., idempotency_key=key)`，既有的 `**extra` 參數就收得下）
  5. 兩個請求幾乎同時到（真的連點）：後到的那個會撞到資料庫的唯一限制 → 接住，改去找先存的那筆，一樣轉過去。寫法跟寫入 API 的 `post()` 相同
- 一次性訊息用 Django 內建的 messages（已經裝好、只是沒用過）：顯示一次就消失，重新整理就沒了，所以第一次正常送出不會有（驗收 8）

## 按鈕回饋（`submit-button.js`）

- 用一般的 `<script src defer>` 載入，**不經過 Vite 建置**：只有十幾行、不需要 React，IOI-HA 頁也要用
- 表單送出時：按鈕停用、文字改「送出中…」；看不見的狀態區（`role="status"`）寫入「送出中…」讓螢幕閱讀器念
- 10 秒後、或 `pageshow`（按上一頁從快取回到這頁）時：按鈕和狀態區恢復
- 沒有 JS 時這些都不會發生，伺服器端照樣擋（驗收 6）

## 一次性訊息放哪

放在 `layout.html` 的 `<main>` 最上面，一個地方就涵蓋 HHIE-S 和 IOI-HA 兩種結果頁。只有有訊息時才出現，其他頁面不受影響。

## 測試

| 驗收 | 測試 |
|---|---|
| 1 | 同一個編號送兩次（答案相同）→ 一筆、兩次都轉到同一筆 |
| 2 | 打開兩次作答頁 → 編號不同；各送一次 → 兩筆 |
| 3 | 漏答送出（頁面上的編號跟送出的一樣）→ 補好再送 → 一筆 |
| 4 | A、B 用同一個編號 → 各一筆；B 送出後轉到的是 B 自己的 |
| 5 | IOI-HA、HHIE-S、HHIA-S 各連送兩次 → 各一筆 |
| 6 | Django 測試本身就沒有 JS → 驗收 1 的測試即是證明 |
| 7、8 | 第二次答案不同 → 一筆、結果頁有說明文字；第一次 → 沒有 |
| 9 | 沒有編號、編號是亂碼 → 都照舊存檔 |
| 連點的競爭 | 模擬「查的時候還沒有、存的時候撞到限制」→ 轉到先存的那筆 |
| 10–12 | vitest＋jsdom＋假時鐘：按下 → 停用、文字、狀態區；9999 毫秒還停用、10000 毫秒恢復；`pageshow` 恢復 |
| 13 | 本人手機人工 |

既有測試要改一處：`test_only_expected_scripts` 的作答頁預期多一支 `submit-button.js`。
先寫測試、確認失敗，再改程式。
