# iPhone 主畫面的聽伴用 LINE 登入失敗（#608）

日期：2026-11-16。基準：`95d80b73`（origin/main，#603 合併後）；分支：`fix/line-login-home-screen-app`；commit：`1860c4a2`（重現測試與修正）、`f469be40`（自審修正）；PR #609。

狀態：本機自動測試、自審（Standards／Spec）和 CI 都通過。這次碰到登入，照規則要交叉審查，**本人 2026-11-16 決定跳過**。LINE 的回呼網址只登記了正式站和本機，主畫面 app 連不到本機，所以 iPhone 實機驗收在合併、部署後才做：**本人 2026-11-16 在正式站驗收通過**（見最下面）。未操作真實資料，沒有啟動開發伺服器，不需 migration。

## 問題與根本原因

本人回報（iPhone 實機）：從主畫面的聽伴按「使用 LINE 帳號登入」→ 跳到 LINE app → 跳到 Safari → 顯示「登入沒有完成，請再試一次。」

原因：這一趟的 `state`、`nonce`、PKCE 存在 session 裡（`screening/oidc.py` 的 `begin()`）。iPhone 上主畫面 app 和 Safari 的 cookie 各自獨立；LINE 的自動登入會開 LINE app，同意後把回呼網址交給 Safari。Safari 的 session 裡沒有這一趟，`finish()` 判定「no trip in the session」。這個檢查是對的，沒有放寬。

同一個原因也影響主畫面 app 裡的保存卡、確認本人、新增登入方式。#506 的實機驗收只測了 LINE 裡和 Safari。

## 做法

- `frontend/src/pwa-nav.js`：在 iPhone 主畫面 app（`navigator.standalone === true`）留 cookie `home_screen_app=1`。伺服器從 User-Agent 分不出主畫面 app 和 Safari，所以用 cookie；它正好留在造成問題的那一個 cookie 罐子裡。iPhone 對腳本寫的 cookie 只留 7 天，所以每一頁都重寫。
- `screening/oidc.py`：`begin()` 看到這個 cookie，就加上 `PROVIDERS[provider].in_home_screen_app`。LINE 是 `disable_auto_login=true`（[LINE 官方參數](https://developers.line.biz/en/docs/line-login/integrate-line-login/)，2026-11-16 查），Google 沒有。四個 LINE 起點都經過 `begin()`。
- 代價：主畫面 app 裡第一次用 LINE 要輸入 LINE 的 email 和密碼，之後有單一登入就按一下。這是 2026-11-14「LINE 不要求重新登入」的例外，補記在 `docs/planning/open-access/login-research.md` 第 10 節。
- 多一個登入用的 cookie，不含個資；隱私權說明「只用登入和送出表單需要的 cookie」仍成立，文案沒改。
- 沒有採用：讓回呼不靠 session、在 Safari 完成登入。那樣別人可以拿自己開始的登入連結騙人同意，而且主畫面 app 還是沒登入。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。

| 條件（#608） | 驗證 | 證據 |
|---|---|---|
| 1 主畫面 app 開始 LINE 登入，授權網址帶 `disable_auto_login=true` | ✅ 自動 | `screening/tests/test_line_sign_in.py:230`；修正前失敗 |
| 2 保存卡、確認本人、新增登入方式也帶，且不帶 `prompt`、`max_age` | ✅ 自動 | 保存卡同上（`line_save_card` subTest）；`screening/tests/test_line_confirm_identity.py:152`；`screening/tests/test_line_sign_in_methods.py:253` |
| 3 不在 iPhone 主畫面 app 時不帶 | ✅ 自動 | `screening/tests/test_line_sign_in.py:237`；`frontend/src/pwa-nav.test.js:98`（Android 主畫面 app、瀏覽器分頁不留 cookie） |
| 4 Google 的授權網址不變 | ✅ 自動 | `screening/tests/test_google_sign_in.py:109` |
| 5 只有 iPhone 主畫面 app 留 cookie | ✅ 自動 | `frontend/src/pwa-nav.test.js:89`、`:98`；修正前 `:91` 失敗（`expected '' to contain 'home_screen_app=1'`） |
| 6 state、nonce、PKCE、回呼只用一次不放寬 | ✅ 自動 | `finish()` 沒有改動；既有的 LINE、Google 測試照過 |
| 7 iPhone 主畫面的聽伴用 LINE 登入：不跳去 LINE app 和 Safari，回到聽伴且已登入 | ✅ 本人 | 2026-11-16 正式站實機：出現 LINE 的網頁登入，輸入 LINE 的 email 和密碼後回到聽伴、已登入 |
| 8 同一支 iPhone 的 Safari 用 LINE 登入，照舊自動登入成功 | ✅ 本人 | 2026-11-16 正式站實機：正常 |

## 測試結果

- 單元測試：`Ran 2638 tests … OK`
- 前端：`Test Files 38 passed`、`Tests 587 passed`
- Ruff：`ruff check`、`ruff format --check` 都通過
- CI（PR #609）：3 項檢查通過；合併後 `main`（`79bbc18e`）的 CI 也通過
- 沒有跑 e2e：畫面沒有變動

## 自審

`/mattpocock-skills:code-review`，基準 `origin/main`。

- Standards：沒有硬性違規。四項判斷題（`in_home_screen_app` 的命名、新欄位只有 LINE 用、cookie 寫在 `pwa-nav.js`、`navigator.standalone` 判斷出現兩次）都照現有寫法，沒有改；`oidc.py` 的註解照建議寫清楚了。
- Spec：確認本人、新增登入方式沒有自己的斷言，已補（`f469be40`）；和 2026-11-14 決定的衝突已請本人確認並補記。沒有範圍蔓延。

## 本人驗收

2026-11-16，正式站（`https://tingpal.tw`），PR #609 合併、部署後。部署確認：線上的 `pwa-nav.js` 已有 `home_screen_app`。

- [x] 7 iPhone 主畫面的聽伴按「使用 LINE 帳號登入」：不跳去 LINE app 和 Safari，在 LINE 的網頁輸入 email 和密碼後回到聽伴、已登入
- [x] 8 同一支 iPhone 的 Safari 用 LINE 登入：正常

已知代價（實機確認）：主畫面 app 裡第一次用 LINE 要輸入 LINE 的 email 和密碼。長輩記不得 LINE 密碼時，可以改用 Safari 開聽伴登入；要不要在登入頁加這句提示還沒決定。
