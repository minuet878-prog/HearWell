# 運作檢查網址（#562，規格 #561）

日期：2026-11-16。分支：`feat/562-uptime-check`（接在 `docs/561-backup-restore` 後面；那邊合併後，這個 PR 只剩 #562 的改動）。

不需交叉審查：不收資料、不涉及登入、計分、門檻、權限，也沒有 migration（規格 #561 實作決定）。

## 做了什麼

- 新網址 `/uptime-check`（`GLOSSARY.md`「運作檢查」）：對資料庫問一次 `SELECT 1`。問得到回 200 `ok`，問不到回 503 `database unavailable`，都是純文字。
- 資料庫的錯誤在網址裡接住、自己回 503，不往上丟：外部監控自己會開問題、寄信，不需要每分鐘再送一筆錯誤到 Sentry。Sentry 的 Django 整合本來就不收 `django.request` 那條「回了 5xx」的紀錄（套件原始碼 `ignore_logger("django.request")`），所以接住之後 Sentry 什麼都收不到。
- 只收 GET、HEAD；不快取（`never_cache`）、不讓搜尋引擎收錄（`X-Robots-Tag: noindex, nofollow`）。
- 加進同意書檢查的「還沒同意也能開」清單，理由寫在清單上方的註解。
- 不放進任何頁面的連結、導覽或頁尾。第 2 項做 sitemap 時要把它列在「不公開」那一邊。
- 收尾清單補上第 5 段（設定 Sentry）、第 6 段（兩次停機測試）。

## 實作時的做法（請本人知道）

- **英文名稱**：網址 `uptime-check`、函式 `uptime_check`，避開 `health`（站內的 health 指使用者的健康資料，拷問決定 Q14）。
- **POST 在正式站會先得到 403**：Django 的 CSRF 檢查（防止別的網站冒用你的身分送表單）在網址之前，沒帶 CSRF token 的 POST 在那裡就被擋了；帶了 token 才會到網址回 405。兩種都不做任何事。測試用 Django 測試客戶端（預設不檢查 CSRF），所以驗到的是 405。
- **資料庫停了、但瀏覽器帶著登入 cookie 打開時**：同意書檢查會先讀登入狀態，這時會出錯回 500、也會送一筆到 Sentry。Sentry 的探測機器人不帶 cookie，不會碰到；只有本人自己在停機測試時用登入中的瀏覽器打開才會。
- **清單第 5 段照 Sentry 說明寫欄位，沒寫按鈕位置**：Sentry 官方說明只列了欄位（網址、方法、間隔、逾時、失敗與恢復次數），沒寫在哪裡按。清單註明畫面以 Sentry 為準，對不上就停下來回報。

## 驗收條件

測試檔：M＝`screening/tests/test_monitoring.py`。

- [x] 1 正常、沒登入：回 200、`text/plain; charset=utf-8`、內容只有 `ok`：M:350、M:351、M:352
- [x] 2 資料庫連不上：回 503，Sentry 收不到任何事件（用跟 gunicorn 一樣的 WSGI 路徑送請求，Sentry 換成記錄用的假傳送）：M:292、M:293
- [x] 3 正常與 503 兩種都帶 `X-Robots-Tag: noindex, nofollow`、`Cache-Control` 含 `no-store`、沒有 cookie；沒有建立 session：M:361、M:362、M:363、M:364、M:365
- [x] 4 POST 回 405、HEAD 回 200：M:369、M:370（正式站沒帶 CSRF token 的 POST 先得到 403，見上）
- [x] 5 已登入但還沒同意最新同意書：照樣回 200 `ok`，沒被帶去同意頁：M:376、M:377
- [x] 清單第 5、6 段：Sentry 設定與兩次停機測試，每一步都有確切指令和「做對了會看到什麼」，沒有真的位址或帳號（規格驗收 25 的這一段）
- [ ] 21–24 本人照清單設定 Sentry、停兩次服務（#569），結果之後補進來

每一條都先寫測試、看它失敗（原因各是：網址不存在、沒問資料庫、沒有禁止收錄的標記、POST 照樣 200、被轉去同意頁 302），再寫最少的程式讓它通過。

## 自動測試

（跑完後補）

## 自審

（跑完後補）
