# Phase 6-2 正式環境不裝開發工具：審查報告

- 規格：[phase6_ruff_dev_only.md](../../specs/phase-06/phase6_ruff_dev_only.md)
- 比對：`git diff main...chore/ruff-dev-only`（含規格打勾）
- 審查：`reviewer` subagent（2026-10-16）；結論：沒有 bug，沒做「不做」清單的事；本機 Django 333、前端 135、ruff 通過

| # | reviewer 意見 | 嚴重程度 | 主 session 查證 | 分類 |
|---|---|---|---|---|
| 2-1 | 計畫檔只寫 `check --deploy`，實作多了 `pip list`、`gunicorn --check-config` | 低 | 屬實：加 gunicorn 是試驗沒抓到 whitenoise 後補的，計畫檔沒跟上 | 要修（文件）：計畫檔補一段，規格「規格以外的決定」寫明 |
| 2-2 | 註解說「照 Render 啟動指令」無法在 repo 驗證 | 低 | 本人 2026-10-16 提供 Render Start Command：`gunicorn config.wsgi`，與註解一致 | 不改 |
| 3-1 | 驗收 1、6 只印 `pip list`，以後有人把 ruff 加回正式清單 CI 不會擋 | 低 | 屬實。加回來的後果是部署多裝一個沒用的套件，不會壞 | 不改（規格沒要求；交本人決定） |
| 3-2 | 驗收 5 未勾、完成後回報空白 | 低 | 驗收 5 要合併部署後才能看 | 補（收尾第 9 步） |
| 3-3 | 本機 `ruff` 指令是 Homebrew 的 | — | 這次驗收 2 用的是 `py313/bin/ruff`（開發清單裝的 0.16.1）；CI 只有開發清單那份 | 不改 |
