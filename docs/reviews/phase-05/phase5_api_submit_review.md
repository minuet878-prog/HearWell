# 審查報告：寫入 API（作答送出）

- 規格：[phase5_api_submit.md](../../specs/phase-05/phase5_api_submit.md)　計畫：[phase5_api_submit_plan.md](phase5_api_submit_plan.md)
- 審查範圍：分支 `feat/api-submit-answers` 未 commit 的改動＋`screening/migrations/0018_submission_idempotency_key.py`
- 審查者：沒有參與實作的 subagent，2026-10-15

## 總結

- 全套測試：`Ran 235 tests ... OK`（實際跑過）。
- **沒有找到會造成錯誤資料、越權存取或 500 的 bug**。收據編號流程、唯一限制、IDOR 範圍、網頁版搬移都正確。
- 主要問題在「測試沒驗到它宣稱的東西」：用暫時修改驗證（都已還原）發現 4 處拿掉實作，測試還是全過。
- 一處和規格字面不符：`wearing_hearing_aid` 會接受 `1`、`"yes"`、`"on"`，規格寫「只接受 true／false」。

驗證方法：把原檔備份到 scratchpad，每次改一處 → 跑 `screening` 全部測試 → 從備份還原。探測用的測試放在 scratchpad（`PYTHONPATH` 指過去跑），沒有放進 repo。結束時 `git diff --stat` 跟開始時一樣。

---

## 一、Bug／和規格不符

### 1. `wearing_hearing_aid` 接受 true／false 以外的值（確定）
- 位置：`screening/api/serializers.py:123-129`（DRF `BooleanField`）
- 規格 4.2：「`wearing_hearing_aid` 必填，只接受 true／false」。
- 實際：DRF 的 `BooleanField` 也接受 `1`、`0`、`"yes"`、`"on"`、`"true"`、`"1"` 等。用探測測試實際送出：
  ```
  wearing 1 201
  wearing 'yes' 201
  wearing 'on' 201
  ```
- 影響：小。只有前端送錯型別才會發生，而且不會存錯值（`1` 還是存成 True）。但前端如果有 bug 把字串送過來，API 不會擋，跟規格「被竄改或前端有 bug 時要擋」的精神不符。
- 建議分類：**要修（小）或請本人決定改規格**。修法很短：`validate_wearing_hearing_aid` 裡檢查 `self.initial_data` 原始值是不是 `bool`，或改用 `ChoiceField(choices=[True, False])`。

### 2. 「沒有題目的問卷」那道檢查是必要的，但沒有測試（確定）
- 位置：`screening/api/serializers.py:135-136`
- 拿掉這兩行（M5），235 個測試全過。
- 但這兩行其實很重要：拿掉之後，對一份沒題目的問卷送 `answers: []`，formset 會判斷「送來的題目集合（空）＝應有的題目集合（空）」而通過，**存出一筆沒有答案的 submission**——正是 CLAUDE.md 第 11 條要另外處理的「空的 submission」。
- 探測結果（現在的實作是對的）：`empty questionnaire 400 {"questionnaire":["這份問卷沒有題目"]}`
- 規格 4.2 表格有寫「沒有題目 → 400，什麼都不存」，但第 5 節沒有對應的驗收條件，所以實作者沒寫測試。
- 建議分類：**補測試**。

---

## 二、測試沒驗到它宣稱的東西

用「拿掉一段實作，看測試會不會失敗」驗證（每次都已還原）：

| 代號 | 拿掉什麼 | 結果 |
|---|---|---|
| M1 | `forms.py:121` `BaseAnswerFormSet.save()` 裡的 `transaction.atomic()` | **235 全過** |
| M2 | `api/views.py:113` view 裡的 `transaction.atomic()` | **235 全過** |
| M3 | 兩個都拿掉 | `test_failure_midway_leaves_nothing` FAIL、`test_concurrent_same_key_returns_first_not_500` ERROR |
| M4 | `serializers.py:138-141` 依題號排序答案 | **235 全過** |
| M5 | `serializers.py:135-136` 沒題目就擋 | **235 全過**（見一-2） |
| M6 | `api/views.py:65` `_same_content` 的問卷比對 | **235 全過** |
| M7 | `api/views.py:29` 問卷詳情排除 IOI-HA | `test_missing_or_ioi_ha_gets_404` FAIL（有驗到） |

### 3. 兩層 `transaction.atomic()` 互相掩護，網頁版的「全有或全無」沒有測試（確定）
- 位置：`screening/forms.py:121`、`screening/api/views.py:113`
- `formset.save()` 自己已經包了 `atomic`。在 view 裡再包一層時，內層 `atomic` 會自動變成 savepoint（交易裡的「存檔點」，出錯可以只退回到這裡），所以 view 那層的效果跟內層完全重疊：M1、M2 單獨拿掉都不會壞。
- 後果：
  - 網頁版作答（`screening/views.py:147`）只靠 `formset.save()` 那層保護全有或全無，但**沒有任何測試**驗它（M1 全過）。將來有人把 `save()` 裡的 `atomic` 拿掉，網頁版就可能留下半份作答，測試抓不到。
  - view 那層 `atomic` 是多寫的（註解說是給同時請求用的 savepoint，但內層已經是了）。
- 建議分類：
  - **補測試**：網頁版作答也加一個「存答案中途失敗 → 不留作答」的測試（或直接對 `formset.save()` 測），讓 M1 會失敗。
  - **不改或刪掉 view 那層 `atomic`**：刪掉的話程式較少；留著的話把註解改成「明確標出 IntegrityError 的退回點」。兩者行為一樣，看本人偏好。（推薦刪，並靠上面的新測試＋現有 API 測試保護。）

### 4. 答案排序是目前用不到的程式（確定），而且沒有測試
- 位置：`screening/api/serializers.py:137-141`
- 計畫有說明：formset 用「第幾個表單 ↔ 第幾題」配選項（F-6 位置耦合），所以先排序。但 API 只收 HHIE-S／HHIA-S，每題選項都一樣（`Score.choices`），排不排結果都一樣，M4 全過。
- 測試 `_body()` 有故意倒序送出，但因為選項都一樣，倒序送也驗不到排序。
- 這段在將來開放 IOI-HA（每題選項不同）時才會真的起作用。
- 建議分類：**不改**（計畫已經跟本人說明是預防性的，而且很短）。但要知道它目前**沒有測試保護**；等開放 IOI-HA 時一定要補「倒序送出、每題選項不同」的測試。這點建議寫進 roadmap 或 decisions 素材。

### 5. 409 測試少了「問卷不同」那一種（確定，影響低）
- 位置：`screening/tests.py` `test_same_key_different_body_gets_409`
- 驗收條件寫「答案不同（或問卷不同、wearing_hearing_aid 不同）」，測試只有答案不同、wearing 不同兩種。
- 不過 `_same_content` 的問卷比對（M6）邏輯上是多餘的：題目 id 只屬於一份問卷，問卷不同時答案的題目 id 一定不同，照樣會 409。所以補測試也不會讓 M6 失敗。
- 建議分類：**補測試**（一行 subTest，對齊驗收條件文字即可；不必刪問卷比對，它讓意圖更清楚）。

### 6. 「回傳的總分與分級和我的紀錄頁一樣」驗得偏弱（確定，影響低）
- 位置：`screening/tests.py` `test_valid_submission_is_saved_and_scored`
- 只檢查「我的紀錄」頁出現「顯著影響」，沒有檢查總分 30 也出現在頁面上。
- 建議分類：**補測試**（加一行斷言頁面上有 30 這個分數；要看 `my_hearing.html` 實際怎麼顯示分數再寫）。

### 7. 同時請求的測試是用 mock 模擬的（推測，可接受）
- `test_concurrent_same_key_returns_first_not_500` 用 mock 讓第一次 `_find_by_key` 回 None，真的撞到唯一限制，這部分有驗到（M3 會 ERROR）。但 except 之後第二次 `_find_by_key` 回的是 mock 給的物件，沒有驗「撞到限制之後重新查詢真的查得到」。
- 推理：本機和正式都是 PostgreSQL、預設 READ COMMITTED、沒有開 `ATOMIC_REQUESTS`（`config/settings.py` 查過），第二個請求的 INSERT 會等第一個 commit 後才報錯，savepoint 退回後重新查詢看得到第一筆。所以實際行為應該正確。
- 建議分類：**不改**。要真的驗需要 `TransactionTestCase`＋兩個執行緒，成本高、容易不穩定。

---

## 三、多寫

### 8. view 那層 `transaction.atomic()`（確定）
- 見第 3 點。

### 9. `test_detail_stays_read_only` 和既有測試重複（確定，影響低）
- `ApiSubmitTests.test_detail_stays_read_only` 測 PUT／PATCH／DELETE 單筆 → 405；既有的 `ApiSubmissionTests.test_endpoints_are_read_only` 已經對單筆 URL 測了 post／put／patch／delete。
- 建議分類：**不改**。驗收條件要「每條至少一個測試」，在新測試類別裡留一個對應的也合理。

其他沒有發現多寫：沒有新套件、沒有 PUT／PATCH／DELETE、沒有 IOI-HA 寫入、沒有 rate limit／版本號。

---

## 四、「不做」清單

逐項檢查，**沒有違反**：

| 不做 | 檢查結果 |
|---|---|
| React 作答頁、中途儲存 | 沒有前端改動 |
| 修改網頁版行為 | `screening/views.py:147` 只是把原本的建 Submission＋`bulk_create` 搬進 `formset.save()`，內容逐行相同（generator 改 list 不影響，`bulk_create` 會先轉成 list）。IOI-HA 的 `_ioi_ha_norm` 仍在交易外計算，跟原本一樣。網頁既有測試全過 |
| PUT／PATCH／DELETE | 單筆仍是 `RetrieveAPIView`，405 |
| IOI-HA 透過 API | 問卷詳情、送出都排除 `code=IOI_HA` |
| rate limit、版本號、JWT、CORS | 沒有 |
| 新增套件 | `requirements*.txt` 沒動 |

---

## 五、其他檢查過、沒問題的地方

- **IDOR**：`_find_by_key` 用 `user.submissions` 限定本人；回傳用 `_own_submission_details(request)`；請求裡的 `user` 欄位被忽略（有測試）。唯一限制是 `(user, idempotency_key)`，別人用過的編號不影響我（有測試，且拿掉 user 範圍時測試會失敗——推理：B 的分數全 0、A 的全非 0，會變 409）。
- **NULL 與唯一限制**：網頁版作答的 `idempotency_key` 是 NULL，PostgreSQL 唯一限制不比對 NULL，不會互撞。migration 只加可空欄位＋限制，不動舊資料。
- **收據編號格式**：大寫、加大括號、無連字號的 UUID 都會被 `uuid.UUID()` 正規化成同一個值（探測：同一個編號四種寫法 → 201、200、200、200，資料庫 1 筆），這是好事。
- **檢查順序**：先收據編號 → 再內容驗證 → 再比對用過的編號。用過的編號＋不合法內容 → 400（不是 409），跟計畫第 3 點一致。
- **錯誤訊息**：
  - 1001 題 → `{"answers":["重複題目"]}`；2001 題 → `{"answers":["請送出最多 1000 個表單。"]}`（Django 內建，中文但用語是「表單」，可接受）。
  - 不存在的題目 id → `{"answers":["表單資料有誤，請重新確認每一題的作答"]}`。
  - body 不是物件 → `{"non_field_errors":["無效的資料，應該為字典類型，並非 list。"]}`。
  - 都是中文、不會 500。
- **計分單一路徑**：回傳走 `SubmissionDetailSerializer`＋`Submission` 計分方法，沒有另寫聚合。201 內容和 GET 單筆一樣（有測試）。
- **0 分**：全 0 → 201、total 0、`normal`（有測試）。
- **問卷詳情 N+1**：`Prefetch` 有 `select_related("questionnaire")`，`answer_choices` 不會每題多查一次。送出時 `attrs["questionnaire"].questions.all()` 透過反向關聯管理員取得，Django 會自動把 `question.questionnaire` 指回同一個物件，也不會 N+1。

### 10. 每題答案格式錯時，錯誤會逐題標出（確定，影響低）
- 例如某一題少了 `score`：`{"answers":{"0":{"score":["這個欄位是必須的。"]}}}`。
- 規格說「不逐題標出」，但那是指 formset 的內容驗證（漏題、不合法分數）；這裡是 JSON 形狀錯誤，DRF 預設就是這個格式。
- 建議分類：**不改**（只有前端送錯格式才會發生，規格的意圖是不為了逐題錯誤設計複雜格式，不是禁止 DRF 的預設行為）。可以在完成後回報提一句。

---

## 六、分類總表

| # | 項目 | 分類 |
|---|---|---|
| 1 | `wearing_hearing_aid` 接受 1／"yes"／"on" | 要修（小），或由本人改規格 |
| 2 | 沒題目的問卷 → 400，沒有測試 | 補測試 |
| 3 | 兩層 atomic 互相掩護；網頁版全有或全無沒有測試 | 補測試＋（建議）刪 view 那層 atomic |
| 4 | 答案排序目前無作用、無測試 | 不改（開放 IOI-HA 時補測試，記進 roadmap） |
| 5 | 409 少「問卷不同」 | 補測試 |
| 6 | 「我的紀錄」頁只比對分級沒比對總分 | 補測試 |
| 7 | 同時請求用 mock 模擬 | 不改 |
| 9 | 單筆唯讀測試重複 | 不改 |
| 10 | JSON 形狀錯誤會逐題標出 | 不改 |

---

## 七、實作者查證後的分類（2026-10-15）

查證方式：#1 直接對 serializer 欄位送 `1`／`"yes"`／`"on"`，都變成 True（重現）。#3 暫時拿掉 `formset.save()` 的 `atomic`，235 個測試全過（重現，已還原）。#2、#5、#6、#8 照程式碼逐行確認，結論同審查。

### 要修
- **#1** `wearing_hearing_aid` 只收 JSON 的 true／false：其他值（1、"yes"、"on"、"true" 字串）回 400，訊息沿用「請選擇這次有沒有戴助聽器」。理由：規格明寫「只接受 true／false」，API 的錯誤本來就是給「前端有 bug」的情況。
- **#8** 刪掉 API view 裡多包的那層 `transaction.atomic()`。理由：`formset.save()` 自己已經是全有或全無，撞到唯一限制時那一層會整段退回，外層多一層沒有效果，只是讓人以為它有作用。

### 補測試
- **#1** 送 1、"yes"、"true" → 400。
- **#2** 沒有題目的問卷 → 400、什麼都不存；並把這條補進規格第 5 節（4.2 表格有寫，驗收條件漏了）。
- **#3** 網頁版作答：存答案中途失敗 → 不留半份作答（讓拿掉 `formset.save()` 的 atomic 時會失敗）。
- **#5** 409 加「問卷不同」一種（對齊驗收條件文字）。
- **#6** 「我的紀錄」頁也要出現總分 30。

### 不改
- **#4** 答案排序：現在只有 HHIE-S／HHIA-S，每題選項一樣，排序沒有可觀察的效果、也寫不出會失敗的測試；留著是為了開放 IOI-HA 時不踩 F-6。記進 roadmap：開放 IOI-HA 寫入時要補「倒序送出、每題選項不同」的測試。
- **#7** 同時請求用 mock 模擬：真的雙執行緒測試成本高又容易不穩定；資料庫唯一限制那一段有真的撞到。
- **#9** 單筆唯讀測試重複：新測試類別對應自己的驗收條件，留著。
- **#10** JSON 形狀錯誤時逐題標出：DRF 預設行為，只有前端送錯格式才會出現；規格的「不逐題」指的是內容驗證。寫進完成後回報。
