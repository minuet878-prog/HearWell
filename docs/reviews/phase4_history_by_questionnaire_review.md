# 我的紀錄依問卷分開：審查報告（審查者原文）

- 審查範圍：`feat/history-by-questionnaire` 的 commit `1e090a5`（審查時先看未 commit 的 diff，之後確認 `1e090a5` 內容與審查的 diff 完全相同：同樣 13 個檔案、行數一致，工作目錄對 `1e090a5` 無差異）；`history_compare.html` 不審。
- 對照：`docs/specs/phase4_history_by_questionnaire.md`（狀態「已確認」）、CLAUDE.md 不可違反的規則與已知陷阱。
- 實際執行：
  - `py313/bin/python manage.py test --settings=config.test_settings` → 201 個測試全過（OK）。
  - `npm test --prefix frontend` → 2 個檔案、31 個測試全過。
  - 另寫探測測試（放在專案外的 scratchpad，繼承 `HistoryTabsTests`，跑完已刪除）：查詢次數、網址參數變體、同時間紀錄、IOI-HA 灰色帶與點的 grid-row 值。結果引用在下面各項。

---

## 一、Bug 與邊界

### 1-1 同一時間建立的紀錄，預設分頁與「最近一次」IOI-HA 不穩定（低）
- 位置：`screening/views.py:240`（`submissions[0].questionnaire`）、`screening/views.py:213`（`latest = records[0]`）；排序來自 `screening/models.py:87` `with_scores()` 的 `.order_by("-created_at")`，沒有 `-id` 當平手規則。
- 問題：`_latest_hhie_s` 用 `("-created_at", "-id")`，但 `my_hearing` 的清單只排 `-created_at`。兩筆 `created_at` 完全相同時，誰是「最近一次」由資料庫決定，預設分頁、IOI-HA 常模圖的「最近一次」和清單順序可能跟 `_latest_hhie_s` 的判斷不一致。
- 重現：探測測試建立 HHIE-S（id 70）與 IOI-HA（id 71），把兩者 `created_at` 更新成同一值，打開我的紀錄 → 預設分頁是 HHIE-S（id 較小的那筆），與 `-id` 平手規則相反。
- 實務上 `auto_now_add` 有微秒，正式環境幾乎不會撞；但規則不一致。建議 `with_scores()` 的排序加上 `"-id"`（同時影響 API 與清單，需評估是否算「改變既有 API 回傳」——只是平手時的順序，應不算）。

### 1-2 網址參數各種值：行為正確（無問題，記錄探測結果）
- 位置：`screening/views.py:238-241`。
- 探測結果（使用者有 HHIE-S 與 IOI-HA，最新是 IOI-HA）：
  | 查詢字串 | 狀態碼 | 打開的分頁 |
  |---|---|---|
  | `?questionnaire=HHIE-S`（大寫） | 200 | IOI-HA（預設） |
  | `?questionnaire=hhie-s&questionnaire=ioi-ha` | 200 | IOI-HA（取最後一個） |
  | `?questionnaire=ioi-ha&questionnaire=hhie-s` | 200 | HHIE-S（取最後一個） |
  | `?questionnaire`（空） | 200 | IOI-HA |
  | `?questionnaire=%20hhie-s` | 200 | IOI-HA |
  | `?questionnaire[]=hhie-s` | 200 | IOI-HA |
- 大寫不比對、重複參數取最後一個，都不會 404/500，符合規格第 3 節。只有「他人才有的問卷」由 `test_only_own_records` 與 `test_invalid_tab_falls_back_to_default`（`ioi-ha`、`other`）涵蓋。大寫與重複參數沒有測試，但行為合理，不一定要補。

### 1-3 IOI-HA 紀錄缺題或 `norm_group` 空白時會 500（低）
- 位置：`screening/views.py:220`（`latest_scores[number]`）、`screening/views.py:227`（`IOI_HA_NORMS[latest.norm_group]`）。
- 問題：`grouped = latest.norm_group != NormGroup.UNGROUPED`，`norm_group == ""` 也會被當成「有分組」，接著 `IOI_HA_NORMS[""]` → `KeyError` → 500。缺任一題答案時 `latest_scores[number]` 也會 `KeyError`。
- 目前送出流程一定會填 `norm_group`、一定 7 題全答，admin 也不能新增 Submission，所以靠資料不變式擋住；IOI-HA 尚未上線、沒有舊資料。屬於防禦性問題，可接受不改，但值得知道「資料不變式被打破時整頁 500」。

### 1-4 IOI-HA「前一次」只看緊鄰的上一筆（低，確認解讀）
- 位置：`screening/views.py:215-217`。
- 實作：只取 `records[1]`，不同組就不疊。若順序是「中重度（最新）→ 輕中度 → 中重度」，不會往回找第三筆。這符合驗收 16 的字面（「前一次是輕度至中度就不疊」），但待決問題 4 寫「只疊同一組的前一次」也可以讀成「同一組裡的前一次」。建議請本人確認是這個意思（目前實作與驗收 16 一致）。

### 1-5 差值為 0、負數、未記錄：正確（無問題）
- `screening/views.py:188-202`：`change == 0` → 「沒有變化」，`< 0` → 「多了 N 分」，未記錄（None）在 `_latest_hhie_s` 用 `wearing_hearing_aid=wearing` 過濾，`None` 永遠不會被當成 True/False。`{% if difference %}` 判斷的是 dict，不是分數，不會把 0 當沒資料（規則 11 OK）。
- IOI-HA 只有一筆：`len(records) > 1` 擋住，OK。前一筆不同組、最新未分組：都不疊，OK。`column.previous_row`／`latest_row` 值域是 1–5，`{% if %}` 不會把 0 誤判（不可能出現 0）。

### 1-6 查詢次數：沒有 N+1（無問題，附一個可省的小優化，低）
- 探測結果（CaptureQueriesContext）：
  | 分頁 | 6 筆紀錄 | 26 筆紀錄 |
  |---|---|---|
  | HHIE-S | 7 | 7 |
  | IOI-HA | 5 | 5 |
- `_item_scores` 最多呼叫兩次（最新、前一次），每次一個查詢，與筆數無關；`_aided_difference` 固定 2 次 `.first()` ＋ 2 次 `aggregate`。
- 小優化（可不做）：`_aided_difference` 另外查兩次 DB 再各自 `aggregate`，其實 `records` 已經是用 `with_scores()` 標註好分數的同一批 HHIE-S，可以直接從 `records` 挑出最近的沒戴／有戴，省 4 個查詢。兩條路最後都走 `_score_expressions()`，所以不違反規則 10，純粹效能。

### 1-7 `total_answer_score` 走單一計分路徑（無問題）
- 模板 `my_hearing.html:24-25` 用 `difference.unaided.total_answer_score`，這是 `Submission` 的 property → `_calculate_scores()` → `_score_expressions()`；清單用 `with_scores()` 標註，也是同一個 `_score_expressions()`。符合規則 10。

### 1-8 HHIE-S 分頁的趨勢圖可能比清單少點、甚至整張不見（中）
- 位置：`frontend/src/TrendChart.jsx:57`（只抓 `/api/submissions/` 第一頁，最新 20 筆，跨所有問卷）、`frontend/src/TrendChart.jsx:66`（`points.length === 0` 就 `return null`）。
- 問題：分頁之後，HHIE-S 分頁的圖是「最新 20 筆（所有問卷混在一起）裡的 HHIE-S」。IOI-HA 紀錄越多，HHIE-S 圖的點就越少；若最新 20 筆全是 IOI-HA，HHIE-S 分頁的圖會整個消失，沒有任何說明，但下方清單照樣列出全部 HHIE-S。
- 重現（前端）：`mockApi({ results: [20 筆 ioi-ha] })`，`render(<TrendChart code="hhie-s" />)` → `container.textContent === ""`。
- 改版前也有「只看第一頁」的限制，但當時圖固定畫「最新那份問卷」，所以至少有點；現在分頁固定畫指定問卷，問題變得比較容易出現。實務上 IOI-HA 填得少，短期不太會撞到。修法需要 API 支援依問卷篩選（規格說「是否需要新增 API 屬於實作，計畫時再提」），建議至少列為已知限制，或在 roadmap 記一筆。

### 1-9 標籤順序依問卷 pk，而不是明確的規則（低）
- 位置：`screening/views.py:236`（`sorted(..., key=lambda q: q.id)`）。
- fixture 中 HHIE-S pk=1、IOI-HA pk=2，所以目前結果正確。但「HHIE-S 在前、IOI-HA 在後」是寫在規格的規則，程式卻是依賴 pk 的巧合；之後若新增 HHIA-S（pk 3）會排在 IOI-HA 後面，是否符合期待沒人決定過。可接受，但建議在註解寫清楚「依 pk，fixture 保證 HHIE-S=1、IOI-HA=2」。

### 1-10 模板用字串 `"ioi-ha"`，view 用常數 `IOI_HA`（低）
- 位置：`screening/templates/screening/my_hearing.html:7`。
- 同一個判斷有兩處來源。可以改成 `{% if submissions and not ioi_ha_chart %}`，與 `my_hearing.html:29` 的判斷一致，避免日後只改一邊。

---

## 二、有沒有多寫

- 沒有發現規格外的功能。`_latest_hhie_s` 是從 `_ioi_ha_norm` 抽出來給差值共用，合理。
- `IOI_HA_ITEM_NAMES`（`screening/scoring.py:36-45`）：七個欄位短名稱（「使用時間」「幫助程度」…）是規格沒指定、由實作自行決定的文字，而且放在 `scoring.py`（計分模組）裡，但它只是顯示用文字。建議在「完成後回報 → 規格以外的決定」列出，並請本人（聽力師）確認名稱是否貼近書上 168 頁的用語（低）。
- CSS `.ioi-axis .ioi-grid > * { grid-column: auto; }` 與 `.ioi-grid > * { grid-column: 1; }` 互相覆蓋，可行但略繞（低，不改也可以）。

---

## 三、驗收條件與測試對應

| 驗收 | 測試 | 評估 |
|---|---|---|
| 1 | `test_default_tab_is_newest_ioi_ha` | OK |
| 2 | `test_default_tab_is_newest_hhie_s` | OK |
| 3 | `test_tab_url_shows_that_questionnaire`（＋ 1 的 href 斷言） | OK |
| 4 | `test_invalid_tab_falls_back_to_default` | OK；未涵蓋大寫、重複參數（行為正確，可不補） |
| 5 | `test_single_questionnaire_has_no_tabs` | OK |
| 6 | `test_no_records` | OK |
| 7 | `test_only_own_records` | OK；他人有沒戴＋有戴、本人只有沒戴，能抓到差值沒限定使用者的錯 |
| 8 | `test_anonymous_redirected_to_login` | OK |
| 9 | 前端 `draws a filled circle, a hollow square and a hollow triangle`、`explains the shapes in a legend`、`names the status in the tooltip` | OK，見 3-2 |
| 10 | `test_difference_uses_latest_unaided_and_aided` | OK（含更舊的 30 分與較新的未記錄當干擾） |
| 11 | `test_difference_ignores_order` | OK |
| 12 | `test_difference_of_zero_is_no_change` | OK |
| 13 | `test_difference_increase_has_no_verdict` | OK |
| 14 | `test_no_difference_without_both` | OK |
| 15 | `test_chart_bands_follow_latest_group` | **部分**，見 3-1 |
| 16 | `test_chart_overlays_previous_only_in_same_group` | OK（但「形狀不同」沒有測，見 5-1） |
| 17 | `test_ungrouped_latest_has_no_bands` | OK |
| 18 | `test_ioi_ha_result_links_to_ioi_ha_tab` | OK |
| 19 | `test_current_tab_marked_for_screen_readers`、`test_chart_text_alternatives` | OK，見 3-3 |
| 20 | 人工 | 尚未勾，見 5-4 |
| 21 | 全部測試通過 | OK |

### 3-1 常模圖灰色帶與點的「位置」沒有任何測試（中）
- 位置：`screening/views.py:221`（`latest_row = 6 - score`）、`:224`（`previous_row`）、`:227`（`band_rows = f"{6 - upper} / {7 - lower}"`）；測試 `screening/tests.py` `test_chart_bands_follow_latest_group` 只數 `class="ioi-band"` 有 7 個、點有 7 個，並檢查報讀文字。
- 問題：如果把 `6 - score` 寫成 `score`（圖上下顛倒），或 `band_rows` 少算一列，所有測試仍會通過——報讀文字是另外用 `compare_to_norm` 產生的，不會跟著錯。也就是「看得到的圖」和「報讀器聽到的」可能不一致而沒人發現。
- 我用探測測試確認目前值是對的：分數 (5,4,3,2,1,3,4)、中重度組 → 第 1 題帶 `1 / 3`（5–4 分）、點 `1`；第 4 題帶 `1 / 4`（5–3 分）、點 `4`；全部正確。
- 建議補測試：斷言至少一欄的 `style="grid-row: 1 / 3"` 與點的 `grid-row: 1`，以及一個 `previous_row`。

### 3-2 驗收 9「各有文字」的解讀（低，請本人確認）
- 實作是「圖例＋tooltip」標文字，點旁邊沒有文字。規格第 2 節寫「點依配戴狀態用不同形狀並標文字」。若本人的意思是每個點旁邊要寫「沒戴／有戴」，目前不符合；若圖例即可，則符合。手機上 tooltip 要點才出現，圖例是唯一常駐的說明。

### 3-3 驗收 19 的 HHIE-S 部分沒有測到新東西（低）
- `test_chart_text_alternatives` 前半段斷言清單裡有「助聽器：沒戴／有戴／未記錄」，但這是改版前就存在的清單欄位，不是這次新增；圖本身 `aria-hidden="true"`。論證上「清單就是圖的文字替代」成立，測試也能抓到「清單把配戴欄位拿掉」的錯，所以不算空轉；只是要知道它沒有驗證任何新程式碼。

### 3-4 前端「最新一點只靠放大」測試（無問題）
- `makes the latest point bigger` 只比較 `data-size`，已拿掉舊的「最新一點實心」斷言，符合待決問題 14。

---

## 四、規格「不做」清單

- 沒有改 API（`screening/api/` 無 diff）。OK
- 結果頁只改 IOI-HA 的「看我的紀錄」連結（`result_ioi_ha.html:29`）。OK
- 沒有記住上次分頁（純網址參數，無 session／localStorage）。OK
- 沒有 IOI-HA 總分或總結論、沒有差值好壞判定。OK
- 首頁、導覽列、作答頁、選問卷頁沒有改。OK
- 灰色地帶：模板 `my_hearing.html:31-32` 對「IOI-HA 以外的任何問卷」都畫趨勢圖（例如將來的 HHIA-S）。規格「不做」寫「HHIA-S 的差值與圖」以及「沒有專屬圖的其他問卷，分頁只列紀錄清單」。HHIA-S 的總分趨勢圖在改版前就有（`ClassifyViewTests` 也用 hhia-s），所以這比較像沿用舊行為而不是新增；但字面上與「沒有專屬圖的其他問卷只列清單」有衝突，建議請本人確認（低）。

---

## 五、無障礙

### 5-1 IOI-HA「前一次」與「最近一次」都是圓形，只差實心／空心（中）
- 位置：`screening/static/screening/styles.css`（`.ioi-dot`, `.ioi-legend-latest`, `.ioi-legend-previous` 都是 `border-radius: 50%`）。
- 規格第 2 節：「用另一種形狀疊上前一次」；驗收 16：「形狀不同，有圖例」。目前是同形狀（圓）、不同填色（實心深藍 vs 空心灰框），不符合字面。另外待決問題 14 剛決定「實心／空心只代表配戴狀態」，雖然那是 HHIE-S 圖，但同一頁另一個分頁又用實心／空心代表「最近／上一次」，意義不一致，對長者容易混淆。建議前一次改成別的形狀（例如空心方形或菱形，用 `border-radius: 0` ＋ `transform: rotate(45deg)`），並補測試。

### 5-2 兩點同分時的位移套用在所有欄（低）
- 位置：`styles.css` `.ioi-dot-previous { transform: translateX(-0.5rem); }`、`.ioi-dot-previous + .ioi-dot-latest { transform: translateX(0.5rem); }`。
- 註解寫「同分時左右並排」，但選擇器不看是否同列：只要有前一次，七欄的最新點都會往右偏 0.5rem、前一次往左偏，即使兩點在不同列。視覺上不影響判讀，只是不置中；與註解不符。

### 5-3 常模圖報讀與 aria-hidden 搭配（無問題，附小註）
- 每欄 `visually-hidden` 文字含題名、最近一次分數、（有時）上一次分數、常模範圍與比較結果；格線、名稱 `aria-hidden="true"`，不會重複唸。OK。
- 小註（低）：座標軸那格 `<li class="ioi-axis" aria-hidden="true">` 仍在 `<ul>` 裡，部分報讀器（VoiceOver）可能宣告「清單 8 項」但只唸 7 項。可以把座標軸移出清單，或接受。
- 報讀文字有「上一次 N 分」但沒有上一次的日期（日期只在圖例）。圖例本身沒有 `aria-hidden`，報讀器會讀到「上一次（2026/xx/xx）」，所以資訊仍在，OK。

### 5-4 字級與 320px／200%（驗收 20 人工項目的風險提示）
- 字級都用 rem（`history-tabs a` 1.125rem、`.ioi-name`／座標軸 0.875rem）；`1px` 只用在框線與格線，不是字級，不違反規則 13。
- 風險（低～中，請人工驗收時特別看）：`.ioi-name` 與座標軸用 0.875rem（基礎 18px 下約 15.75px），對 65+ 偏小。320px 寬時每欄約 34px，四字名稱會折成兩行；若手機系統字級放大到 200%，每欄只剩約 27px，名稱會一字一行，而點（1rem ≈ 36px）會比欄寬還寬，互相重疊。`minmax(0, 1fr)` 會避免橫向捲動，但可能出現重疊。
- 分頁籤：`min-height: 2.75rem`（約 49.5px）、`flex: 1`，觸控大小 OK；目前分頁用深藍底白字＋`aria-current="page"`，不只靠顏色（還有填滿的底色對比空框），報讀器會唸「目前頁面」。OK。文字沒有垂直置中（只有 min-height，沒有 flex 對齊），純外觀。

### 5-5 HHIE-S 圖例與形狀（無問題）
- 圖例只列出現過的狀態，順序固定；每項是 SVG 形狀（aria-hidden）＋文字。形狀＋填色＋文字三重區分，不只靠顏色。OK。

---

## 六、前端

- `main.jsx`：從 `data-questionnaire` 讀 code；若缺屬性，`code` 為 `undefined` → 沒有點 → 不畫，不會壞。OK
- `selectPoints(submissions, code)`：改成依傳入 code 篩選；`wearing` 帶 `true/false/null`。`trend.test.js` 有涵蓋「另一份問卷較新也照樣畫指定的」與 null。OK
- `statusOf(payload.wearing)`：API 一定回 `wearing_hearing_aid`（`screening/api/serializers.py:50`，`allow_null=True`），不會是 `undefined`。若將來欄位消失會在 `.shape` 爆掉，但目前無風險。
- `name` 改成從符合 code 的那筆取（`TrendChart.jsx:68`），因為上一行已確保至少一點，`find` 不會是 undefined。OK
- 舊行為：摘要框、分級帶、同日多筆（x 用 id）、0 分畫在底部、錯誤訊息——原有測試都保留並通過。OK
- Tooltip 加上「助聽器：沒戴／有戴／未記錄」。OK
- 摘要「比上一次增加／減少」仍跨配戴狀態比較（例如沒戴 → 有戴也算「比上一次減少」），這是舊行為，規格沒要求改；但同一頁上方又有「配戴前後比較」，兩個數字可能讓長者困惑（低，僅提醒）。

---

## 七、沒問題的部分（簡列）

- 所有資料都從 `request.user.submissions` 出發（清單、分頁、差值、IOI-HA 圖），規則 8 OK；有他人資料的測試。
- 差值與 IOI-HA 比較都在後端算好（規則 10），前端沒有重算；HHIE-S 分數走 `Submission` 計分方法，IOI-HA 走 `compare_to_norm`。
- 0 分與「沒有變化」處理正確（規則 11）。
- 未登入導向登入；無效網址參數回預設分頁，不 404／500。
- 沒有 N+1，查詢次數與筆數無關。
- 規格「不做」清單基本都遵守；API 未改。
- Django 201 個、前端 31 個測試全過。

## 建議分類（給實作者參考）

- 建議要修：5-1（IOI-HA 前一次要不同形狀）。
- 建議補測試：3-1（灰色帶與點的 grid-row）。
- 請本人確認：1-4（「前一次」的定義）、3-2（「標文字」是圖例還是點旁文字）、四的灰色地帶（其他問卷是否畫趨勢圖）、二的欄位短名稱。
- 可不改／記為已知限制：1-1、1-3、1-6、1-8、1-9、1-10、5-2、5-3 小註、5-4（人工驗收時看）。

---

## 主流程查證與分類（2026-10-15）

### 要修
- **5-1 IOI-HA 前一次與最近一次都是圓形（中）→ 已修**：查證屬實，模板兩者都是 `.ioi-dot`，只差填色，不符驗收 16「形狀不同」。做法：前一次改成空心菱形，圖例同步。
- **規格 2「沒有專屬圖的問卷只列清單」（低）→ 已修**：查證屬實，模板條件是「不是 IOI-HA 就放趨勢圖」，HHIA-S 之類的問卷也會載圖。做法：趨勢圖只在 HHIE-S 分頁出現（`<head>` 的 JS 與 `<div>` 同一個條件）。順便處理 1-10，條件只寫一處。
- **1-1 同時間建立的紀錄排序不一致（低）→ 已修**：查證屬實，`with_scores()` 只排 `-created_at`，`_latest_hhie_s` 有 `-id`。做法：`with_scores()` 加 `-id`。API 的游標分頁本來就自己指定 `("-created_at", "-id")`，回傳不變。
- **5-2 位移的註解跟實際不符（低）→ 已修**：行為是「有前一次時兩點固定左右錯開」，改註解，不改行為。

### 補測試
- **3-1 常模圖位置沒有測試（中）→ 已補**：查證屬實。補：中重度組「使用時間」灰色帶 `grid-row: 1 / 3`、最近一次 5 分在第 1 列、前一次 2 分在第 4 列。
- 隨上面的修改補：前一次是菱形、HHIA-S 分頁沒有趨勢圖、同時間建立時以 id 較大者為最近一次。

### 不改
- **1-8 趨勢圖被 IOI-HA 擠掉（中）**：前提不成立。`/api/submissions/` 已排除 IOI-HA（`screening/api/views.py` 的 `_own_submissions`），IOI-HA 紀錄不會佔掉最新 20 筆。只有將來出現第二份「有分級」的問卷（例如 HHIA-S）才會互相擠，到時候再加 API 篩選。
- **1-3 資料不變式被破壞時 500（低）**：送出流程一定存組別、7 題全答，admin 不能新增作答；加防呆屬於不需要的程式碼。
- **1-4「前一次」的解讀**：驗收 16 寫的就是緊鄰的前一次，照規格。
- **1-6 小優化**：純效能、查詢次數固定，不改。
- **1-9 標籤順序依 pk**：fixture 固定 HHIE-S pk 1、IOI-HA pk 2，符合規格。
- **3-2 驗收 9 的文字**：本人已同意圖例＋提示框＋清單的做法。
- **3-3 驗收 19 的 HHIE-S 部分**：清單就是圖的文字替代，測試能抓到欄位被拿掉。
- **欄位短名稱**：本人已在計畫的決定 2 確認。
- **5-4 200% 時點可能重疊**：列入驗收 20 人工檢查。

### 修改後（2026-10-15）
- 新測試：`test_chart_positions`（試驗：把列號公式改錯時會失敗，已還原）、`test_previous_point_has_another_shape`、`test_no_trend_chart_for_other_questionnaires`、`test_same_time_records_newest_id_wins`。
- Django 205、前端 31 全部通過；ruff 通過；用 320／360px 預覽確認菱形。
