# 審查報告：phase6_error_monitoring（錯誤監控）

- 規格：`docs/specs/phase-06/phase6_error_monitoring.md`
- 審查者：`reviewer` subagent（唯讀），2026-10-16
- 基準：`main`；分支 `feat/error-monitoring` 已 stage 的變更（`git diff --cached main`）

## 審查結論（reviewer 原文摘要）

主要流程沒問題：500 會送；訊息、標頭、查詢字串、表單、cookie、使用者都有擋；404／403／405 不送；測試網址權限正確。有 1 項要修（log 事件帶分數），1 項建議改設定（session 追蹤），2 項補測試／不改。

- bug：只有下方第 1 項是實際的外洩路徑。連鎖例外的訊息會逐一拿掉；SQL 麵包屑預設不帶參數值。
- 多寫：未發現問題（`transport` 參數是測試必要的最小設計）。
- 驗收：3 缺登入的測試；6 待 CI；9 人工待做；其餘都有透過真的 WSGIHandler 跑的測試。
- 不可違反的規則：規則 3 有第 1 項的違反；其他未發現問題。
- 測試：375 通過、0 失敗。

## 發現與查證

### 1. `logger.error` 會變成 Sentry 事件，內容帶分數

- **位置**：`config/monitoring.py` 的 `init`（logging 整合是預設開啟）；觸發點 `screening/scoring.py:104`、`:110`
- **reviewer 說**：Sentry 預設把 ERROR 等級的 log 轉成獨立事件，`logentry.formatted`、`logentry.params` 帶出分數；`_scrub` 不碰 `logentry`。INFO 以上的 log 也會變成麵包屑，隨下一筆 500 送出。
- **查證**：屬實，已重現。初始化 CaptureTransport 後呼叫 `scoring.classify(999, "hhie-s")`，收到一筆事件：`logger: screening.scoring`，`formatted: "Score 999 out of range for questionnaire 'hhie-s'"`，`params: [999, …]`。
- **分類**：**要修＋補測試**。修法有兩種，交本人決定（見對話）。

### 2. 偵測到版本號時，每個請求都會送一筆 session 統計

- **位置**：`config/monitoring.py` 的 `init`（`auto_session_tracking` 預設 True）
- **reviewer 說**：release 由 `SENTRY_RELEASE`、`git rev-parse` 或幾個平台的環境變數自動偵測；偵測得到時會送 release health 資料，規格「不做」。
- **查證**：屬實，已重現。設定 `SENTRY_RELEASE` 後送一個正常的 GET，收到的是 `sessions` 項目（沒有任何錯誤也送）。Render 是否會被偵測到不確定（偵測清單裡沒有 Render，但執行目錄若留著 `.git` 就會）。
- **分類**：**要修**。明確設 `auto_session_tracking=False`，補測試（有版本號時一般請求什麼都不送）。

### 3. 驗收 3 只測了註冊，沒測登入

- **查證**：屬實。`test_normal_refusals_send_nothing` 的登入是 200，驗證不到「出錯時不帶密碼」。
- **分類**：**補測試**。讓登入在驗證成功後出錯（500），斷言送出內容沒有密碼。

### 4. 測試網址沒有限定 GET

- **分類**：**不改**。非管理員一律 404，只影響管理員自己。

### 其他

- reviewer 說規格狀態「實作中」不在模板裡：**不屬實**，`spec_template.md` 的狀態列有「實作中」。不改。
- 驗收 6：本機 `check --deploy` 已包含在測試裡通過；CI 的「只裝正式清單」步驟待 PR。

## 合併前：CI 偶發失敗（2026-10-16）

- **現象**：PR #51 第二次 CI（`b7b0913`，只改文件）`test_logged_error_sends_only_the_template` 失敗：`'999' unexpectedly found`；同一份程式第一次 CI、本機都通過。
- **根本原因**：
  1. 測試在整份送出內容裡找 `999`，撞到時間戳記的微秒（`…55.087999Z`）。
  2. 那個時間戳記屬於麵包屑——測試之間換回的「沒有 DSN」client 用預設 `max_breadcrumbs=100`，仍在記錄，下一個測試 `init` 後殘留的麵包屑跟著送出。正式環境只在啟動時 `init` 一次，照那個順序實測沒有麵包屑。
- **修正（只改測試）**：`setUp` 在 `init` 後清掉所有範圍的麵包屑；分數改用 7 位數 `4242424`；該測試補斷言「沒有麵包屑」（修正前本機穩定失敗）。全部測試連跑 3 次通過；拿掉 `max_breadcrumbs=0` 仍有測試變紅。
