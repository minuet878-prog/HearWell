# Phase 6-1 CI 審查報告

- 規格：[phase6_ci.md](../../specs/phase-06/phase6_ci.md)
- 比對：`git diff main...ci/github-actions`
- 審查：`reviewer` subagent（2026-10-16）；主 session 查證與分類待補

| # | 項目 | 嚴重程度 | reviewer 建議 |
|---|---|---|---|
| 1 | `main` 的 concurrency：同一組最多一個在跑、一個排隊，連續合併三次時中間那次會被取消，跟 `ci.yml` 第 11–15 行註解「每個 commit 都有自己的結果」不符 | 低 | 要修：`main` 改用 commit 分組，或改註解 |
| 2 | 規格第 72 行的驗證方式（在本分支弄壞再拿掉）沒更新成實際做法（丟棄用分支 `ci/trial`），「規格以外的決定」也是空的 | 低 | 要修（文件） |
| 3 | 驗收 10 只用 API 確認了設定，沒看到紅色 PR 被擋就打勾；`ci/trial` 的目標是 `ci/github-actions`，`main` 的規則不作用在它上面。附帶：以後改 job 名稱，PR 會卡在「等待檢查」 | 低到中 | 補驗證：開目標 `main` 的草稿 PR 故意失敗，看合併按鈕 |
| 4 | 官方元件用版本標籤，沒有釘到 commit SHA | 很低 | 不改（唯讀權限、只用官方元件、規格沒要求） |

reviewer 也查證了：`DEBUG: "True"` 是必要的；debug-toolbar 已被 `test_settings` 移除；`ruff` 隨 `requirements-dev.txt` 一起裝到；前一步失敗後面照跑的條件邏輯正確；沒做「不做」清單的事；本機 Django 333、前端 135 全部通過。

## 主 session 查證與分類（2026-10-16）

| # | 分類 | 查證 | 理由 |
|---|---|---|---|
| 1 | 要修 | GitHub 文件明寫：同一個 concurrency group 最多一個在跑、一個排隊，新的排隊會取消舊的排隊，跟 `cancel-in-progress` 無關。沒有實際連合三次重現（要動 `main`） | 註解寫的保證做不到。改成 PR 用分支分組、`main` 用 commit 分組，一行就能讓註解成真；Render 也就能看到每個 `main` commit 的結果 |
| 2 | 要修（文件） | 規格第 72 行確實還是舊做法 | 規格要反映實際做的事；完成後回報也要寫進「規格以外的決定」 |
| 3 | 補驗證 | 屬實：`ci/trial` 的目標是 `ci/github-actions`，`main` 的規則管不到它 | 開一個目標 `main` 的一般 PR（不是草稿，草稿本來就不能合併），故意讓 ruff 失敗，用 API 看 `mergeStateStatus` 是 `BLOCKED`，並請本人看合併按鈕；做完關掉、刪分支 |
| 4 | 不改 | — | 同意 reviewer：唯讀權限、只用 GitHub 官方元件、規格沒要求 |
| 5（主 session 自己發現） | 要修（文件） | 驗收 9 的後半「合併進 `main` 後也跑一次」還沒發生，卻已經打勾 | 跟驗收 11 一樣，合併後才能確認；先取消打勾 |
