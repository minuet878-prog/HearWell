# C1-B 分享聽力報告給家人：實作計畫

規格：`docs/specs/phase-08/phase8_c1_family_share.md`（已確認）。這份是第 4 步的計畫，等本人點頭才動手。

## 1. 資料：新 model `ReportShare`（migration 0022）

| 欄位 | 說明 |
|---|---|
| `user` | FK → User，`PROTECT`（和其他表一致；刪帳號時由 `delete_with_data()` 先刪） |
| `token` | `CharField(unique=True)`，用 `secrets.token_urlsafe(32)` 產生（43 字元、約 256 位元亂數，猜不到也列舉不了） |
| `created_at` | 產生時間 |
| `expires_at` | 產生時就寫好 = 產生時間＋7 天 |
| `revoked_at` | 取消時間，`null` = 沒取消 |
| `open_count` | 開啟次數，預設 0 |
| `last_opened_at` | 最後一次開啟，`null` = 沒人開過 |

- `ReportShareQuerySet.active()`：沒取消、而且 `expires_at` 還沒到。「有效」只在這裡定義，所有地方都用它。
- 失效的紀錄不刪，留著給「下載我的資料」用（Q-B8）；刪帳號時才刪。
- 「一次只有一個」：資料庫沒辦法用限制擋「還沒過期」這種跟時間有關的條件，所以產生時在交易裡先鎖住這個使用者那一列（`select_for_update`），再檢查有沒有有效的連結，避免連按兩次產生兩個。
- token 用明碼存：規格要求本人看得到連結網址，存雜湊就顯示不出來。

## 2. 網址與 view（`screening/views.py`、`urls.py`）

| 網址 | 方法 | 誰 | 做什麼 |
|---|---|---|---|
| `/report` | GET | 本人 | 原本的報告頁，上方多「分享給家人」區塊 |
| `/report/share` | POST | 本人 | 產生連結。表單要帶 `confirm` 才產生；已有有效連結就不再產生。做完導回 `/report` |
| `/report/share/<id>/cancel` | POST | 本人 | 取消。用 `get_object_or_404(..., user=request.user)` 找**有效的**那筆，別人的回 404 |
| `/shared/<token>` | GET | 任何人 | 封面：標題、有效日期、「打開報告」。不查任何健康資料、不計次 |
| `/shared/<token>/report` | GET | 任何人 | 報告唯讀版，每次 +1（用 `F("open_count") + 1` 在資料庫裡加，兩個人同時開也不會少算） |

- 代碼不存在、格式不對、過期、取消、帳號刪除：都是「`active()` 裡找不到」，同一個失效頁、404。
- 「打開報告」用 GET 連結：LINE 預覽只抓你貼的那個網址（封面），重新整理也不會跳出「重新送出表單」。代價是重新整理也算一次，跟規格「每次顯示報告算一次」一致。
- **抽共用**：把 `health_report` 裡組報告內容的部分抽成 `_report_context(user)`，本人頁和家人頁都呼叫它，走同一條計算路徑（規則 10）。
- **同意閘門**（`middleware.py`）：兩個 `/shared/...` 加進 `OPEN_PAGES`。原因：家人自己可能也有帳號、而且還沒同意，閘門會把他擋下。本人的同意狀態不影響連結（Q-B4），家人頁本來就不看本人有沒有同意。
- 家人頁的回應（封面、報告、失效頁）都加上：`never_cache`（不快取）、`X-Robots-Tag: noindex, nofollow`＋`<meta name="robots">`（不收錄）、`Referrer-Policy: no-referrer`（點出去的網站拿不到連結）。

## 3. 畫面（`screening/templates/screening/`）

- `health_report.html`：報告內容（摘要框到免責聲明）搬進新的 `report_content.html`，本人頁和家人頁都 `include` 它。差異用一個 `shared` 變數控制：家人版不顯示使用者名稱、出生年、手寫姓名欄、「回我的紀錄」，改顯示年齡（有填才顯示）和「這是家人分享給您的報告，連結有效到 ○月○日」。
- 新增 `report_share.html`（本人的分享區塊，`include` 在報告頁上方，加 `no-print`）：
  - 沒有有效連結：說明文字＋`<details>`（瀏覽器內建的「點開／收起」元件）「產生分享連結」→ 點開後才看到確認說明和「確認產生」按鈕。沒按確認就不會送出（驗收 23），不需要 JavaScript，也不會跳出瀏覽器對話框。
  - 有有效連結：網址、「傳給家人」、有效到、已開啟 N 次、最後開啟（沒開過寫「還沒有人打開」）、「家人看到的是您最新的報告」、「取消分享」。
- 新增 `shared_cover.html`、`shared_report.html`、`share_invalid.html`。
- `share-button.js`：多讀按鈕上的 `data-url`、`data-title`（報告頁要分享的是家人連結，不是目前這頁）；衛教頁沒有設，照舊分享目前這頁。
- `styles.css`：分享區塊、封面的少量樣式（rem）。列印沿用 `.health-report` 的規則。

## 4. 其他

- `models.py`：`delete_with_data()` 在刪 User 前先刪 `report_shares`。
- `views.download_my_data`：加 `report_shares`（產生時間、有效到、是否取消、開啟次數、最後開啟），不含 token。
- `privacy.html`：「會交給誰」後面加一段分享說明。`PRIVACY_UPDATED_ON` 改成合併當天；`CONSENT_VERSION` 不動。**注意**：現在的日期已經是 2026-10-17，今天合併的話數字看起來沒變，驗收 16 的測試會改成檢查「有分享段落、已同意者不被要求重新同意」。
- `screening/admin.py`：不註冊（admin 上看得到 token 等於多一個外洩的地方，也沒有要求）。

## 5. 測試（先寫、先確認失敗）

- 新檔 `screening/tests/test_share.py`，對應驗收 1–23（24 是手機人工）。用假帳號、假分數。
  - 時間相關（3、22）：直接把 `expires_at` 改成過去，不等 7 天。
  - 13：`assertNumQueries` 比較 1 筆和 20 筆的查詢數一樣。
  - 2、10、20：家人頁的分數／分級和本人報告頁比對同一段文字。
- 既有測試：`test_report.py`（報告頁搬成 include 後應全過，不改斷言）、`test_export.py`（JSON 多一個欄位，看有沒有斷言整份內容）、`test_account_deletion.py`、`test_consent.py`（允許清單）。
- e2e：這次不加（規格沒要求；分享按鈕的行為已經有衛教頁的 e2e 測過同一支 js）。

## 6. 不做（照規格）

API、React、多個連結、記錄 IP、自訂期限、全站 never_cache、改 C3 報告內容。

## 7. 驗證

- `python manage.py test --settings=config.test_settings`（全部）＋ `ruff check .`
- `python manage.py makemigrations --check`（確認沒漏 migration）
- 本機需要你自己 `migrate`（0022）＋ runserver 才能人工看畫面；驗收 24 在部署後用手機做。
