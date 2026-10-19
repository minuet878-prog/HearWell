# Phase 5 規格：重寫 README

- **狀態**：已完成
- **分支**：`docs/readme-rewrite`
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-15

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

README 和現在的程式碼一致：面試官看得懂這個產品解決什麼問題、有哪些設計考量；開發者照著做能在本機跑起來。

## 2. 範圍

### 要做
- 開頭：一句話定位、問題背景（保留原數據，標「出處待補」）、聽力師開發、線上展示連結
- 功能清單（照現有功能）
- 設計重點：無障礙、規則式計分與單一計算路徑、IDOR 防護、Strangler 模式、冪等寫入；每點一兩句並連到 `docs/decisions/`
- 技術棧、更新後的 ER 圖、API endpoint 列表
- 本機開發（含前端）、常用指令、部署、文件索引

### 不做
- 不改 README 以外的程式碼或設定
- 不改 CLAUDE.md、`docs/decisions/`
- 不加截圖、徽章（badge）、授權條款段落
- 不替數據找出處（由本人補）
- 不寫還沒做的功能（聽力圖、家屬版等），roadmap 只放連結

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本任務特別注意：
  - 不寫入任何真實個資、密碼、連線字串（`.env.example` 的範例值除外）
  - 每項事實都要能在程式碼找到對應，不照舊 README 抄

## 4. 行為描述

本任務沒有程式行為，只有文件內容。章節順序見第 2 節「要做」。

## 5. 驗收條件

- [x] 假設照 README「本機開發」從頭做，當逐條對照 `.env.example`、`requirements*.txt`、`frontend/package.json`、`.node-version`，則每條指令與檔名都存在且正確。
- [x] 假設讀「常用指令」與「部署」，當對照 CLAUDE.md 常用指令與 `build.sh`，則測試指令含 `--settings=config.test_settings`，部署步驟順序與 `build.sh` 一致。
- [x] 假設看 ER 圖，當對照 `screening/models.py`，則列出的欄位與關係都存在，沒有已刪除的欄位（例如 `birth_date`）。
- [x] 假設看功能與問卷清單，當對照 `screening/fixtures/questions_fixture.json` 與 `scoring.py`，則只列出現有的問卷（HHIE-S、IOI-HA）與已完成的功能。
- [x] 假設看 API 段落，當對照 `screening/api/urls.py`，則 endpoint 一一對應。
- [x] 假設搜尋 README，當找密碼、金鑰、真實姓名，則除了 `.env.example` 的本機範例值外都沒有。
- [x] 假設在 GitHub 預覽 README，則 mermaid ER 圖能正常顯示。（本人在 PR #33 確認，註腳也正常）

### 5.1 追加：首頁數據卡片（2026-10-15，本人確認）

首頁「7–10 年」卡片和 README 一樣沒有文獻支持「平均 7–10 年」，同一個 PR 一起修。舊規格 `phase4_ui_flow.md` 保留原樣當紀錄。
- 大字改「可達 10 年」，說明改「從察覺聽力問題到尋求協助，往往拖延多年。及早了解，才能及早處理。」
- 首頁不列出處（出處在 README）。

- [x] 8. 假設未登入，當開啟首頁，則卡片依序顯示「可達 10 年」與新說明，不再出現「7–10 年」與「平均要拖這麼久」；其他首頁內容與順序不變。

## 6. 待決問題

- [x] ~~Q1：README 問卷清單要不要寫 HHIA-S？~~ → 照程式碼，只寫 HHIE-S、IOI-HA；CLAUDE.md 這次不動。
- [x] ~~Q2：「設計重點」段的語言？~~ → 中文為主，技術名詞附英文（例如「冪等（idempotency）」）。

---

## 完成後回報（由 AI 填寫）

- **改了哪些檔案、為什麼**：`README.md` 整份重寫，內容對齊目前程式碼（功能、技術、ER 圖、API、本機前端建置、`build.sh` 部署步驟）。
- **驗收條件對應的測試**：文件任務沒有自動測試；驗收 1–6 以指令逐條比對程式碼與設定檔（fixture 題數、`settings.py`、`vite.config.js`、`build.sh`、`api/urls.py`、連結檔案是否存在、搜尋密碼字串）；驗收 7 本人在 GitHub 確認；驗收 8 對應 `PageFlowTests.test_home_order_for_anonymous`／`test_home_order_for_logged_in_without_hint`（`HOME_ORDER` 改新文字，並斷言不再出現「7–10 年」）。
- **規格以外的決定**（如果有，說明原因）：拿掉舊 README 的 `ruff format .`（目前有 4 個檔案未照此格式，照跑會改到不相干的檔案）；IDOR 連結指向 `docs/specs/phase-03/phase3.md`，因為 `decisions/security.md` 沒有寫到 IDOR。依本人要求改寫開頭：數據依文獻修正（三成→四成、平均 7–10 年→可達 10 年）、加「參考資料」段（GitHub 註腳語法 `[^n]`）、產品說明改寫成兩種使用者（未就醫、已戴助聽器）。原規格「不替數據找出處」由本人改為要找。
- **這次用到的新概念**（各用一句話解釋）：
- **面試可能追問的 2–3 題**（附答案要點）：
- **建議寫進 decisions/ 的內容**（素材即可，條目由本人撰寫；註明放哪個主題檔）：
