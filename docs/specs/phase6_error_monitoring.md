# Phase 6 規格：錯誤監控

- **狀態**：已完成
- **分支**：`feat/error-monitoring`
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-16

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

正式環境發生錯誤（使用者看到 500）時，本人要在第一時間收到通知，看得到錯在哪裡，不用等使用者回報、也不用自己去翻 Render 的 log。
這是健康資料網站，**送去監控的內容不能帶出個資或作答內容**。

## 2. 範圍

### 要做
- 用 **Sentry 免費版**（資料放歐盟區），只在正式環境啟用。
- 伺服器端沒有被處理的錯誤（使用者看到 500 的那種）送到監控平台，並 email 通知本人。
- 限制送出的內容（第 4.2 節）。
- 一個只有管理員（superuser）打得開的測試網址，打開就故意出錯，用來在正式環境確認真的有送出（4.3）。
- roadmap 的 Phase 7「同意書與隱私權說明頁」補一句：要寫出錯誤監控用到的第三方服務。

### 不做
- 前端（瀏覽器裡 React）的錯誤：要多載入約 20–30 KB 的 JS，影響長輩手機首屏，之後另開一項評估。
- 效能監控（每個請求花多久）、使用者操作錄影（session replay）、上線紀錄（release tracking）。
- 404、403、表單驗證沒過這類「正常的拒絕」不送。
- 不改既有的錯誤頁、不改任何既有功能。
- 不設定 Django 的 `LOGGING`（log 格式、等級）——Render 的 log 維持現狀。
- 不做站內的錯誤後台。

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本 phase 特別注意：
  - 規則 3：真實個資與病人資料不能送出去；測試用假資料。
  - 規則 7：監控平台的金鑰只放 `.env`／Render 環境變數，不寫進程式碼。
  - 規則 8：測試網址非管理員（含未登入、一般使用者）一律 404。
  - 本人帳號的建立、通知設定、Render 環境變數，由本人操作；AI 只寫步驟。

## 4. 行為描述

### 4.1 什麼時候送

| 情況 | 送不送 |
|---|---|
| 正式環境，伺服器沒有處理到的錯誤（500） | 送，並 email 通知 |
| 程式自己記錄的錯誤（`logger.error`，例如「分數超出範圍」「找不到門檻表」） | 送，只送訊息樣板（`Score %s out of range ...`），不送填進去的值（審查後追加） |
| 404、403、405、表單驗證沒過 | 不送 |
| 本機、測試、CI（沒有設定監控金鑰） | 不啟用，什麼都不送，網站照常 |
| 同一個錯誤短時間發生很多次 | 平台彙整成一件，不會每次都寄信（平台內建） |
| 沒有錯誤的一般請求 | 什麼都不送（不送使用統計，即使偵測得到版本號） |

### 4.2 送出的內容

| 會送 | **不能**送 |
|---|---|
| 錯誤類型、程式出錯的位置（哪個檔案第幾行、呼叫順序） | 密碼、session cookie、CSRF token |
| 網址路徑與 HTTP 方法（例如 `POST /questionnaire/1`） | 表單內容（作答、聽力圖的點、註冊資料）；請求標頭（含 `X-CSRFToken`）與查詢字串（`?` 後面） |
| 發生時間、伺服器環境（Python、Django 版本） | 使用者名稱、email、出生年、IP 位址、帳號編號（完全不送使用者身分） |
| | 程式執行當下的變數值（可能含答案或分數） |
| | 錯誤訊息本身（例如資料庫錯誤會寫出重複的使用者名稱；類型和位置通常就夠查） |
| | `logger.error` 填進樣板的值（分數、問卷代碼），以及出錯前同一個請求裡的其他 log（麵包屑） |

### 4.3 管理員測試網址

| 項目 | 內容 |
|---|---|
| 網址與方法 | 一個固定網址，GET |
| 誰可以使用 | 未登入：404　　一般使用者：404　　管理員（superuser）：故意出錯（500），監控收到一筆 |
| 顯示 | 管理員看到的是一般的 500 錯誤頁；其他人看到一般的 404 頁 |
| 錯誤內容 | 專用的錯誤類型，名稱看得出是「測試用」（錯誤訊息一律不送，所以靠類型辨認） |

### 4.4 上線步驟（本人操作）

1. 到 sentry.io 註冊。建立組織時，**資料存放位置選 European Union（Frankfurt）**——建立後不能改。
2. 建立專案，平台選 **Django**。到 Settings → Projects → 這個專案 → Client Keys (DSN)，複製 DSN（一串 `https://…@…ingest.de.sentry.io/…` 的網址）。DSN 只貼進 Render，不要貼進程式碼或對話。
3. 第二道防線（伺服器端）：Settings → 組織 → Security & Privacy，確認 **Data Scrubber**、**Use Default Scrubbers** 開著，勾選 **Prevent Storing of IP Addresses**。
4. 通知：Alerts 裡確認有一條「新的 issue 出現時寄 email 給我」的規則（建立專案時預設會有）；個人 Settings → Notifications 的 email 也要開著。
5. Render → 這個服務 → Environment，新增 `SENTRY_DSN`＝剛才的 DSN，存檔（會重新部署）。
6. 部署完成後，用管理員帳號登入正式站，打開 `/monitoring-test`，會看到錯誤頁。幾分鐘內應該收到 email；在 Sentry 打開那筆，確認類型是 `MonitoringTestError`，看不到使用者、IP、標頭、錯誤訊息（驗收 9）。

## 5. 驗收條件

- [x] 1. 假設有設定監控金鑰，當某個網頁發生沒有處理的錯誤，則監控平台收到一筆，內容有錯誤類型、網址路徑、出錯位置，沒有錯誤訊息；使用者看到的仍是原本的 500 頁面。
- [x] 2. 假設有設定監控金鑰，當送出作答（帶密碼以外的表單資料）時發生錯誤，則送出的內容裡沒有表單內容、cookie、CSRF token、使用者名稱、email、IP、程式變數值。
- [x] 3. 假設登入或註冊時發生錯誤，則送出的內容裡沒有密碼。
- [x] 3a. 假設錯誤訊息裡帶著使用者資料（例如資料庫唯一限制錯誤寫出重複的使用者名稱），當送到監控，則送出的內容裡找不到那筆資料，錯誤類型和位置還在。
- [x] 3b. （審查後追加）假設程式記錄了 `Score 999 out of range ...` 這類錯誤，當送到監控，則只送樣板，找不到 999 和問卷代碼；同一個請求裡出錯前的 log 也不會跟著送出。
- [x] 4. 假設有設定監控金鑰，當請求得到 404、403、405 或表單驗證沒過，則什麼都不送。
- [x] 4a. （審查後追加）假設偵測得到版本號（例如有 `SENTRY_RELEASE`），當一般請求正常完成，則什麼都不送（沒有使用統計）。
- [x] 5. 假設沒有設定監控金鑰（本機、測試、CI），當網站啟動與發生錯誤，則不啟用監控、不嘗試連線，網站與全部測試照常。
- [x] 6. 假設改完，當跑 `check --deploy` 與 CI，則全部通過，正式環境的安裝清單有這次需要的套件。（PR #51：`backend`、`frontend` 通過，「Production dependencies」只裝 `requirements.txt` 有裝到 `sentry-sdk`，`check --deploy`、`gunicorn --check-config` 通過）
- [x] 7. 假設未登入或用一般使用者登入，當打開管理員測試網址，則回 404，監控什麼都不送。
- [x] 8. 假設用管理員登入，當打開管理員測試網址，則回 500，監控收到一筆，錯誤類型看得出是測試用，而且沒有使用者身分。
- [ ] 9. （人工，本人）假設正式環境已設定金鑰，當本人用管理員帳號打開測試網址，則幾分鐘內收到 email，打開看得到錯誤，而且看不到第 4.2 節「不能送」的任何東西。

## 6. 待決問題

- [x] ~~**1. 用哪個工具？**~~ → A：Sentry 免費版，資料放歐盟區（2026-10-16）
- [x] ~~**2. 前端錯誤要不要一起送？**~~ → A：這次不做（2026-10-16）
- [x] ~~**3. 要不要知道是哪個使用者？**~~ → A：完全不送（2026-10-16）
- [x] ~~**4. 上線後怎麼確認真的有送出？**~~ → A：管理員測試網址，見 4.3（2026-10-16）
- [x] ~~**5. 錯誤訊息要不要送（計畫時發現：錯誤訊息可能帶資料）**~~ → A：只送類型和位置，訊息一律拿掉（2026-10-16）

---

## 完成後回報（由 AI 填寫）

- **改了哪些檔案、為什麼**：
  - `config/monitoring.py`（新增）：`init(dsn, transport=None)` 設定 Sentry 與 `_scrub`（`before_send`）。`transport` 讓測試收下要送出的內容、不連網。
  - `config/settings.py`：有 `SENTRY_DSN` 才呼叫 `init`；變數用小寫，避免出現在 debug 頁。
  - `requirements.txt`：`sentry-sdk==2.72.0`、`certifi`、`urllib3`。
  - `screening/views.py`、`screening/urls.py`：`MonitoringTestError` 與 `/monitoring-test`（非 superuser 一律 404）。
  - `screening/tests/test_monitoring.py`（新增）：透過 `WSGIHandler`（跟 gunicorn 同一條路）送請求，檢查實際送出的內容。
  - `docs/roadmap.md`：Phase 6 打勾；Phase 7 隱私權說明頁補一句第三方服務。
- **驗收條件對應的測試**（`screening/tests/test_monitoring.py`）：
  - 1：`test_unhandled_error_is_sent_with_type_path_and_place`
  - 2：`test_answer_error_sends_no_form_cookie_or_user`
  - 3：`test_register_error_sends_no_password_or_name_in_message`、`test_login_error_sends_no_password`（審查後補）
  - 3a：`test_register_error_sends_no_password_or_name_in_message`
  - 3b：`test_logged_error_sends_only_the_template`、`test_logs_before_the_error_do_not_ride_along`
  - 4：`test_normal_refusals_send_nothing`
  - 4a：`test_no_usage_data_even_with_a_release`
  - 5：`MonitoringSwitchTests`（子行程，沒有／空的／有 DSN）
  - 6：本機 `check --deploy` 已在既有測試中通過；PR #51 的 CI 通過（含只裝正式清單）
  - 7、8：`test_test_page_is_404_for_everyone_but_admins`、`test_test_page_sends_a_test_error_for_admins`
  - 9：人工，本人（步驟見 4.4）
  - 每一道限制（10 道）都拿掉試過，各自有測試變紅。
- **規格以外的決定**：
  - 請求標頭與查詢字串整組不送：測試發現 `X-CSRFToken` 不在 Sentry 自己的過濾清單；規格「會送」只列路徑與方法，照此解讀（已補進 4.2）。
  - 審查後經本人決定追加：`logger.error` 只送樣板（B）、麵包屑關掉、使用統計關掉（4.1、4.2、驗收 3b、4a）。
- **這次用到的新概念**（各用一句話解釋）：
  - DSN：Sentry 給的專案網址兼金鑰，SDK 用它知道要送去哪裡。
  - `before_send`：每筆事件送出前呼叫的函式，可以改內容或丟掉。
  - transport：SDK 實際送出內容的那一層；測試換成存進清單，就能檢查真正會送出的內容。
  - SDK 預設整合：logging、Django、session 追蹤等會自己啟用，不設定也會送東西。
  - 原始碼片段（source context）：Sentry 附上每一層呼叫前後幾行程式碼；寫在程式碼裡的字串會被帶出去。
- **面試可能追問的 2–3 題**：Q93–Q95（見 `docs/interview.md`）。
- **建議寫進 decisions/ 的內容**：見對話（放「帳號與安全」`security.md`）。
