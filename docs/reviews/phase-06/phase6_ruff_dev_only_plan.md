# Phase 6-2 正式環境不裝開發工具：實作計畫

規格：[phase6_ruff_dev_only.md](../../specs/phase-06/phase6_ruff_dev_only.md)

## 要改的檔案

| 檔案 | 改什麼 |
|---|---|
| `requirements.txt` | 刪掉 `click==8.4.2`、`h11==0.16.0`、`ruff==0.16.1` 三行 |
| `requirements-dev.txt` | 加 `ruff==0.16.1`（版本不變） |
| `.github/workflows/ci.yml` | `backend` job 多一個步驟「Production dependencies」（見下） |
| `README.md` 第 127 行、`claude.md` 第 141 行 | 「開發用清單多了 debug-toolbar」改成「debug-toolbar 和 ruff」 |
| `docs/specs/phase-06/phase6_ci.md` | 驗收 9、11 打勾（合併後已確認） |

`build.sh` 不動：它本來就只裝 `requirements.txt`。

## CI 新步驟的設計

放在 `backend` job 裡，**不另開 job**：另開 job 的話，你要回 GitHub 把它加進必要檢查；放在 `backend` 裡，它失敗 `backend` 就紅，ruleset 不用改。

步驟內容：
1. 開一個全新的虛擬環境（只在這次 CI 裡），只裝 `requirements.txt`
2. 用這個環境跑 `python manage.py check --deploy --fail-level WARNING`：跟 `build.sh` 在 Render 上跑的是同一個指令
3. 環境變數照正式環境的樣子：`DEBUG` 設成 `False`；`SECRET_KEY` 在 CI 執行時用亂數產生（設定檔裡不寫任何金鑰）；`DATABASE_URL` 沿用 CI 的臨時資料庫（系統檢查不會真的連）

這一步跟其他檢查一樣，前一步失敗也照跑（`!cancelled()`）。

## 驗證（先確認會失敗，再改）

1. **改之前**，在 scratchpad 開一個乾淨的虛擬環境、只裝目前的 `requirements.txt`：列出套件應該**有** `ruff`、`click`、`h11`（驗收 1、6 現在是失敗的）。
   **這是試驗**：虛擬環境放在 scratchpad，不在 repo 裡，做完刪掉。
2. 改完再開一個乾淨環境重做一次：三個都沒有（驗收 1、6）；`check --deploy` 通過（驗收 4）。
3. 本機 `ruff check .`、Django 測試、前端測試照跑（驗收 2）。
4. 推上去開 PR：CI 綠，紀錄裡看得到新步驟、乾淨環境、只裝正式清單（驗收 3、7）。
5. 試驗：丟棄用分支把 `whitenoise` 搬到開發清單，開 PR 到這條分支 → Django 測試綠、新步驟紅、看得到缺 `whitenoise`（驗收 8）。做完關 PR、刪分支。
6. 合併後看 Render 部署紀錄（驗收 5）。

## 查到的事實：移除 `click`、`h11` 的風險比想像小

`requirements.txt` 不是完整的鎖定清單：`pip install` 會自動補裝每個套件需要的其他套件。
所以就算有哪個正式套件其實需要 `click`，pip 也會自己裝回來，不會因為清單少一行就啟動失敗。
真正的風險只有「程式直接 `import click`」，`grep` 過，沒有。

## 實作中追加（2026-10-16，本人同意）

驗收 8 的試驗第一次沒變紅：`whitenoise` 只出現在 `MIDDLEWARE`、`STORAGES`，`check --deploy` 不會 import 它們。
本機重現後，在 `check --deploy` 後面加 `gunicorn --check-config config.wsgi`（照 Render 啟動指令 `gunicorn config.wsgi` 把程式載入一次），
並加 `pip list` 讓紀錄看得到裝了什麼。重跑試驗變紅。`brotli`（只在 collectstatic 用）仍抓不到，不做。
