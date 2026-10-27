# 結果類型的摘要片段依用途拆開（#409）

日期：2026-10-27。基準：`26257af`（origin/main）；分支：`refactor/409-summary-snippets`。票：[#409](https://github.com/minuet878-prog/HearWell/issues/409)（#385 驗證時記下的後續；2026-10-27 拷問四題後寫入決定與驗收條件）。

狀態：2026-10-27 本人回覆人工驗收三項都通過。自動測試全過；自審要修 0 項。只動模板與結果類型的兩個屬性、畫面不變，不碰計分、門檻、migration 或權限：依 AGENTS.md 不需交叉審查（#409 決定 5）。沒有操作真實資料。

## 本人決定（2026-10-27）

1. 每種結果類型兩個片段：「摘要」（純文字，首頁上次結果與聽力報告共用，首頁自己包 `<div>`）與「紀錄列」（我的紀錄每一列）。拿掉 `place`。分級沒有摘要。
2. 依用途分資料夾、依類型取檔名：`summaries/`、`record_rows/`，跟 `comparisons/` 同一套。
3. 常模比對的摘要自己讀 `submission.result.norm_summary`，拿掉 `ioi_ha` 參數。
4. 報告的 SSQ12 那一行直接 include `summaries/average.html`。

## 做了什麼

- 新增 `summaries/average.html`、`norm.html`、`subscale.html`；`record_rows/graded.html`、`average.html`、`norm.html`、`subscale.html`。平均與分量表的紀錄列 include 自己的摘要，不重寫同一段字。
- 刪除 `graded_summary.html`、`ssq_average.html`、`sadl_overall.html`、`ioi_ha_summary.html`。
- 結果類型多 `row_template`；分級的 `summary_template` 是 None。首頁改成「有摘要才包一個 `<div>` 放進去」，我的紀錄 include `row_template`，報告三處改用新片段。
- 新片段照舊檔不加檔尾換行，輸出逐字相同。

Commits：`41f88f3` 主要改動、`b75d9b7` 自審。

## 驗收對照

| 驗收 | 證據 |
|---|---|
| 首頁四種類型與改動前相同 | #385 釘住的 HTML 測試沒改斷言、全過：`test_result_types.py` 首頁生活影響問卷與 THI／平均／常模比對／分量表；另 `test_home.py` |
| 我的紀錄每一列相同 | 同上，五個問卷分頁各兩列的 HTML 釘住測試 |
| 報告與家人分享頁的摘要那一行相同 | IOI-HA 重點與摺疊標題由既有測試釘住；SSQ12 那一行自審後補釘 `<p>未計算：包含不適用題目</p>`（兩頁都驗） |
| 沒有 `place=`、`ioi_ha=`，舊檔已刪 | `test_the_snippets_take_no_place_or_ioi_ha_and_the_old_ones_are_gone`：掃描所有模板的 `{% %}` 裡沒有 `place`、include 沒有 `ioi_ha=`；四個舊檔不存在（改動前先跑過，失敗） |
| 結果物件指向新檔、分級摘要是 None | 四個結果類型測試各自斷言 `summary_template`／`row_template` 與渲染結果 |
| 查詢數沒有增加 | 我的紀錄、首頁、聽力報告與家人分享頁的查詢數測試數字沒改、全過 |
| 測試、e2e、Ruff | 見下方 |

另外的一次性比對（試驗，測試檔已刪除）：拿 #385 驗證用的同一份測試資料，跟 #385 最後版本的 60 個輸出比，HTML 空白正規化後完全相同；只差報告的產生日期（前一天跑的）與首頁 SADL 查詢 25 → 10（#407，已合併）。

## 測試與審查

- 單元測試 `--parallel 4`：1492 項全過。
- 端對端：建置前端後 `e2e.main_flow --parallel 4`：276 項全過。
- `ruff check .`、`ruff format --check .`、`makemigrations --check --dry-run`：通過。
- 自審（Standards／Spec）：要修 0 項。採納：拿掉測試裡新加的 `.strip()`（恢復逐字比對）、`record_rows/graded.html` 寫法跟其他片段一致、平均紀錄列斷言實際的配戴狀態、掃描測試照同檔既有寫法並抓 `{% if place %}`、測試改名、註解說清楚 None 的意思、補釘報告 SSQ12 那一行。
- 唯一改動的既有斷言：檢查首頁與我的紀錄 include 哪個片段的那條（檢查模板原始碼，不是畫面），配合改名必須改。

## 人工驗收

畫面應該完全不變，請用預覽網站看：

1. 首頁上次結果：生活影響問卷（儀表與分級）、SSQ12（整體平均或未計算原因）、IOI-HA（常模摘要）、SADL（整體滿意度）、THI（只有標題）。
2. 我的紀錄：每個問卷分頁的每一列。
3. 聽力報告與家人分享頁：「重點」裡 SSQ12、IOI-HA 那一行，SSQ12 區塊的摘要，IOI-HA 摺疊標題。

回覆：2026-10-27 本人在預覽網站確認三項都通過。
