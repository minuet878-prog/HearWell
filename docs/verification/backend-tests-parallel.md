# CI 後端測試平行執行（小改動，無 issue）

日期：2026-11-17。基準：`8fccea71`（main，含 #701）；分支：`ci/backend-parallel`。

狀態：本機連跑通過；CI 上的實際秒數等這個 PR 的 run。只動 CI，沒碰計分、門檻、資料 migration、權限，
不需交叉審查。未操作真實資料；沒有啟動開發伺服器。

## 為什麼做

#701 把 e2e 分到兩台後，PR 上 backend job 4 分 14 秒（測試 209 秒）、e2e 每台約 6 分 20 秒，backend 成了第二慢的檢查，
也是必要檢查。main 合併後那次 backend 207 秒、e2e 兩台 337／409 秒。

## 改了什麼

- `.github/workflows/ci.yml`：Django tests 加 `--parallel 4`（CI 機器 4 核心），每個程序有自己的測試資料庫。
  `tblib` 早已在 `requirements-dev.txt`（e2e 平行時加的），失敗的 traceback 照樣傳得回來。

## 平行安全檢查

- 寫檔：`screening/tests` 沒有寫檔，只讀 `frontend/src`、`templates`、`screening/data` 等原始檔。
- 快取：`default` 是各程序自己的記憶體；`password_reset` 存在資料庫，每個程序各有一份測試資料庫。
- 子程序：`test_deploy`、`test_monitoring` 開子程序只讀設定、印出結果，不寫共用的東西。

## 驗收對照

| 需求 | 驗證 | 證據 |
|---|---|---|
| CI 的後端測試平行執行 | ✅ 看 diff | `ci.yml` 的 Django tests 步驟 |
| 平行時全部通過、不偶發失敗 | ✅ 本機執行 | `--parallel 4` 連跑 4 次：2777 項 154 秒 OK（#701 前試驗）；合併 #701 後 2864 項 132／66／67 秒，三次都 OK |
| 本機依序跑的時間對照 | ✅ 本機執行 | 2777 項依序 279 秒 |
| CI 上變快 | ⏳ 等 PR 的 CI | 原本 backend job 約 3.5–4 分（測試約 210 秒） |

## 測試與審查

- 只改 CI 一行，沒寫自動斷言；上表本機連跑就是驗證。
- 自審：看過 diff，沒有要修的項目。
- 本機指令（`AGENTS.md` 的「測試」）沒有改，照舊依序跑；要本機也平行，另外決定。
