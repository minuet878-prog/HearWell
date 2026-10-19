# 開發與上線前檢查：審查報告（審查者原文）

- 審查對象：分支 `chore/phase0-checks` 未 commit 的變更（build.sh、claude.md、config/settings.py、config/test_settings.py、config/urls.py、screening/tests.py、.python-version、requirements-dev.txt）
- 規格：docs/specs/phase-00/phase0_dev_checks.md
- 審查日期：2026-10-15

## 0. 實際跑過的東西

| 項目 | 結果 |
|---|---|
| 全部測試 `py313/bin/python manage.py test --settings=config.test_settings` | 212 個測試，OK |
| `DEBUG=True`＋有裝 toolbar（暫存腳本，子行程） | `check` 0 問題；toolbar 在 INSTALLED_APPS、middleware 第一個；`/__debug__/render_panel/` 可解析；沒有 HSTS 標頭 |
| `DEBUG=False`＋隨機 50 字元金鑰（暫存腳本，只呼叫 SecurityMiddleware，不碰 DB） | HTTPS 請求：`Strict-Transport-Security: max-age=3600; includeSubDomains`（無 preload）；HTTP 請求：301 導向 https；`/__debug__/` → 404 |
| `DEBUG=False SECRET_KEY=shortkey manage.py check --deploy --fail-level WARNING` | **W009，rc=1**（建置會失敗） |
| `SECRET_KEY` 以 `django-insecure-` 開頭 | **W009**（建置會失敗） |
| 專案複製到暫存目錄（沒有 `.env`、沒有 `staticfiles/`），給一個連不到的 DATABASE_URL 跑 `check --deploy` | 0 問題（1 silenced）→ 建置階段沒有 collectstatic 結果、DB 連不到都不影響 |
| 同上但沒有 DATABASE_URL | `ImproperlyConfigured`（settings 匯入時就要 DATABASE_URL） |

暫存腳本與複製目錄都在 scratchpad，已刪除。沒有對資料庫下任何指令（`check` 不加 `--database` 不會連 DB）。

---

## 1. Bug／部署會失敗的地方

### 1-1【中】Render 上的 SECRET_KEY 不夠強，第一次部署就會被 W009 擋下
- 位置：build.sh:7（`check --deploy --fail-level WARNING`）× Render 環境變數 `SECRET_KEY`
- 描述：W009 的條件是「少於 50 字元、少於 5 種字元、或以 `django-insecure-` 開頭」。以前沒跑 `check --deploy`，所以正式金鑰從沒被檢查過。若當初用 Render 的「Generate」按鈕產生（Render 產生的是 base64 的隨機值，長度通常 40 多字元，**可能不到 50**），或手動貼了較短的字串，建置會直接失敗。
- 重現：`DEBUG=False SECRET_KEY=shortkey py313/bin/python manage.py check --deploy --fail-level WARNING` → W009、rc=1。
- 影響：失敗發生在建置第 7 行，舊版本照常服務，**不會弄壞正式站**，但會擋住部署。
- 建議：合併前請本人到 Render 確認 `SECRET_KEY` 長度 ≥ 50、不是 `django-insecure-` 開頭；不夠就用 `get_random_secret_key()` 換一把。注意：換金鑰會讓所有人的登入 session 失效（要重新登入），選離峰時間。

### 1-2【低】Render 的 `PYTHON_VERSION` 環境變數會蓋過 `.python-version`
- 位置：.python-version:1
- 描述：檔案格式 `3.13.15\n` 正確，放在 repo 根目錄，Render 認得。但 Render 的優先順序是 `PYTHON_VERSION` 環境變數 > `.python-version`。若 Render 上曾設過 `PYTHON_VERSION`，這個檔案不會生效。另外 Render 必須提供 3.13.15 這個版本；沒有的話建置一開始就失敗（同樣不影響舊版本）。
- 建議：合併前看一下 Render 環境變數沒有 `PYTHON_VERSION`；驗收 11 看 build log 的 Python 版本即可確認。

### 1-3【低（既有問題，非本次引入）】`ALLOWED_HOSTS` 設成空字串時 check --deploy 抓不到
- 位置：config/settings.py:44
- 描述：`"".split(",")` 得到 `[""]`，不是空 list，W020 不會觸發，但網站會全部回 400。
- 重現：`DEBUG=False ALLOWED_HOSTS= SECRET_KEY=<50字元> manage.py check --deploy --fail-level WARNING` → 0 問題。
- 建議：不在本次範圍（規格「不做」：不改現有設定），記下來即可。

### 檢查過、沒有問題的部分
- **建置階段讀得到的東西**：`check` 只需要 settings 能匯入（SECRET_KEY、DATABASE_URL 環境變數存在即可），不連 DB、不需要 `staticfiles/` 或 manifest；whitenoise 沒有自己的 system check。放在 `npm`／`collectstatic`／`migrate`／`loaddata` 前面是對的，`set -o errexit` 讓它失敗即中止。
- **HSTS 與 SECURE_SSL_REDIRECT**：HTTP 請求先被 301 導向 HTTPS（不帶 HSTS），HTTPS 回應才帶 HSTS，這是 Django 的正常順序。正式站 SSL 導向已經上線且運作（沒有無限導向），表示 Render 後面 `request.is_secure()` 為真，HSTS 會正常送出。
- **debug-toolbar 的各種組合**：
  - `DEBUG=False`：不進 INSTALLED_APPS、URL 不註冊（`/__debug__/` 404）。
  - `DEBUG=True`＋有裝：正常載入、URL 註冊、`check` 0 問題。
  - `DEBUG=True`＋沒裝：`try/except ImportError` 跳過，urls.py 的條件看 INSTALLED_APPS，不會去 import，網站正常。
  - 測試：test_settings 把 app 與 middleware 濾掉，urls.py 讀的是過濾後的 INSTALLED_APPS，所以 toolbar URL 也不註冊。toolbar 8.0.0 自帶的 E001（測試時誤裝）不會觸發。
- **W021 略過**：只略過這一個，旁邊有理由（settings.py:83–84）。`SILENCED_SYSTEM_CHECKS` 放在 `if` 外面不影響行為（W021 只有 `--deploy` 才出現）。

---

## 2. 有沒有多寫

### 2-1【低】`test_production_python_matches_tests`（screening/tests.py:2980）不在驗收條件裡
- 描述：驗收 11 是人工；這個測試是額外加的。它的價值是「有人改了本機 Python 卻忘了改 `.python-version`」時會提醒，算合理。但它把**本機的 patch 版本**綁死：本機 py313 升到 3.13.16、或在 CI 用別的 3.13.x 跑，測試就會紅。
- 建議：保留可以，但要知道它會在升級本機 Python 時故意失敗；若覺得太嚴，可改成只比對主次版本（3.13）。由本人決定。

其餘改動都對得上規格「要做」，沒有看到多餘的設定選項或抽象。`try/except ImportError` 是驗收 4 需要的，test_settings 的過濾是規格第 3 節要求的。

---

## 3. 驗收條件與測試

| 驗收 | 測試 | 意見 |
|---|---|---|
| 1 | 人工 | 我的探測已確認 DEBUG=True＋有裝時 toolbar 載入、URL 可解析。 |
| 2 | `test_production_settings`（2931） | 只驗 INSTALLED_APPS／MIDDLEWARE，**沒驗「連不到它的網址」**。見 3-1。 |
| 3 | `test_tests_never_load_toolbar`（2945）＋全套測試通過 | 見 3-3（在沒 `.env` 的機器上是空轉）。 |
| 4 | `test_debug_without_dev_packages_still_works`（2939） | 用 `sys.modules["debug_toolbar"] = None` 模擬沒裝，`check` 會載入 urls，抓得到錯。好。 |
| 5 | `test_toolbar_only_in_dev_requirements`（2952） | 好。 |
| 6 | `test_production_settings` | **只驗 settings 值，沒驗回應標頭**。見 3-2。 |
| 7 | `test_debug_without_dev_packages_still_works` | 只驗 `SECURE_HSTS_SECONDS == 0`（等同不送標頭，可接受）；但只在「沒裝 toolbar」組合下驗。 |
| 8 | `test_deploy_check_passes_with_warnings_as_errors`（2960） | 斷言 `"no issues (1 silenced)"` 且 silenced 只有 W021，抓得到「多略過一個」或「出現新警告」。好。 |
| 9 | `test_build_runs_deploy_check_before_anything_changes`（2967） | 字串比對 build.sh 順序與參數，夠用。 |
| 10、11 | 人工 | — |

### 3-1【低／補測試】驗收 2 的「連不到網址」沒有斷言
- 位置：screening/tests.py:2889–2906（DUMP）、2931
- 描述：目前是靠「app 不在 → urls.py 不註冊」間接推論。若有人把 urls.py 的條件改成 `if settings.DEBUG or True:` 之類，測試抓不到。
- 建議：在 DUMP 裡加一行 `resolve("/__debug__/")` 是否 404，輸出到 JSON。

### 3-2【低／補測試】驗收 6 沒驗實際標頭
- 位置：screening/tests.py:2931–2937
- 描述：驗收 6 寫的是「回應有 `Strict-Transport-Security: …`」，測試只看 settings 值。我用 `RequestFactory().get("/", secure=True)` 丟給 `SecurityMiddleware` 確認標頭正確（見第 0 節），這個做法不碰 DB，可以直接放進 DUMP。
- 建議：DUMP 裡加 SecurityMiddleware＋RequestFactory 取出標頭字串，斷言等於 `max-age=3600; includeSubDomains`。

### 3-3【低】`test_tests_never_load_toolbar` 在沒有 `.env`（或 `.env` 沒 `DEBUG=True`）的機器上是空轉
- 位置：screening/tests.py:2945、config/test_settings.py:10–12
- 描述：toolbar 只有 `DEBUG=True` 才會被加進去。CI 或別台機器通常沒設 DEBUG，就算把 test_settings 的過濾刪掉，這個測試也照樣通過；只有在本人這台（`.env` 有 `DEBUG=True` 且裝了 dev 套件）才真的有在驗。
- 建議：改成子行程、強制 `DEBUG=True`、`DJANGO_SETTINGS_MODULE=config.test_settings`，再看 INSTALLED_APPS 與 `/__debug__/`。這樣在哪台機器都會真的驗到過濾。

### 3-4 其他機器／CI 跑 subprocess 測試會不會失敗
- 子行程用 `{**os.environ, ...}`，DATABASE_URL 來自父行程（父行程本身也是靠它才跑得起來測試），沒有 `.env` 時兩邊一樣需要外部提供 DATABASE_URL，**不會多出新的失敗條件**。
- `.env` 裡的 `DEBUG`、`SECRET_KEY` 不會蓋過子行程明確設定的值（`load_dotenv` 預設不覆寫已存在的環境變數）。
- 子行程只跑 `check`（不加 `--database`），不連資料庫，即使 DATABASE_URL 指向正式庫也不會碰到。
- 例外：`test_production_python_matches_tests` 在不同 patch 版的 Python 上會失敗（見 2-1）。
- 沒有空轉的問題（除 3-3）：子行程失敗時 `returncode` 斷言會擋下，並附 stderr。

---

## 4. 規格「不做」清單與 CLAUDE.md 規則

- 沒有改頁面、計分、API 行為；沒動 DEBUG／SECRET_KEY／SSL／cookie 既有設定；HSTS 沒超過 1 小時；沒開 preload；沒加其他工具。✔
- 金鑰：測試用 `get_random_secret_key()` 在子行程內產生、不落地；程式碼裡沒新增任何金鑰（settings.py:41 的 `django-insecure-...` 是既有的 DEBUG fallback，非本次引入）。✔
- 不碰正式資料庫：子行程只跑 `check`，不連 DB。✔
- 垃圾不進版控：`.python-version`、`requirements-dev.txt` 是該進版控的；`py313/`、`.env`、`staticfiles/` 已在 .gitignore。✔

### 4-1【低】規格「要做」的 roadmap HSTS 待辦還沒寫
- 位置：config/settings.py:32（註解寫「see roadmap」）、docs/roadmap.md（未修改）
- 描述：規格第 2 節「要做」包含「roadmap 加 HSTS 時效拉長的待辦」，目前 roadmap 沒有，註解指向的內容不存在。若預計在收尾步驟補上就沒問題，提醒不要漏掉。

### 4-2【低，範圍外】`ruff` 在正式環境套件清單裡
- 位置：requirements.txt（`ruff==0.16.1`）
- 描述：既有問題，現在有了 requirements-dev.txt，ruff 其實適合搬過去。規格「不做」沒有涵蓋但也沒要求，建議記為之後的小任務，本次不改。

---

## 5. 部署風險

### 5-1【中】第一次部署：SECRET_KEY 強度（同 1-1）
最可能讓這次部署失敗的就是它。失敗是安全的（舊版繼續跑），但要先確認。

### 5-2【低】Python 3.14.3 → 3.13.15
- 所有套件在本機 3.13.15 都裝得起來、測試通過，requirements.txt 的版本都有 3.13 的 Linux wheel（psycopg2-binary、rpds-py、brotli 等），風險低。
- Session 用 JSON 序列化、沒有 pickle 快取，降版不會讓既有 session 讀不出來。
- Render 換 Python 版本會重建虛擬環境，第一次建置會比較久，屬正常。
- 要確認的只有 1-2（`PYTHON_VERSION` 環境變數、Render 是否提供 3.13.15）。

### 5-3【低】HSTS 開了回不去的風險
- 時效 1 小時：最壞情況（HTTPS 壞掉）使用者最多被卡 1 小時。要撤回就把 `SECURE_HSTS_SECONDS` 設 0 部署，瀏覽器下次透過 HTTPS 收到 `max-age=0` 就會忘掉。
- `includeSubDomains` 只影響 `<你的服務>.onrender.com` 底下的子網域，目前沒有，不影響其他 Render 服務。
- 真正要小心的是之後拉到 1 週、1 年，以及**改用自訂網域時**：includeSubDomains 會套到自訂網域所有子網域（規格已寫「改用自訂網域時重新評估」）。
- 本機開發是 HTTP、`DEBUG=True` 不送標頭，不會讓 localhost 被瀏覽器記住。✔

### 5-4【低，提醒】以後任何 deploy 警告都會擋部署
- `--fail-level WARNING` 也包含第三方套件的 deploy check（例如 drf-spectacular 在 `--deploy` 時會產生 schema，有 schema 警告就會失敗）。這是規格要的行為，只是之後改 API 時，本機要記得跑一次 `check --deploy`（測試 `test_deploy_check_passes_with_warnings_as_errors` 已經會擋，等於每次跑測試都會檢查到）。

---

## 6. 沒問題的部分（簡列）

- build.sh 的位置與參數正確，失敗會在任何變更前中止。
- HSTS 只在 `DEBUG=False` 時設定，值、子網域、無 preload 都符合規格；與 SSL 導向的互動正常。
- debug-toolbar 在 DEBUG=True/False、有裝/沒裝、測試四種情況行為都正確（已實測）。
- urls.py 用 INSTALLED_APPS 當條件，與 settings、test_settings 一致。
- `.python-version` 格式正確（`3.13.15\n`），未被 ignore。
- requirements-dev.txt 用 `-r requirements.txt` 疊加、版本有釘死。
- W021 只略過一項且附理由；`check --deploy` 實測 0 問題（1 silenced）。
- 全部 212 個測試通過。

---

## 主流程查證與分類（2026-10-15）

### 合併前本人確認（不改程式）
- **1-1／5-1 SECRET_KEY 強度（中）**：重現屬實（短金鑰 → W009、建置失敗）。正式金鑰只有本人看得到，請到 Render 確認：至少 50 字元、至少 5 種不同字元、不是 `django-insecure-` 開頭。不夠的話要換新金鑰；代價是所有人的登入狀態失效（session 用這把金鑰簽章），要重新登入一次。
- **1-2 `PYTHON_VERSION` 環境變數（低）**：Render 上若有設，會蓋過 `.python-version`。請本人確認沒有設。

### 補測試
- **3-1 驗收 2「連不到 toolbar 的網址」→ 已補**：查證屬實，目前只檢查 app 清單。補：`DEBUG=False` 的設定下 `/__debug__/` 解析不到。
- **3-2 驗收 6 實際標頭 → 已補**：查證屬實，目前只檢查設定值。補：`DEBUG=False` 的設定下，用 Django 測試 client 發一個 HTTPS 請求，回應標頭是 `max-age=3600; includeSubDomains`、沒有 `preload`（另開程序、不連資料庫）。
- **3-3 `test_tests_never_load_toolbar` 在沒有 `.env` 的機器上空轉 → 已改**：查證屬實，它依賴本機 `.env` 的 `DEBUG=True`。改成另開程序、明確設 `DEBUG=True` 載入 `config.test_settings` 再檢查，不靠 `.env`。

### 收尾時處理
- **4-1 roadmap 的 HSTS 時效待辦 → 已寫**：規格「要做」的一項，排在第 9 步更新 roadmap 時寫。

### 不改
- **2-1 Python 版本綁到最後一碼**：刻意的。鎖版本就是要「測過的版本＝上線的版本」；本機升級時測試失敗，正好提醒要一起改 `.python-version`。
- **1-3 `ALLOWED_HOSTS` 空字串、4-2 `ruff` 在正式套件清單**：本次之前就有，不在規格範圍；列為之後的待辦。
- **5-2 Python 退回 3.13、5-3 HSTS 回不去、5-4 之後任何警告都會擋部署**：都是規格已經接受的取捨（時效從 1 小時開始就是為了 5-3）。

### 修改後（2026-10-15）
- 補測試時另外發現：`/__debug__/` 本身不是 toolbar 的網址（只有子路徑，例如 `/__debug__/render_panel/`），原本的「連不到網址」斷言永遠成立。已改用真實存在的子路徑，並先確認有裝 toolbar 的開發設定「連得到」，才檢查測試設定「連不到」。
- 試驗：拿掉 `test_settings.py` 的排除，`test_tests_never_load_toolbar` 會失敗；已還原。
- Django 212、前端 31 全部通過；ruff 通過。

