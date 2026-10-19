# 審查報告：phase6_tests_by_feature（測試依功能分資料夾）

- 規格：`docs/specs/phase-06/phase6_tests_by_feature.md`
- 審查者：`reviewer` subagent（唯讀），2026-10-16
- 基準：`main`；分支 `refactor/tests-by-feature` 已 stage 的變更（`git diff --cached main`）

## 審查結論（reviewer 原文摘要）

只搬家、沒有改測試行為；測試清單、類別內容、分組都對得上規格。沒有「要修」的項目。

### 驗證方式
- 用 AST 抓每個類別原始碼比對：舊檔 43 個類別、新資料夾 43 個，沒有少、沒有多、沒有同名類別出現在兩個檔案。
- 有差異的 11 個類別，差異都是：`Path(__file__)` 多一層 `.parent`、跨檔借用加檔名，以及下面第 1 項。
- `_point`、`_air`、`_bone`、`_four`、`_masked` 只在 `test_audiogram.py`，內容相同。
- 舊檔靜態列出的 356 個「類別.方法」與新結構實際執行（`-v 2`）比對：IDENTICAL，沒有重複。
- 每個檔案的類別與規格 4.1 分組表逐組吻合。

### 各檢查項目
1. bug：未發現問題。跨檔借用匯入整個模組，實測不會重複收集。
2. 多寫：沒有多寫功能，只有下面第 1 項的邏輯調整。
3. 驗收條件：1–5 已確認；6（CI）要開 PR 後確認，CI 指令不用改。
4. 「不做」清單：未發現問題（斷言、資料、類別與方法名、測試數、正式程式碼、前端測試都沒動）。
5. 不可違反的規則：未發現問題；IDOR 404 測試原封不動。

### 測試結果
- 後端 356 通過、0 失敗；10 組各自單獨跑全部 OK（18／46／29／7／48／28／27／87／52／14）
- 前端 11 檔、139 通過；`ruff check .` 通過

## 發現與查證

### 1. `PwaTests.test_no_service_worker_registration` 的排除條件不只是改路徑

- **位置**：`screening/tests/test_pages.py:810-814`
- **reviewer 說**：舊條件 `p.name != "tests.py"` 排除檔名叫 `tests.py` 的檔案；新條件 `p != Path(__file__).resolve()` 只排除 `test_pages.py` 自己，其他 9 個測試檔現在也會被掃描。超出驗收 4 明文允許的範圍，屬於邊界情況。
- **查證**：屬實。`main` 上 `screening/` 底下只有一個 `tests.py`，所以舊條件實際上就是「排除這個測試所在的檔案」。現在只有 `test_pages.py` 含有 `serviceWorker`（grep 確認），其他測試檔被掃描也照樣通過。
- **分類**：**不改**。舊條件在新結構下已經排除不到任何檔案，非改不可；新寫法和原本的註解「This file names "serviceWorker" itself」意思一致，而且只會更嚴格。寫進規格「完成後回報」的「規格以外的決定」。
  - 替代寫法（本人決定）：`"tests" not in p.parts`，排除整個測試資料夾，維持「只掃描正式程式碼」的範圍。

### 2. 決策檔還寫著舊的 `tests.py`

- **位置**：`docs/decisions/data-integrity.md:44`、`:115`
- **查證**：屬實，兩行都寫「寫進 `tests.py`」。
- **分類**：**不改**（`docs/decisions/` 由本人撰寫）。收尾時列為素材，由本人決定要不要改。
  - 舊規格與 `docs/reviews/` 裡的 `screening/tests.py` 是當時的歷史紀錄，不用改。
