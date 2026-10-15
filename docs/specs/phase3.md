# Phase 3 規格：DRF 唯讀 API

- **狀態**：已完成（第 1、2 批）
- **分支**：`feat/api-foundation`（第 1 批）、`feat/api-submissions`（第 2 批）
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-14

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

在現有網站旁邊加一組只讀的 `/api/`，用 JSON 回傳使用者**自己的**問卷列表、歷史紀錄、單筆結果，分數與分級由後端算好。這是 Phase 4 React 趨勢圖（B2）的資料來源；現有頁面完全不動。

## 2. 範圍

### 要做
- 安裝 Django REST framework 與 drf-spectacular；建立 `/api/` 命名空間。
- 認證沿用登入的 session cookie；所有 `/api/` 端點都要登入。
- 四個唯讀端點：問卷列表、歷史紀錄（cursor 分頁）、單筆結果、OpenAPI schema。
- 產生的 OpenAPI schema 存成 repo 裡的檔案，測試比對「現在產生的」與「檔案」是否一致。

### 不做
- 任何寫入（作答送出等）：Phase 5。
- React、PWA：Phase 4。
- token／JWT 認證、CORS。
- Swagger／Redoc 網頁介面。
- 篩選、排序、搜尋參數。
- 問卷列表附帶題目（React 作答頁在 Phase 5 才需要）。
- 修改任何現有 template 頁面或其行為。
- 流量限制（rate limiting）、API 版本號。

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本 phase 特別注意：
  - **IDOR**（第 8 條）：歷史紀錄、單筆結果只查 `request.user` 的資料；別人的或不存在的一律 404，回應內容相同。
  - **計分單一路徑**（第 10 條）：分數走 `Submission` 的計分方法（列表用 `with_scores()`、單筆用 `Submission` 的分數 property），分級走 `Submission.classified`；不另寫聚合，前端不重算。
  - **0 是合法分數**（第 11 條）：分數一律是整數，沒有用 `null` 代表 0。
  - 歷史紀錄的查詢次數不能隨筆數成長。
  - 新增套件只有 `djangorestframework`、`drf-spectacular`，寫進 `requirements.txt` 並固定版本。

## 4. 行為描述

共通：
- 未登入 → **403**，`{"detail": "..."}`（JSON，不轉址到登入頁）。例外：schema 端點的 403 用它自己的 OpenAPI 格式（YAML 的 `detail: ...`），一樣不轉址、不洩漏 schema 內容（實作時發現，本人同意）。
- 只接受 GET（以及 HEAD／OPTIONS）；已登入時 POST／PUT／PATCH／DELETE → **405**（未登入一律先回 403：DRF 先檢查權限，再檢查方法）。
- 時間一律 ISO 8601、台北時區，例如 `"2026-10-14T14:30:00+08:00"`。

### 4.1 問卷列表 `GET /api/questionnaires/`

| 項目 | 內容 |
|---|---|
| 誰可以使用 | 未登入：403　　已登入：可以　　能否存取他人資料：不適用（問卷是共用的） |
| 回傳 | 陣列，依 id 排序；每份 `{"id": 1, "code": "hhie-s", "name": "HHIE-S"}` |
| **不能**回傳 | 題目、作答紀錄 |
| 需要計算的資料 | 無 |
| 空資料時 | `[]` |

### 4.2 歷史紀錄 `GET /api/submissions/`

| 項目 | 內容 |
|---|---|
| 誰可以使用 | 未登入：403　　已登入：只列自己的　　能否存取他人資料：不能 |
| 回傳 | cursor 分頁，每頁 20 筆：`{"next": 網址或 null, "previous": 網址或 null, "results": [...]}`，依作答時間新到舊 |
| 每一筆 | 見下方 JSON |
| **不能**回傳 | 使用者帳號、email、出生年；每題作答（只在單筆結果） |
| 需要計算的資料 | 由誰計算：後端　　計算路徑：`Submission.objects.with_scores()`、`Submission.classified` |
| 空資料時 | `{"next": null, "previous": null, "results": []}` |

```json
{
  "id": 3,
  "created_at": "2026-10-14T14:30:00+08:00",
  "questionnaire": {"code": "hhie-s", "name": "HHIE-S"},
  "wearing_hearing_aid": true,
  "scores": {"total": 18, "emotional": 8, "social": 10},
  "level": {"code": "mild_to_moderate", "text": "輕度到中度影響"}
}
```

- `wearing_hearing_aid`：`true` 有戴、`false` 沒戴、`null` 未記錄。
- `level.code`：`normal`／`mild_to_moderate`／`severe`／`unknown`；`text` 與網頁顯示相同。無法判讀時 `{"code": "unknown", "text": "無法判讀"}`，分數照常回傳。
- 不回傳顏色（顏色是前端的呈現）。

### 4.3 單筆結果 `GET /api/submissions/<id>/`

| 項目 | 內容 |
|---|---|
| 誰可以使用 | 未登入：403　　已登入：只能看自己的　　能否存取他人資料：不能，404 |
| 回傳 | 4.2 的所有欄位，再加 `advice`（與結果頁相同的建議文字）和 `answers` |
| **不能**回傳 | 使用者帳號、email、出生年 |
| 需要計算的資料 | 由誰計算：後端　　計算路徑：`Submission` 的分數 property、`Submission.classified`、`scoring.get_advice` |
| 空資料時 | 不適用（不存在 → 404） |

```json
"advice": "聽力的問題已經慢慢開始影響到您的社交活動以及情緒，例如……",
"answers": [
  {"number": 1, "text": "認識新朋友時，聽力問題使你不好意思嗎？", "score": 4, "label": "常常"}
]
```

- `answers` 依題號排序；`label` 是「常常／有時／從未」。

### 4.4 OpenAPI schema `GET /api/schema/`

| 項目 | 內容 |
|---|---|
| 誰可以使用 | 未登入：403　　已登入：可以 |
| 回傳 | OpenAPI 3 文件，只有 YAML（要 JSON：`?format=json` 回 404、`Accept: application/json` 回 406；審查後補強） |
| 版控 | 產生的 schema 存成 repo 裡的檔案；測試重新產生並比對，不一致就失敗 |

## 5. 驗收條件

### 第 1 批（`feat/api-foundation`）
- [x] 1. 假設未登入，當呼叫任一 `/api/` 端點，則回 403 和 JSON `{"detail": ...}`，不轉址；schema 端點回 403、內容有 `detail`、沒有 schema 內容。
- [x] 2. 假設已登入，當對問卷列表送 POST／PUT／PATCH／DELETE，則回 405。
- [x] 3. 假設有兩份問卷，當已登入呼叫問卷列表，則回 200 和依 id 排序的 `[{"id", "code", "name"}, ...]`，沒有其他欄位；沒有問卷時回 `[]`。
- [x] 4. 假設已登入，當呼叫 `/api/schema/`，則回 200 的 OpenAPI 文件，裡面有 `/api/questionnaires/`。
- [x] 5. 假設 API 的欄位或端點改了、但 repo 裡的 schema 檔沒更新，則測試失敗；更新後通過。
- [x] 6. 現有 template 頁面的測試全部通過；安裝 DRF 不會改變現有頁面的訊息用詞（例如「這個欄位是必須的。」）。

### 第 2 批（`feat/api-submissions`）
- [x] 7. 假設 A、B 各有紀錄，當 A 呼叫歷史紀錄，則只看到自己的，依作答時間新到舊，每筆欄位與 4.2 完全相同（不多不少）。
- [x] 8. 假設一筆紀錄，則 API 的總分、情緒、社交分數與分級，等於結果頁顯示的值。
- [x] 9. 假設三筆紀錄的助聽器分別是有戴、沒戴、未記錄，則 `wearing_hearing_aid` 分別是 `true`、`false`、`null`。
- [x] 10. 假設一筆所有題目都答「從未」的紀錄，則分數是 `0`（不是 `null`），分級是 `normal`。
- [x] 11. 假設問卷沒有門檻表（無法判讀），則 `level` 是 `{"code": "unknown", "text": "無法判讀"}`，分數照常回傳，不會 500。
- [x] 12. 假設有 21 筆紀錄，則第一頁 20 筆、`next` 不是 null；照 `next` 取第二頁得到 1 筆、`next` 是 null；兩頁合起來沒有重複或遺漏。
- [x] 13. 假設沒有紀錄，則回 `{"next": null, "previous": null, "results": []}`。
- [x] 14. 假設 1 筆和 5 筆紀錄，則歷史紀錄的查詢次數相同。
- [x] 15. 假設 A 呼叫自己的單筆結果，則回 4.3 的所有欄位，`answers` 依題號排序，`advice` 與結果頁相同。
- [x] 16. 假設 A 呼叫 B 的單筆結果、或不存在的 id，則都回 404，回應內容相同。
- [x] 17. 回應裡沒有使用者帳號、email、出生年。
- [x] 18. schema 檔更新後包含兩個新端點；現有 template 頁面的測試全部通過。

## 6. 待決問題

- [x] ~~怎麼切？~~ → 一份 phase 規格，分批 PR
- [x] ~~範圍？~~ → 問卷列表、自己的歷史紀錄、自己的單筆結果（＋schema）
- [x] ~~未登入？~~ → 403 JSON
- [x] ~~別人的／不存在的？~~ → 一律 404
- [x] ~~欄位？~~ → 列表含分項；單筆加每題作答和建議；分級用代碼＋文字；不回傳顏色
- [x] ~~分頁？~~ → cursor，每頁 20 筆
- [x] ~~schema 誰能看？~~ → 登入後，只給 YAML，不提供網頁介面
- [x] ~~契約檢查？~~ → schema 檔進版控＋測試比對

---

## 完成後回報（由 AI 填寫）

### 第 1 批（`feat/api-foundation`）

- **改了哪些檔案、為什麼**：
  - `requirements.txt`：新增 `djangorestframework==3.18.3`、`drf-spectacular==0.30.0` 與 8 個相依套件，全部固定版本。
  - `config/settings.py`：`INSTALLED_APPS` 加 `rest_framework`、`drf_spectacular`；`REST_FRAMEWORK`（只用 session 認證、預設要登入、只輸出 JSON、用 drf-spectacular 產 schema）；`SPECTACULAR_SETTINGS`（schema 也要登入）；`LOCALE_PATHS`。
  - `config/urls.py`：掛上 `api/`。
  - `screening/api/`（新）：`serializers.py`（`QuestionnaireSerializer`）、`views.py`（`QuestionnaireList`）、`urls.py`（問卷列表、`SpectacularYAMLAPIView`）。
  - `docs/api/schema.yaml`（新）：API 契約檔。
  - `locale/zh_Hant/LC_MESSAGES/django.po`／`.mo`（新）：把被 DRF 蓋掉的 5 句蓋回 Django 原本用詞。
  - `screening/tests.py`：`ApiFoundationTests`（8 個）。
- **驗收條件對應的測試**：
  1. `test_anonymous_gets_403_json`、`test_anonymous_cannot_read_schema`
  2. `test_questionnaire_list_is_read_only`
  3. `test_questionnaire_list`（id 小的字母順序排後面，只有依 id 排序才會過）、`test_questionnaire_list_empty`
  4. `test_schema_lists_endpoints`、`test_schema_is_yaml_only`
  5. `test_committed_schema_is_up_to_date`
  6. 全部既有測試；`RegisterFormTests.test_required_fields` 鎖住「這個欄位是必須的。」（拿掉 `LOCALE_PATHS` 會失敗）
- **規格以外的決定**：
  - 實作時發現：DRF 的 zh_Hant 翻譯蓋掉 Django 核心的 5 句（全站），本人同意用專案 `LOCALE_PATHS` 蓋回；`.mo` 進版控（Render 不保證有 `msgfmt`）。
  - 實作時發現：schema 端點的 403 是 YAML，本人同意改規格。
  - 審查後：schema 改用 `SpectacularYAMLAPIView`，要 JSON 回 404／406；規格補上「未登入先 403 再 405」。
- **這次用到的新概念**：DRF（serializer、generic view、全域設定）、預設拒絕、OpenAPI／drf-spectacular、契約檔比對測試、Django 翻譯優先順序與 `LOCALE_PATHS`、內容協商（404／406）。
- **面試可能追問的 2–3 題**：Q28、Q29、Q30。要點見 `docs/interview.md`。
- **建議寫進 decisions/ 的內容**：見對話（由本人撰寫）。

### 第 2 批（`feat/api-submissions`）

- **改了哪些檔案、為什麼**：
  - `screening/api/serializers.py`：`SubmissionSerializer`（列表）與繼承它的 `SubmissionDetailSerializer`（多 `advice`、`answers`）；`scores`、`level` 用巢狀 serializer 直接讀 `Submission` 的分數 property 與 `classified`，不另算。
  - `screening/api/views.py`：`SubmissionPagination`（cursor、20 筆、`-created_at, -id`，只用在這個 view）；`_own_submissions()` 共用查詢，跟 `my_hearing` 同一句，從 `request.user` 出發；`SubmissionList`、`SubmissionDetail`（`Prefetch` 依題號排序的作答）。
  - `screening/api/urls.py`：`submissions/`、`submissions/<int:pk>/`。
  - `docs/api/schema.yaml`：重新產生，含兩個新端點。
  - `screening/tests.py`：`ApiSubmissionTests`（16 個）。
- **驗收條件對應的測試**：
  7. `test_list_only_own_newest_first_with_exact_fields`
  8. `test_scores_match_result_page`（列表與單筆都比對結果頁 context）
  9. `test_wearing_hearing_aid_values`
  10. `test_all_never_scores_zero_not_null`
  11. `test_unknown_level_still_returns_scores`
  12. `test_cursor_pagination_has_no_gaps_or_duplicates`、`test_pagination_with_identical_created_at`（拿掉 `-id` 會失敗）
  13. `test_empty_list`
  14. `test_list_query_count_does_not_grow`
  15. `test_detail_matches_result_page`（測試資料把答案倒著存，沒排序就會失敗）
  16. `test_others_and_missing_submission_both_404_identically`
  17. `test_responses_have_no_personal_data`
  18. `test_schema_lists_submission_endpoints`、`test_committed_schema_is_up_to_date`、全部既有測試（106 個通過）
  - 另補：`test_anonymous_gets_403`、`test_endpoints_are_read_only`、`test_created_at_is_taipei_time`（第 4 節共通規則）
- **規格以外的決定**：
  - 時間會帶微秒（例如 `…:54.677525+08:00`），仍是 ISO 8601，不另外截掉。
  - 審查後：時間完全相同時往回翻（`previous`）可能不正確（DRF cursor 的已知限制），同一人同一微秒送兩次才會發生，接受不修；註解改成符合實際。
- **這次用到的新概念**：cursor 分頁、排序的平手處理（tie-breaker）、巢狀 serializer 與 `source="*"`、`Prefetch` 物件、測試資料太剛好。
- **面試可能追問的 2–3 題**：Q31、Q32、Q33。要點見 `docs/interview.md`。
- **建議寫進 decisions/ 的內容**：見對話（由本人撰寫）。
