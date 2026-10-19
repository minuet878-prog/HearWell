# 實作計畫：寫入 API（作答送出）

規格：[phase5_api_submit.md](../../specs/phase-05/phase5_api_submit.md)　分支：`feat/api-submit-answers`

## 動到的檔案

| 檔案 | 改什麼 | 為什麼 |
|---|---|---|
| `screening/models.py` | `Submission` 加 `idempotency_key`（UUID、可空），加唯一限制「同一個 user ＋ 同一個編號」 | 收據編號存在作答紀錄上；資料庫層擋「兩個請求同時到」。舊紀錄是空值，PostgreSQL 的唯一限制不比對空值，不受影響 |
| `screening/migrations/0018_…` | 上面那個欄位的 migration | 只新增可空欄位＋限制，不改舊資料 |
| `screening/forms.py` | `BaseAnswerFormSet` 加 `save(user, questionnaire, **extra)`：在交易（全有或全無）裡建 `Submission` ＋ 一次存所有答案 | 網頁版 view 現在就有這段程式；搬進 formset，網頁和 API 共用同一份存檔邏輯 |
| `screening/views.py` | 作答 view 改呼叫 `formset.save(...)`，**行為完全不變**（既有測試照跑當證據） | 同上。規格「不做」寫的是不改網頁行為；這是搬程式碼、不是改行為，先跟你說 |
| `screening/api/serializers.py` | 新增 `QuestionnaireDetailSerializer`（題目＋選項）、`SubmissionCreateSerializer`（收請求、把答案轉給 `AnswerFormSet` 驗證、錯誤轉成依欄位分開的中文訊息） | 驗證放 form 層：serializer 只檢查 JSON 形狀（是不是數字、是不是陣列），題目對不對、分數合不合法都交給既有的 formset |
| `screening/api/views.py` | `QuestionnaireDetail`（排除 IOI-HA）；`SubmissionList` 加 `post`：檢查收據編號 → 驗證 → 查「自己用過這個編號嗎」→ 存檔或回傳舊的／409；存檔撞到唯一限制時（同時到）改走「用過」那條路 | 收據編號流程集中在這裡 |
| `screening/api/urls.py` | 加 `questionnaires/<int:pk>/` | 4.1 |
| `docs/api/schema.yaml` | 重新產生 | 驗收「schema 和檔案一致」 |
| `screening/tests.py` | 新增 `ApiSubmitTests`、`ApiQuestionnaireDetailTests`，26 條驗收各至少一個測試 | 第 5 步：先寫、先確認失敗 |

收尾時另外更新：`docs/roadmap.md`、本規格的完成後回報、`docs/specs/phase-00/phase0_dev_checks.md`（驗收 1、10、11 打勾、狀態改「已完成」，上次說好下次分支一起補）。

## 幾個實作細節

1. **答案順序**：規格說「順序不限」，但 formset 是用「第幾個表單 ↔ 第幾題」配選項的（之前記過的 F-6 位置耦合）。所以 API 先把答案依題號排好再交給 formset。HHIE-S／HHIA-S 每題選項一樣，不排也不會錯，但排了才不會在將來埋雷。
2. **錯誤訊息**：formset 的錯誤會放在 `answers` 底下（例如「有題目沒有作答」「表單資料有誤，請重新確認每一題的作答」）。`wearing_hearing_aid` 的訊息直接取網頁版表單上那一句，不另抄一份文字。問卷不存在／IOI-HA 用 DRF 的中文預設訊息（「無效的主鍵…」之類）。
3. **檢查順序**：登入／CSRF（DRF 自動）→ 收據編號格式 → 內容驗證 → 比對用過的編號。內容不合法時一律 400，不管編號用過沒。
4. **「同樣內容」的比對**：問卷 id、wearing_hearing_aid、`{題目 id: 分數}` 三樣都一樣才算重送。
5. **回傳**：201／200 都用單筆結果 API 的同一個查詢與 serializer 產生，保證和 GET 一模一樣。
6. **中途失敗測試**：讓「存答案」那一步故意丟錯誤，確認作答紀錄也沒留下。
7. **同時到的測試**：模擬「查的時候還沒有、存的時候已經有」，確認回的是舊那筆而不是 500。

## 不會做的事

不改網頁版作答行為、不新增套件、不碰 IOI-HA 的寫入、不改單筆結果 API 的輸出格式。
