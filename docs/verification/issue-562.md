# 運作檢查網址（#562，規格 #561）

日期：2026-11-16。分支：`feat/562-uptime-check`（接在 `docs/561-backup-restore` 後面；那邊合併後，這個 PR 只剩 #562 的改動）。

不需交叉審查：不收資料、不涉及登入、計分、門檻，也沒有 migration（規格 #561 實作決定）。自審時 Standards 軸指出加進同意書檢查的開放清單算擦邊的「權限」，本人 2026-11-16 決定照規格不做交叉審查（這個網址不顯示任何人的資料，放進清單不會讓任何人看到更多東西）。

## 做了什麼

- 新網址 `/uptime-check`（`GLOSSARY.md`「運作檢查」）：對資料庫問一次 `SELECT 1`。問得到回 200 `ok`，問不到回 503 `database unavailable`，都是純文字。
- 資料庫的錯誤在網址裡接住、自己回 503，不往上丟：外部監控自己會開問題、寄信，不需要每分鐘再送一筆錯誤到 Sentry。Sentry 的 Django 整合本來就不收 `django.request` 那條「回了 5xx」的紀錄（套件原始碼 `ignore_logger("django.request")`），所以接住之後 Sentry 什麼都收不到。
- 只收 GET、HEAD；不快取（`never_cache`）、不讓搜尋引擎收錄（`X-Robots-Tag: noindex, nofollow`）。
- 加進同意書檢查的「還沒同意也能開」清單，理由寫在清單上方的註解。
- 不放進任何頁面的連結、導覽或頁尾。第 2 項做 sitemap 時要把它列在「不公開」那一邊。
- 收尾清單補上第 5 段（設定 Sentry）、第 6 段（兩次停機測試）。

## 實作時的做法（請本人知道）

- **英文名稱**：網址 `uptime-check`、函式 `uptime_check`，避開 `health`（站內的 health 指使用者的健康資料，拷問決定 Q14）。
- **POST 在正式站會先得到 403**：Django 的 CSRF 檢查（防止別的網站冒用你的身分送表單）在網址之前，沒帶 CSRF token 的 POST 在那裡就被擋了；帶了 token 才會到網址回 405。兩種都不做任何事。本人 2026-11-16 決定接受 403、不加 `csrf_exempt`，規格驗收 4 改成「回 405 或 403」（#561 留言）。測試用 Django 測試客戶端（預設不檢查 CSRF），驗的是 405 那一種。
- **資料庫停了、但瀏覽器帶著登入 cookie 打開時**：同意書檢查會先讀登入狀態，這時會出錯回 500、也會送一筆到 Sentry。Sentry 的探測機器人不帶 cookie，不會碰到；只有本人自己在停機測試時用登入中的瀏覽器打開才會（清單的停機測試用 `curl`，不帶 cookie）。本人 2026-11-16 決定不修。
- **清單第 5 段照 Sentry 說明寫欄位，沒寫按鈕位置**：Sentry 官方說明只列了欄位（網址、方法、間隔、逾時、失敗與恢復次數），沒寫在哪裡按。清單註明畫面以 Sentry 為準，對不上就停下來回報。

## 驗收條件

測試檔：M＝`screening/tests/test_monitoring.py`。

- [x] 1 正常、沒登入：回 200、`text/plain; charset=utf-8`、內容只有 `ok`：M:350、M:351、M:352
- [x] 2 資料庫連不上：回 503，Sentry 收不到任何事件（用跟 gunicorn 一樣的 WSGI 路徑送請求，Sentry 換成記錄用的假傳送）：M:292、M:293
- [x] 3 正常與 503 兩種都帶 `X-Robots-Tag: noindex, nofollow`、`Cache-Control` 含 `no-store`、沒有 cookie；503 的內容是 `database unavailable`；沒有建立 session：M:361、M:362、M:363、M:364、M:365、M:366
- [x] 4 POST 回 405、HEAD 回 200：M:370、M:371（驗收 4 已改成「405 或 403」，正式站沒帶 CSRF token 的 POST 先得到 403，見上）
- [x] 5 已登入但還沒同意最新同意書：照樣回 200 `ok`，沒被帶去同意頁：M:377、M:378
- [x] 清單第 5、6 段：Sentry 設定與兩次停機測試，每一步都有確切指令和「做對了會看到什麼」，沒有真的位址或帳號（規格驗收 25 的這一段）
- [x] 21–24 本人照清單設定 Sentry、停兩次服務（#569），見下方「本人操作」

每一條都先寫測試、看它失敗（原因各是：網址不存在、沒問資料庫、沒有禁止收錄的標記、POST 照樣 200、被轉去同意頁 302），再寫最少的程式讓它通過。

## 自動測試

提交 `91480cf` 之後的工作區（自審修正已改，還沒 commit 時跑），2026-11-16，本機：

| 項目 | 結果 |
|---|---|
| Django 測試（`--parallel 4`） | 2610 項通過 |
| `ruff check`、`ruff format --check` | 通過 |

前端、e2e 沒跑：沒有改畫面、樣式或前端程式。

## 自審

`/mattpocock-skills:code-review`，基準 `docs/561-backup-restore`（只看 #562 的兩個 commit）。

- **Standards**：沒有硬性違規（第 2 條不用登入要寫理由、第 24 條禁止快取都有做到；名稱避開 `health`；文件沒有真的位址或帳號）。判斷題都修了：回應的寫法重複兩次，改成先決定內容和狀態碼、只寫一次；測試 `test_post_is_refused` 其實也驗了 HEAD，改名 `test_answers_only_get_and_head`；補 503 內容的斷言（清單 6-3 要本人照這段字比對）；清單 6-3 改用 `pg_lsclusters`（`systemctl is-active postgresql` 只看總開關）。兩個測試各寫一次「資料庫停掉」的 mock，沒抽出來（只有兩處，抽出來反而要多看一層）。
- **Spec**：驗收 1–5 都有斷言（見上）。補了兩處清單：5-1 加 `sudo ufw status`（上面的 `curl` 驗不到防火牆有沒有限定 IP）；第 6 段註明服務名稱出自 `vpsdeploy.md` 哪一段。POST 回 403、帶 cookie 時回 500 兩項由本人決定（見「實作時的做法」）。

## 本人操作（#569，規格驗收 21–24）

2026-11-16，本人照收尾清單第 5、6 段操作，代理從終端機讀結果、從 Mac 每 30 秒查一次網站。

- **部署**：正式站從 `2b5731c` 更新到 `903d53f`（照 VPS 筆記的步驟，先跑 `hearwell-backup.service` 備份；`check --deploy` 沒有問題，沒有 migration）。從外面查 `https://tingpal.tw/uptime-check` 回 `ok 200`、帶 `X-Robots-Tag: noindex, nofollow` 與含 `no-store` 的 `Cache-Control`、沒有 `Set-Cookie`；用 `SentryUptimeBot/1.0` 打也是 `200`；`ufw status` 的 443 來源是 Anywhere。
- **發現：正式站的錯誤監控一直沒開**。VPS 的 `.env` 沒有 `SENTRY_DSN`，11/12 搬家之後正式站的錯誤都沒送到 Sentry。本人補上原本 Render 時期那個專案的 DSN 並重啟；從 VPS 用同一份設定送一筆測試訊息，Sentry 收到。補的時候 SSH 斷線、重連，檢查 `.env` 12 個變數都在、`SECURE_HSTS_SECONDS=3600`、沒有 nano 留下的 `.env.save`，重啟後 HSTS 仍是 `max-age=3600`。
- **正式站原本沒有管理員帳號**：查 `is_superuser` 回 0 筆，本人用 `createsuperuser` 建了一個（之後用 `/monitoring-test` 測錯誤監控、進管理後台用）。
- [x] 規格驗收 21：Sentry 專案（原 Render 時期的 python-django）新建 1 個 uptime 監控，網址 `https://tingpal.tw/uptime-check`、間隔 1 分鐘、環境 `production`，警示直接連到這個監控、寄 email 給本人。VPS 的 Nginx 紀錄看到 `SentryUptimeBot` 每分鐘來一次，每次不同 IP，都是 `200`。
- [x] 規格驗收 22：05:24:30 UTC（台灣 13:24）停 `hearwell`；從外面查一直是 `502`；13:28 收到 Sentry 的停機信（約 4 分鐘）；`systemctl start hearwell` 後 `active`，運作檢查 `ok 200`、首頁 `200`。
- [x] 規格驗收 23：05:29:52 UTC（台灣 13:29）停 `postgresql`；從外面查運作檢查一直是 `database unavailable 503`、**首頁一直是 `200`**（只查首頁抓不到這種故障）；13:33 收到 Sentry 的停機信（約 3–4 分鐘）；`systemctl start postgresql` 後 `pg_lsclusters` 為 `online`，運作檢查回 `ok 200`，網站不用重啟；本人登入看得到紀錄。
- [x] 規格驗收 24：見上兩條的時間。本人回覆通知、登入、監控頁恢復都「沒問題」；手機有沒有響、信在哪個分頁，本人沒有另外說明。
- **雜訊**：補上 DSN 之後，Sentry 收到 `DisallowedHost`（有人用不是 tingpal.tw 的網址連進來，Django 照設定擋下，多半是掃描機器人）。網站的處理是對的；要不要讓 Nginx 先擋掉、或請 Sentry 忽略這一種，留給本人決定。
