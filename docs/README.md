# 專案文件

先看[開發進度與待辦](roadmap.md)。新需求、正式規格與實作票放在 [GitHub Issues](https://github.com/minuet878-prog/HearWell/issues)；本目錄按用途整理研究、歷史紀錄與操作參考。

| 要找什麼 | 入口 |
|---|---|
| 目前進度、下一步與待定構想 | [Roadmap](roadmap.md) |
| 成人問卷需求、來源、計分審定與拆票 | [功能規劃](planning/README.md) |
| 2026-10-18 之後的決策與理由（ADR） | [`adr/`](adr/) |
| 每張票的測試、審查與本人驗收紀錄 | [`verification/`](verification/) |
| 母規格結案後的復盤（流程與工具改善） | [`retros/`](retros/) |
| 無障礙量測、已修問題與後續待辦 | [無障礙](accessibility/README.md) |
| API 格式 | [API 文件](api/README.md) |
| 部署操作筆記 | [部署參考](deployment/README.md) |
| 代理的 issue tracker、標籤與領域文件設定 | [代理工作設定](agents/README.md) |
| Phase 0–10 的歷史規格 | [規格索引](specs/README.md) |
| Phase 0–10 的計畫審查、實作審查與 PR 說明 | [審查索引](reviews/README.md) |
| 舊決策的理由與踩過的坑 | [歷史決策](decisions/README.md) |
| 本機面試筆記 | `interview/README.md`（不進版控） |

## 文件用途

- `planning/`：規劃與來源核對的補充資料；正式驗收條件及工作票仍以對應 GitHub issue 為準。
- `specs/`、`reviews/`、`decisions/`：歷史參考，查找時從各自索引進入；新工作不沿用舊規格檔流程。
- 新決策依[領域文件設定](agents/domain.md)記錄於 `docs/adr/`；有實際決策時才新增。
- `verification/`：驗收紀錄跟程式放在同一個 PR，本人驗收通過才合併。
- `interview.md` 保留為本機面試筆記的舊入口，內容已移至分類資料夾。
