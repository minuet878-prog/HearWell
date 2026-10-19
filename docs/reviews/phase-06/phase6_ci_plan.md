# Phase 6-1 CI 實作計畫

規格：[phase6_ci.md](../../specs/phase-06/phase6_ci.md)

## 要新增／修改的檔案

| 檔案 | 動作 | 內容 |
|---|---|---|
| `.github/workflows/ci.yml` | 新增 | CI 設定（唯一的程式改動） |
| `docs/specs/phase-06/phase6_ci.md` | 修改 | 驗收打勾、完成後回報 |
| `docs/roadmap.md`、`docs/interview.md` | 修改 | 收尾 |

不改任何既有程式碼、測試、`requirements*.txt`、`build.sh`。

## `ci.yml` 的設計

**觸發**（驗收 9）：`pull_request`（任何目標分支）＋ `push` 到 `main`。

**權限**（驗收 7）：`permissions: contents: read`，CI 只能讀 repo。

**取消舊的**（驗收 12）：同一個 PR 用同一組 `concurrency`，新的來就取消舊的。
`main` 上**不取消**：連續合併兩次時，每個 commit 都要有自己的結果，Render 才知道能不能部署。

**兩個 job 平行跑**（job：CI 裡一組獨立的工作，各自開一台機器）：

1. `backend`
   - PostgreSQL 18 服務容器（`postgres:18`，密碼寫死 `postgres`，只活在這次 CI 裡）（驗收 6）
   - Python 版本讀 `.python-version`（驗收 8）；`pip install -r requirements-dev.txt`
   - `ruff check .`（驗收 3）
   - `python manage.py test --settings=config.test_settings`（驗收 2）
2. `frontend`
   - Node 版本讀 `.node-version`（驗收 8）；`npm ci --prefix frontend`
   - `npm test --prefix frontend`（驗收 4）
   - `npm run build --prefix frontend`（驗收 5）

**同一個 job 裡，前一步失敗後面照樣跑**：例如 `ruff` 抓到錯，Django 測試照樣跑完。
一次就看得到所有問題，不用修一個、推一次、再看下一個。

**環境變數**：`DATABASE_URL` 指向 CI 臨時的資料庫；`DEBUG=True`，跟本機 `.env` 一樣。

**用到的 GitHub 官方元件版本**：`actions/checkout@v7.0.1`、`actions/setup-python@v7.0.0`、`actions/setup-node@v7.0.0`。
都寫到確切版本，而且都發布滿兩週（setup-node 最新的 v7.1.0 是 10-08 發布的，還不到兩週）。

## 查到的坑：CI 必須設 `DEBUG=True`

`settings.py` 在 `DEBUG` 不是 True 時，會開 `SECURE_SSL_REDIRECT`，而且要求 `SECRET_KEY`。
CI 如果不設 `DEBUG`：
- 沒有 `SECRET_KEY` → 一啟動就報錯；
- 補了 `SECRET_KEY` → 測試的每個請求都被轉址到 https，回 301，幾乎全部失敗。

本機的測試一直都是在 `.env` 的 `DEBUG=True` 下跑的，CI 照做就跟本機一致。
（Django 跑測試時會自己把 `DEBUG` 關掉，所以這不會讓測試看到除錯頁。）

## 驗證方式（試驗）

CI 沒辦法寫進 `tests.py`，改用「推上去看結果」。**這是試驗**：故意弄壞的東西放在另一條丟棄用的分支，不進 `ci/github-actions` 的歷史，也不需要改寫歷史（force-push）。

1. 推 `ci/github-actions`，**先不開 PR** → 確認 CI 沒跑（驗收 9 前半）
2. 開 PR → CI 跑、四項都綠、紀錄裡看得到 Postgres 18、Python 3.13.15、Node 24.21.0（驗收 1、6、8、9）
3. 從這條分支開丟棄用分支 `ci/trial`，一個 commit 同時弄壞四處（沒用到的 import、一個必失敗的 Django 測試、一個必失敗的前端測試、import 不存在的檔案），開草稿 PR（目標是 `ci/github-actions`）→ 四項都紅、各自的錯誤訊息看得到（驗收 2–5）
4. 在 `ci/trial` 連推兩個 commit → 第一次被取消（驗收 12）
5. 關掉草稿 PR、刪掉 `ci/trial`（本機與遠端）
6. 給你 GitHub 分支保護的設定步驟 → 你設定後，看 PR 的合併按鈕（驗收 10）
7. 給你 Render「CI 通過後才部署」的設定步驟 → 合併後看部署紀錄（驗收 11，合併後才能確認）

推分支、開 PR 會發到 GitHub。你同意這份計畫，就等於同意這幾次推送和開草稿 PR。
