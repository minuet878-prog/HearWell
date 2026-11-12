# #450 正式站搬到 VPS：隱私權說明、同意書第 4 版、HSTS 改用環境變數

日期：2026-11-12。規格：#450；票：#451、#452。基準：`origin/main` `4ec412a`；整合分支：`feat/450-vps-cutover`。決策：ADR 0041、0042；詞彙「正式站」「備份」。

狀態：等本人實際操作驗收，以及確認伺服器上的四項（驗收 12–15）。自動測試與自審（Standards／Spec）都已通過，自審後本人選的三項已修。這張碰到同意書與正式環境安全設定，依 AGENTS.md 應做交叉審查；2026-11-12 本人決定這次略過交叉審查，直接驗收。沒有操作真實資料，也沒有新增 migration。

## 測試結果（整合分支 `351a0f6`）

- 單元測試 1874 項通過（`--parallel 4`）；`ruff check .`、`ruff format --check .` 通過。
- 沒有前端改動，沒跑前端測試；e2e 裡沒有斷言這次改的文字（實作時查過 `e2e/main_flow.py`），沒跑整套 e2e。
- 本機用 `DEBUG=False ALLOWED_HOSTS=tingpal.tw SECURE_HSTS_SECONDS=3600` 跑 `check --deploy --fail-level WARNING` 通過（1 silenced）。CI 的正式環境檢查要等推上去才會跑，結果補在 PR。

## 做了什麼

- **HSTS 改用環境變數**（#451）：正式環境讀 `SECURE_HSTS_SECONDS`，沒設就用中文報錯、不啟動；子網域寫死強制 HTTPS、不 preload；W021 的註解改成「自己的網域可以 preload，但幾乎撤不回，等 1 年期穩定後再評估」。CI 的正式環境檢查加上這個變數，`ALLOWED_HOSTS` 改成 `tingpal.tw`。roadmap 的 HSTS 時程改成 VPS 從 3600 起、每穩定 1 週升一階，Render 停在 86400。README 的環境變數表加一列。
- **隱私權說明**（#452）：「存放在哪裡、保存多久」改成 Vultr 日本東京機房、資料傳到日本、另一份加密備份在營運者在台灣的電腦、連線紀錄（含 IP）保存 14 天；最後一行「刪除的資料（包括刪除的帳號、超過 90 天的提問紀錄），在備份中最多再保留 10 天，之後自動清除」取代原本的 6 小時。「會交給誰」的 Render、Neon 換成 Vultr，Sentry 一字未改。
- **同意書第 4 版**，更新日期 2026/11/12；同意過第 3 版的人下次進健康資料頁面會再同意一次。
- `purge_question_log` 的 docstring、指令 help，以及 admin、問答小助手 view 裡的註解，都拿掉「沒有排程器」，改成「VPS 每天 02:30 執行，這裡也順便清」。行為不變，`build.sh` 不改。

## 實作判斷（請本人留意）

- **隱私權說明的句子是代理寫的**，事實照 ADR 0042。自審時發現「超過 90 天的提問紀錄」寫在「提問紀錄保存 90 天」那行之前，本人同意改成放在清單最後，並加測試守住順序。
- **審過句子的雜湊測試**（`test_family_zone.ReviewedPagesTests`）：這次改的七行加進放行清單，其他行的雜湊跟改前相同，代表整頁只有這幾行變。新句子請本人驗收時看過。
- **舊測試放寬**：「版本等於 3」改成「版本 ≥ 3」，第 4 版另由新測試釘住，沿用第 2 版時的寫法。
- **沒改的舊說法**：`ALLOWED_HOSTS` 錯誤訊息的例子還是 `hearwell.onrender.com`、`ci.yml` 與分享網址的註解提到 Render，留給收掉 Render 時一起處理。

## 驗收對照（#450）

勾選代表自動驗證；本人實際操作確認後再改狀態。deploy＝`screening/tests/test_deploy.py`；consent＝`screening/tests/test_consent.py` 的 `VpsPrivacyTests`。

| # | 驗收條件 | 驗證 | 證據 |
|---|---|---|---|
| 1 | 設 3600 → 標頭 `max-age=3600; includeSubDomains` | ✅ 自動 | deploy `test_production_settings`（`:84`、`:85`），真的發 HTTPS 請求 |
| 2 | 換成別的值 → 跟著變 | ✅ 自動 | deploy `test_hsts_seconds_follow_the_environment`（`:92`、`:93`） |
| 3 | 沒設 → 啟動失敗、中文訊息 | ✅ 自動 | deploy `test_production_requires_hsts_seconds`（`:101`、`:102`），本機 `.env` 補不進來 |
| 4 | 子網域 True、不 preload、W021 仍關掉 | ✅ 自動 | deploy `:86`、`:87`、`:141` |
| 5 | 開發環境沒有 HSTS、不需要變數 | ✅ 自動 | deploy `test_debug_without_dev_packages_still_works`（`:110`、`:111`） |
| 6 | `check --deploy --fail-level WARNING` 通過 | ✅ 自動 | deploy `test_deploy_check_passes_with_warnings_as_errors`（`:139`）；CI 待 PR |
| 7 | 看得到 Vultr、東京、台灣電腦、加密、14 天、10 天，刪除帳號與 90 天提問紀錄都適用 | ✅ 自動 | consent `test_where_it_is_kept_names_the_vps_the_backup_and_how_long`（`:552`）、`test_the_backup_days_come_after_the_90_days_they_refer_to`（`:567`）；`test_account_deletion.py:256` |
| 8 | 看不到 Render、Neon、美國俄亥俄州、6 小時 | ✅ 自動 | consent `test_the_old_hosts_and_6_hours_are_gone`（`:575`），比對整個回應 |
| 9 | 會交給誰：Vultr、Sentry，Sentry 不變 | ✅ 自動 | consent `test_who_receives_it_lists_vultr_and_sentry_as_before`（`:579`、Sentry 逐字比對、`:589`） |
| 10 | 顯示第 4 版和新日期 | ✅ 自動 | consent `test_it_shows_version_4_and_the_new_date`（`:592`） |
| 11 | 同意過第 3 版 → 轉去同意頁，同意後存第 4 版、回原頁 | ✅ 自動 | consent `test_who_agreed_to_version_3_agrees_again_to_version_4`（`:599`、`:601`、`:605`） |
| 12 | VPS 有每天 02:30 的 purge timer，排在 03:00 備份之前 | ⬜ 本人 | `systemctl list-timers` |
| 13 | Mac 自動刪除超過 8 天的備份，開機時補做 | ⬜ 本人 | Mac 的排程設定 |
| 14 | Nginx 連線紀錄保存 14 天 | ⬜ 本人 | `/etc/logrotate.d/nginx` 的 `rotate` |
| 15 | 合併前 Render（86400）、VPS（3600）都有 `SECURE_HSTS_SECONDS` | ⬜ 本人 | 兩邊的環境變數 |

隱私權說明承諾、但不在驗收條件裡的兩項（Spec 自審提醒）：

- **VPS 備份的保留天數**：備份腳本用 `find -mtime +7`，一份要滿 8 天才刪，在 10 天承諾以內。⬜ 本人確認腳本沒改過。
- **Mac 硬碟加密**：2026-11-12 在 Mac 上跑 `fdesetup status`，結果是 `FileVault is On`；備份資料夾權限 700。✅ 已查。

## 本人實際操作

- [x] 打開隱私權說明，讀「存放在哪裡、保存多久」與「會交給誰」兩段，句子 OK（2026-11-12 本人確認）
- [x] 用同意過第 3 版的帳號登入，進「紀錄」會被請去同意第 4 版，同意後回到原頁（2026-11-12 本人操作；伺服器紀錄：`POST /login` → `GET /my_hearing` 302 → `GET /consent?next=/my_hearing` → `POST /consent` 302 → `GET /my_hearing` 200）
