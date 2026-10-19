# Phase 6-3 `ALLOWED_HOSTS` 設錯時部署要停下來：實作計畫

規格：[phase6_allowed_hosts.md](../../specs/phase-06/phase6_allowed_hosts.md)

## 要改的檔案

| 檔案 | 改什麼 |
|---|---|
| `config/settings.py` 第 44 行 | 讀 `ALLOWED_HOSTS` 的那一行改成幾行（見下） |
| `screening/tests.py` | 新增 `AllowedHostsTests`；既有 `DevChecksTests._run` 補一個環境變數（見下） |
| `.github/workflows/ci.yml` | 「Production dependencies」步驟加 `ALLOWED_HOSTS: hearwell.onrender.com` |
| `README.md` 第 189 行 | `ALLOWED_HOSTS` 改成「正式環境必填」 |
| `.env.example` 第 4 行附近 | 註解補「正式環境必填」 |
| `docs/specs/phase-06/phase6_ruff_dev_only.md` | 驗收 5 打勾、狀態「已完成」 |

## `settings.py` 的寫法

照同一個檔案裡 `SECRET_KEY`、`DATABASE_URL` 的既有寫法，不加新函式或新檔案：

1. 讀環境變數到小寫暫存變數 `allowed_hosts`（大寫會變成 Django 設定；`decisions/deploy.md` 記過這個坑）
2. 沒設（`None`）：正式環境 → `ImproperlyConfigured`（中文訊息）；本機 → 用 `"127.0.0.1,localhost"`
3. 用逗號切開、每段去掉前後空白、丟掉空的 → `ALLOWED_HOSTS`
4. 切完是空清單 → `ImproperlyConfigured`（不分本機或正式環境）

「沒設」要用 `is None` 判斷，跟「設成空字串」分開：前者本機可以用預設，後者一律是設錯。
（`SECRET_KEY` 那次用 `if not`，是因為兩種情況處理方式一樣；這次不一樣。）

## 測試（照既有 `DevChecksTests` 的做法）

設定在模組載入時就算好，所以每種情況開一個新的 Python 行程、帶不同的環境變數，看它印出清單或錯誤訊息。
專案裡 `DevChecksTests` 已經這樣做，直接沿用。

| 測試 | 環境變數 | 預期 | 驗收 |
|---|---|---|---|
| 空字串 | 正式、`""` | 失敗、訊息含 `ALLOWED_HOSTS` 和中文 | 1 |
| 只有空白、只有逗號 | 正式、`"   "`、`","` | 同上 | 2 |
| 有空白 | `"hearwell.onrender.com, localhost"` | 兩個網址、沒有前導空白 | 3 |
| 多打逗號 | `"a.com,,b.com,"` | `a.com`、`b.com` | 4 |
| 本機沒設 | 本機、不設 | `127.0.0.1`、`localhost` | 5 |
| 正式沒設 | 正式、不設 | 失敗、訊息含 `ALLOWED_HOSTS` | 8 |
| 本機空字串 | 本機、`""` | 失敗 | 9 |
| Render 的值 | 正式、`hearwell.onrender.com`，跑 `check --deploy --fail-level WARNING` | 通過 | 10 |

「不設」要從子行程的環境變數裡**拿掉** `ALLOWED_HOSTS`；另外 `.env` 會被 `load_dotenv` 讀進來，
測試時要確認本機 `.env` 裡沒有 `ALLOWED_HOSTS`（`.env.example` 裡是註解掉的），否則「沒設」測不到。我會先檢查你的 `.env` 有沒有這一行（只看有沒有，不印值）。

**既有測試要改一處**：`DevChecksTests._run` 會用 `DEBUG=False` 開子行程，新規則下沒設 `ALLOWED_HOSTS` 就會啟動失敗。
它裡面的請求用的網址是 `localhost`，所以補 `"ALLOWED_HOSTS": "localhost"`。不改測試的判斷，只補環境。

先跑一次新測試、確認失敗，再改 `settings.py` 讓它通過。

## 驗證

- 本機：Django 全部測試、`ruff check .`、前端測試
- CI：推上去開 PR，全部通過（驗收 6）；「Production dependencies」用 `hearwell.onrender.com` 跑 `check --deploy`（驗收 10 的 CI 版）
- 合併後：Render 部署成功、網站正常（驗收 7）
