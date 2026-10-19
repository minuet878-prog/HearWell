# Phase 5 規格：寫入 API（作答送出）

- **狀態**：已完成
- **分支**：`feat/api-submit-answers`
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-15

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

讓程式（之後的 React 作答頁）可以透過 `/api/` 送出一份問卷的作答，由後端驗證、存檔、算好分數與分級後回傳。網路不穩、使用者連按兩次時，**不會存成兩筆**。現有的作答網頁完全不動。

## 2. 範圍

### 要做
- 送出作答：`POST /api/submissions/`。
- 防止重複送出：收據編號（Idempotency-Key），必填（待決 2、3）。
- 取得單一問卷的題目與選項（待決 4）。
- 驗證規則與網頁版**同一份**：漏題、重複題、別份問卷的題目、不合法的分數、沒選有沒有戴助聽器，都要擋。
- 更新 API 文件（OpenAPI schema 檔）。

### 不做
- React 作答頁、作答中途儲存（D2）：之後的任務。
- 修改現有的作答網頁或它的行為（包括網頁版的連按兩次問題，F-10）。
- 修改、刪除已送出的作答（PUT／PATCH／DELETE）。
- IOI-HA 透過 API 作答或讀題目（待決 1）。
- 流量限制（rate limiting）、API 版本號、token／JWT、CORS。
- 新增套件。

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本任務特別注意：
  - **IDOR**（第 8 條）：作答一律存在 `request.user` 底下，請求裡不能指定使用者；別人用過的收據編號（見 4.2）不能讓我看到別人的紀錄。
  - **計分單一路徑**（第 10 條）：回傳的分數與分級走 `Submission` 的計分方法，不另寫。
  - **驗證放在 form 層**（架構方向）：API 和網頁共用同一套驗證，不在 API 另寫一份規則。
  - **0 是合法分數**（第 11 條）：每題都選「從未」的作答，總分 0，是正常的一筆。
  - **全有或全無**：存檔過程中任何一步失敗，不能留下半份作答（沒有題目的 submission、只存一半的答案）。

## 4. 行為描述

共通（沿用 Phase 3）：
- 未登入 → 403 JSON，不轉址。
- 已登入但沒有帶 CSRF token → 403（session cookie 認證的標準防護：CSRF 是「別的網站偷用你的登入狀態幫你送表單」，token 證明請求真的來自本站頁面）。
- 時間一律 ISO 8601、台北時區。

### 4.1 取得問卷題目 `GET /api/questionnaires/{id}/`

| 項目 | 內容 |
|---|---|
| 誰可以使用 | 未登入：403　　已登入：可以　　能否存取他人資料：不適用（問卷是共用的） |
| 回傳 | 問卷列表那一筆的欄位（id、code、name、levels），加上 `questions` |
| 每一題 | `{"id": 12, "number": 1, "text": "題目全文", "choices": [{"value": 4, "label": "常常"}, {"value": 2, "label": "有時"}, {"value": 0, "label": "從未"}]}`，依題號排序 |
| **不能**回傳 | 題目分類（情緒／社交）、任何作答紀錄 |
| 不存在或 IOI-HA | 404 |

### 4.2 送出作答 `POST /api/submissions/`

| 項目 | 內容 |
|---|---|
| 誰可以使用 | 未登入：403　　已登入：存在自己底下　　能否替他人送出：不能 |
| 請求內容 | 見下方 JSON；header 帶 `Idempotency-Key: <UUID>`（收據編號） |
| 成功 | 201，內容和「單筆結果」`GET /api/submissions/{id}/` 完全一樣（分數、分級、行動建議、每題作答） |
| 重複送出（同一個人、同一個收據編號、同樣內容） | 200，不新增，內容是第一次存的那一筆 |
| 同一個人、同一個收據編號、內容不同 | 409，`{"detail": "這個收據編號已經用過"}`，什麼都不存 |
| 沒帶收據編號、或不是 UUID 格式 | 400，`{"detail": "缺少或無效的收據編號"}`，什麼都不存 |
| 別人用過的收據編號 | 跟沒用過一樣，正常新增在自己底下（編號只在同一個人之內比對） |
| 驗證失敗 | 400，依欄位分開的中文訊息，文字沿用網頁版（form 層），例如 `{"answers": ["有題目沒有作答"]}`、`{"wearing_hearing_aid": ["請選擇這次有沒有戴助聽器"]}`；不逐題標出；什麼都不存 |
| 問卷不存在、IOI-HA、沒有題目 | 400，什麼都不存 |
| 需要計算的資料 | 由誰計算：後端　　計算路徑：`Submission` 的計分方法 |

請求內容：

```json
{
  "questionnaire": 1,
  "wearing_hearing_aid": false,
  "answers": [
    {"question": 12, "score": 4},
    {"question": 13, "score": 0}
  ]
}
```

- `answers` 必須剛好是這份問卷的每一題各一次，順序不限。
- `wearing_hearing_aid` 必填（跟網頁版一樣），只接受 true／false。
- 「同樣內容」＝同一份問卷、同樣的 wearing_hearing_aid、同樣的每題分數（順序不限）。
- 收據編號由前端在開始作答時產生（瀏覽器內建 `crypto.randomUUID()`），重送時沿用。

## 5. 驗收條件

### 送出作答

- [x] 假設未登入，當 POST 一份完整作答，則回 403，資料庫沒有新增任何紀錄。
- [x] 假設已登入但沒帶 CSRF token，當 POST 一份完整作答，則回 403，沒有新增紀錄。
- [x] 假設已登入，當 POST 一份 HHIE-S 完整作答（含 wearing_hearing_aid），則回 201，資料庫多一筆屬於自己的作答、每題一列答案，回傳的總分與分級和「我的紀錄」頁顯示的一樣。
- [x] 假設已登入，當 POST 一份每題都是 0 分的作答，則回 201，總分是 0、分級是最輕的那一級（不是「無法判讀」、不是 null）。
- [x] 假設已登入，當請求裡夾帶 `"user": 別人的 id`，則作答仍然存在自己底下（多出的欄位被忽略）。
- [x] 假設已登入，當漏答一題，則回 400，錯誤訊息指出有題目沒有作答，什麼都不存。
- [x] 假設已登入，當同一題出現兩次，則回 400，什麼都不存。
- [x] 假設已登入，當答案裡混入別份問卷的題目，則回 400，什麼都不存。
- [x] 假設已登入，當某題的分數不是該題的選項（例如 HHIE-S 給 3），則回 400，什麼都不存。
- [x] 假設已登入，當沒給 wearing_hearing_aid（或給 null、1、"yes"、"true" 等不是 JSON true／false 的值），則回 400，什麼都不存。
- [x] 假設已登入，當問卷 id 不存在，則回 400，什麼都不存。
- [x] 假設已登入，當問卷沒有任何題目、answers 是空陣列，則回 400（「這份問卷沒有題目」），什麼都不存（審查補上：4.2 表格有寫、這裡漏列）。
- [x] 假設存答案的過程中途失敗，則資料庫不留下半份作答（作答紀錄和答案都沒有新增）。
- [x] 假設已登入，當用 GET 讀 schema，則 schema 裡有送出作答的請求與回應格式，且和 repo 裡的 schema 檔一致。
- [x] 假設已登入，當 PUT／PATCH／DELETE `/api/submissions/{id}/`，則回 405。

### 收據編號（防重複）

- [x] 假設已登入，當同一個收據編號、同樣內容送兩次，則第二次回 200、內容和第一次一樣（同一個 id），資料庫只有一筆作答。
- [x] 假設已登入，當同一個收據編號、但答案不同（或問卷不同、wearing_hearing_aid 不同）再送，則回 409，資料庫仍只有第一筆，答案沒有被改。
- [x] 假設已登入，當沒帶收據編號、或編號不是 UUID，則回 400，什麼都不存。
- [x] 假設使用者 B 用過某個收據編號，當使用者 A 用同一個編號送出，則 A 回 201、存在 A 底下，回應裡沒有任何 B 的資料。
- [x] 假設兩個請求同時帶同一個收據編號（第二個在第一個存好之前通過檢查），則資料庫層擋下第二個，最後只有一筆，第二個請求不回 500。

### 回傳內容

- [x] 假設送出成功，則 201 的內容和接著 GET `/api/submissions/{新 id}/` 的內容完全一樣。
- [x] 假設驗證失敗，則 400 的錯誤依欄位分開（`answers`、`wearing_hearing_aid` 等），訊息是中文，不是英文的 DRF 預設訊息。

### 取得問卷題目

- [x] 假設未登入，當 GET `/api/questionnaires/{HHIE-S id}/`，則回 403。
- [x] 假設已登入，當 GET `/api/questionnaires/{HHIE-S id}/`，則回 200，含 id、code、name、levels，以及依題號排序的每一題（id、number、text 全文、choices：常常 4／有時 2／從未 0）；沒有題目分類。
- [x] 假設已登入，當 GET 不存在的問卷 id 或 IOI-HA 的 id，則回 404。
- [x] 假設已登入，當用 4.1 拿到的題目 id 和選項值組成作答送出，則回 201（兩支 API 接得起來）。
- [x] 假設已登入，當送出 IOI-HA 的作答，則回 400，什麼都不存。

## 6. 待決問題

> 2026-10-15 本人確認：六題都照建議（A）。答案已寫回第 2、4 節。

- [x] ~~**1. 哪些問卷可以用 API 送出？**~~
  - A（建議）：只有 HHIE-S、HHIA-S。唯讀 API 現在也只回這兩份；IOI-HA 送出時要另外做「常模分組」，結果格式也不同，等真的要做 React 版 IOI-HA 時再加。IOI-HA 送來回 400。
  - B：三份都可以。代價：這次就要處理 IOI-HA 的分組與不同的回傳格式，範圍變大一倍。

- [x] ~~**2. 怎麼防止「連按兩次存成兩筆」？**~~
  - A（建議）：**收據編號**（業界叫 Idempotency-Key，「冪等」＝同一件事做幾次結果都一樣）。前端開始作答時產生一組隨機編號，送出時附上；網路斷了重送也帶同一組。伺服器看到「同一個人、用過的編號」就直接回傳上次那筆，不新增。資料庫層也擋（兩個請求同時到也只會成功一個）。代價：作答紀錄要多存一個欄位（要做 migration）。
  - B：只靠前端把按鈕停用。代價：網路慢、使用者重新整理、手機斷線重送時擋不住，趨勢圖會出現兩個一樣的點。
  - C：伺服器比對「幾秒內、同一份問卷、答案一模一樣」就當重複。代價：靠猜，真的連續做兩次同樣答案的人會被誤擋；秒數怎麼訂也沒有根據。
  - 選 A 的話，追問：沒帶編號的請求怎麼辦？建議**回 400**（必填）：現在只有我們自己的前端會呼叫，必填可以確保每一筆都受保護。

- [x] ~~**3. 同一個收據編號、但內容不一樣（不同答案或不同問卷）？**~~（待決 2 選 A 才需要）
  - A（建議）：回錯誤（409，「這個編號已經用過」），什麼都不存。這通常代表前端有 bug，安靜地回傳舊結果會讓使用者以為新答案存好了。
  - B：不比對內容，一律回傳上次那筆。比較簡單，但上面那種狀況使用者不會發現。

- [x] ~~**4. 這次要不要一起做「取得問卷題目」（4.1）？**~~
  - A（建議）：要。沒有它，前端無從得知每一題的 id 和選項，送出 API 等於只能在測試裡用。它是唯讀、範圍小。
  - B：不要，留給 React 作答頁那個任務。

- [x] ~~**5. 送出成功後回傳什麼？**~~
  - A（建議）：和「單筆結果」API 完全一樣（分數、分級、行動建議、每題作答）。前端送出後可以直接顯示結果，不用再查一次；格式也只有一種。
  - B：只回新紀錄的 id，前端再去讀單筆結果。多一次往返。

- [x] ~~**6. 驗證失敗時的錯誤訊息？**~~
  - A（建議）：依欄位分開、中文，文字沿用網頁版（例如「有題目沒有作答」「請選擇這次有沒有戴助聽器」）。React 頁面會在送出前先自己檢查漏答，所以 API 的錯誤主要給「被竄改或前端有 bug」的情況，不需要逐題標出。
  - B：逐題標出哪一題錯（像網頁版的紅字）。代價：錯誤格式比較複雜，而 React 頁面送出前本來就會擋。

---

## 完成後回報（由 AI 填寫）

- **改了哪些檔案、為什麼**：
  - `screening/models.py`、`screening/migrations/0018_submission_idempotency_key.py`：`Submission.idempotency_key`（UUID、可空）＋唯一限制 `user＋idempotency_key`；網頁版作答是 NULL，不受影響。
  - `screening/forms.py`：`BaseAnswerFormSet.save()`，交易內建立作答＋存所有答案；`screening/views.py` 網頁作答改呼叫它（行為不變）。
  - `screening/api/serializers.py`：`QuestionnaireDetailSerializer`（題目＋選項，選項取自 `forms.answer_choices`）、`SubmissionCreateSerializer`（只驗 JSON 形狀，內容交給 `AnswerFormSet`）、`StrictBooleanField`。
  - `screening/api/views.py`、`screening/api/urls.py`：`QuestionnaireDetail`；`SubmissionList.post`（收據編號流程）；單筆查詢抽成 `_own_submission_details()`，GET 單筆與 POST 回傳共用。
  - `docs/api/schema.yaml`：重新產生。
- **驗收條件對應的測試**（`screening/tests.py`）：
  - 送出作答：`ApiSubmitTests` 的 `test_anonymous_gets_403`、`test_missing_csrf_token_gets_403`、`test_valid_submission_is_saved_and_scored`、`test_all_zero_is_a_real_score`、`test_user_in_body_is_ignored`、`test_invalid_answers_get_400`（漏題、重複、別份問卷、不合法分數）、`test_wearing_hearing_aid_is_required`、`test_unknown_questionnaire_gets_400`、`test_questionnaire_without_questions_gets_400`、`test_failure_midway_leaves_nothing`（另有 `HearingAidTests.test_failure_midway_leaves_nothing` 守網頁版）、`test_schema_documents_write_endpoints`＋`ApiFoundationTests.test_committed_schema_is_up_to_date`、`test_detail_stays_read_only`
  - 收據編號：`test_same_key_same_body_returns_first`、`test_same_key_different_body_gets_409`、`test_missing_or_invalid_key_gets_400`、`test_key_is_scoped_to_user`、`test_concurrent_same_key_returns_first_not_500`
  - 回傳內容：`test_created_body_matches_detail_get`、`test_errors_are_in_chinese_by_field`
  - 取得問卷題目：`ApiQuestionnaireDetailTests` 三個、`ApiSubmitTests.test_questionnaire_detail_feeds_submit`、`test_ioi_ha_gets_400`
  - 結果：Django 237、前端 31 全部通過
- **規格以外的決定**（如果有，說明原因）：
  - 既有測試 `ApiSubmissionTests.test_endpoints_are_read_only` 不再對列表測 POST（POST 現在是送出）。
  - `answers` 用 `ListField`：傳來的不是陣列時，錯誤和其他欄位一樣是一層中文清單。
  - 單題 JSON 形狀錯（例如少了 `score`）時，DRF 預設會逐題標出 `{"answers": {"0": {...}}}`；規格的「不逐題」指內容驗證，這裡沿用 DRF 預設（審查 #10）。
  - 答案先依題號排序再交給 formset（防 F-6 位置耦合）；目前每題選項相同，沒有可觀察的效果，已記進 roadmap。
- **這次用到的新概念**（各用一句話解釋）：冪等／Idempotency-Key、201／200／409、競爭條件、savepoint、唯一限制與 NULL、serializer 轉交 formset、DRF `BooleanField` 很寬鬆、突變驗證。說明見 `docs/interview.md` 第一部分。
- **面試可能追問的 2–3 題**（附答案要點）：Q57 怎麼保證連按兩次只存一筆；Q58「先查再存」的競爭條件與交易退回；Q59 網頁和 API 共用驗證規則。要點見 `docs/interview.md`。
- **建議寫進 decisions/ 的內容**（素材即可，條目由本人撰寫；註明放哪個主題檔）：見對話。
