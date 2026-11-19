# 資安健檢後的修補

日期：2026-11-19。分支：`chore/security-dependency-bumps`。沒有規格 issue：範圍與決定是本人在對話中點選的，整理在下面「本人的決定」。

## 本人的決定

1. 升級有已知漏洞的套件：certifi、brotli、sqlparse。
2. PDF 匯入加資源上限和數值檢查，每個帳號每小時 20 份。
3. 登入失敗次數限制：同一帳號名稱 15 分鐘 5 次、同一 IP 一小時 20 次；一般登入、`/admin/`、刪帳號與確認本人的密碼確認都算（ADR 0071）。
4. Sentry 不收網址裡的 token；本機 log 只留訊息樣板；重設密碼信用 `SITE_URL`。
5. 匿名寫入限流：問答小助手提問每 IP 每小時 30 次、訪客計數 API 每 IP 每小時 60 次（推翻 grill Q15 的「不限流」）。
6. 登出與刪帳號時清掉瀏覽器裡的訪客篩檢結果。
7. CSP 放進同一個 PR（ADR 0072）。
8. Email 確認（ADR 0070）：沒確認的信箱收不到重設信和提醒信；上線前已填的信箱算已確認；連結 3 天；Google 的信箱算已確認；畫面照 `docs/design/email-confirmation-mockup.html`（本人已核准）。
9. 不改：登入保留 14 天；ADR 0038（忘記密碼頁直接說沒註冊）；ADR 0057（Google 同信箱頁照舊）。

## 套件升級

| 套件 | 舊版 → 新版 | 漏洞 | 對聽伴的影響 |
|---|---|---|---|
| certifi | 2026.7.22 → 2026.10.23 | GHSA-6q48-6c7w-9gw2：emSign 根憑證的中間憑證金鑰外洩 | 對外 HTTPS（Google／LINE 登入、Resend、Sentry）可能被中間人攔截，主因 |
| brotli | 1.2.0 → 1.2.1 | GHSA-9v8h-qqgm-4m35 | whitenoise 只壓縮不解壓，風險低 |
| sqlparse | 0.5.5 → 0.6.1 | GHSA-f2ff-p2ww-7p4p 等 5 項 DoS | 只有管理指令用到，風險低；0.6.1 是最後一版，作者停止維護 |

OSV 再比對一次，`requirements.txt` 31 個套件都沒有已知漏洞。

## 驗收條件 → 測試

| 決定 | 證明的測試 |
|---|---|
| 1 | 沒有測試斷言：版本寫在 `requirements.txt`，證據是 OSV 比對（上一節）、`pip check` 無衝突、`collectstatic` 用新版 brotli 產生 `.br`、`sqlmigrate` 正常，以及 CI 用新版套件跑完整套測試 |
| 2 | `test_apple_hearing_test.ReadingLimitTests`（不讓本程序長大、逾時放棄；Linux 上記憶體上限，macOS 跳過）、`UnreadableTests` 的超出圖表、刻度顛倒、未來日期；`test_audiogram_import` 的每小時 20 份（數字寫死在測試裡、一小時後恢復、別帳號不受影響） |
| 3 | `test_sign_in_limits`（5 次後連正確密碼也擋、不同帳號不受影響、跨 IP 也算、IP 20 次、IP 一小時後恢復、成功不算、15 分鐘後恢復、admin、刪帳號、確認本人、密碼確認連帶擋登入、IP 被擋時兩個密碼確認頁也擋、密碼確認頁的失敗算進 IP、快取裡沒有帳號名稱和 IP 原文） |
| 4 | `test_monitoring` 的 `test_secret_links_reach_sentry_as_their_route`、`test_a_link_no_page_answers_reaches_sentry_without_its_path`、`test_the_local_log_keeps_only_the_template`；`test_password_reset` 的 `test_with_a_site_url_the_link_is_on_it_whatever_the_host` |
| 5 | `test_qa_search` 的 `test_thirty_an_hour_from_one_address_then_a_wait`；`test_clinic_cards` 的 `test_sixty_an_hour_from_one_address_then_nothing_is_added`（兩者都含別的 IP 不受影響、一小時後恢復） |
| 6 | `frontend/src/logout.test.js` 的登出與刪帳號兩則 |
| 7 | `test_content_security_policy`（標頭含 style-src 允許內嵌樣式、每個內嵌 script 帶 nonce、每次不同、admin 與 API、模板檢查）；e2e `ContentSecurityPolicyTest`（拿掉一個 nonce 時這個測試會失敗，已驗證） |
| 8 | `test_email_confirmation`（註冊／補上 email／LINE 寄信、Google 算已確認、連結不露出信箱、GET 不確認、按下才確認、未同意隱私權也能開、差一分鐘滿 3 天還能用、過期、改信箱後失效、帳號設定標籤與兩個重寄鈕、每小時 3 封、一小時後可再寄、別帳號的重寄各算各的、忘記密碼紅框、共用信箱只寄已確認的、結果頁與帳號設定的提醒、排程只寄已確認、實際跑排程指令不寄給未確認的信箱、從 0043 實際跑 migration 到 0044 讓舊信箱算已確認）；`test_add_email` 第 8 條改為確認後才能打開提醒；e2e 帳號設定提醒區塊加上「還沒確認」狀態的 200% 字級檢查 |
| 9 | 登入 14 天：`test_sign_in_limits` 的 `test_a_sign_in_still_lasts_14_days`；ADR 0038：既有的 `test_password_reset`（`NOT_REGISTERED` 斷言）；ADR 0057：既有的 `test_google_same_email`，這次沒有改到，照舊通過 |

## 測試結果

- 後端 3208 個測試通過（`--parallel`），1 個跳過（Linux 才跑的記憶體上限）；照交叉審查修完後 3217 個通過。
- 前端 771 個測試通過。
- e2e 480 個測試通過（交叉審查後的修正沒動到畫面，沒有重跑）（`--parallel 4`，含新的 `ContentSecurityPolicyTest`）。第一輪有 17 個失敗：15 個是 Playwright 的 `wait_for_function` 被 CSP 擋下（改用 `wait_until`）；1 個是確認信提示裡的長信箱，在 200% 字級下把同意頁撐寬（提示條改成可以斷行）；1 個是測試帳號的信箱沒標成已確認。修完第二輪全過。
- `ruff check .`、`ruff format --check .` 通過。
- `check --deploy --fail-level WARNING` 在模擬的正式環境變數下通過。

## 沒有驗證到的

- PDF 子程序 256MB 記憶體上限只在 Linux 生效：CI（Linux）會跑合成 PDF；本人真正的 Apple PDF 在 Linux 上還沒試過，部署後請在正式站匯入一次確認讀得出來。
- 確認信實際寄出、在手機信箱裡點按鈕的流程，要部署後由本人實際操作。

## 交叉審查

需要：diff 碰到登入與權限、會改資料的 migration（0044 把現有信箱標成已確認）。

Codex 審查（2026-11-19，基準 `main` ec4d7bc5、HEAD 98e16475），Standards 1 項、Spec 3 項，都已處理：

- **S1 刪帳號與確認本人沒套 IP 上限**（Standards 的缺測是同一件事）：密碼確認表單只用帳號名稱計數。改成兩個頁面都把請求傳進去，跟登入共用帳號和 IP 兩種計數；先寫兩個測試看它失敗（打對密碼仍回 302），修完通過。
- **S2 對不上路由的網址原樣送 Sentry**：改成 `https://網域/<no-route>`，路徑和查詢字串都不送；先寫測試看它失敗，修完通過。
- **S3 缺斷言**：照上表補齊（style-src、快取只存雜湊［把雜湊拿掉時這個測試會失敗，已驗證］、各限制的一小時恢復與 IP／帳號隔離、3 天內還能用、實際跑排程指令、實際跑 migration、登入 14 天）。套件升級沒有適合的測試斷言，證據見表格第 1 列。

## 部署

- 照 `build.sh` 部署：會裝新套件、跑 migration 0044。
- 0044 會把所有已填的信箱標成已確認，不刪不改其他資料。
