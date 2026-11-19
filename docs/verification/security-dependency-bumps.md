# 升級有已知漏洞的三個 Python 套件

日期：2026-11-19。分支：`chore/security-dependency-bumps`。

## 原因

資安健檢時，拿 `requirements.txt` 去比對 OSV 漏洞資料庫，有三個套件的版本有已公開的漏洞：

| 套件 | 舊版 → 新版 | 漏洞 | 對聽伴的影響 |
|---|---|---|---|
| certifi | 2026.7.22 → 2026.10.23 | GHSA-6q48-6c7w-9gw2：內含的 emSign 根憑證，其中間憑證金鑰外洩 | 網站對外連 HTTPS 時（Google／LINE 登入、Resend 寄信、Sentry）會信任這些憑證，理論上可能被中間人攔截。這是升級的主因 |
| brotli | 1.2.0 → 1.2.1 | GHSA-9v8h-qqgm-4m35：解碼器越界寫入 | whitenoise 只用它壓縮靜態檔，不解壓外來資料，實際風險低 |
| sqlparse | 0.5.5 → 0.6.1 | GHSA-f2ff-p2ww-7p4p 等 5 項：CPU 阻斷攻擊（DoS） | Django 只在管理指令（例如 `sqlmigrate`）用到，使用者輸入碰不到，實際風險低 |

注意：sqlparse 0.6.1 是作者宣布的最後一版，之後不再維護、也不出安全修補。它是 Django 的必要套件，之後要跟著 Django 官方的處理方式走。

## 測試

- `pip install -r requirements.txt` 成功；`pip check` 沒有相依衝突。
- 後端 3159 個測試通過（`--parallel`）。
- `check --deploy --fail-level WARNING` 在模擬的正式環境變數下通過。
- `collectstatic` 成功，whitenoise 用新版 brotli 產生了 388 個 `.br` 壓縮檔。
- `sqlmigrate screening 0001` 成功（會用到 sqlparse 排版 SQL）。
- 再比對一次 OSV：`requirements.txt` 的 31 個套件都沒有已知漏洞。
- 只升級套件版本，沒碰計分、門檻、migration、權限，不需交叉審查。

## 部署

合併後照 `build.sh` 部署，第一步的 `pip install -r requirements.txt` 會在 VPS 上換成新版本。
