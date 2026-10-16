# Phase 6 規格：測試依功能分資料夾

- **狀態**：已完成
- **分支**：`refactor/tests-by-feature`（從 `main` 開，PR #48 合併後）
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-16

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

後端測試目前全部擠在一個將近 5,000 行、43 個測試類別的檔案裡，很難找到某個功能的測試。
依功能拆開放進資料夾，做完之後可以一眼找到某功能的測試，也可以只跑某一個功能的測試。
**只搬家，不改任何測試的內容與行為。**

## 2. 範圍

### 要做
- 後端測試依功能分組，放進一個測試資料夾，每組一個檔案（分組見第 4 節）。
- 跑全部測試的指令維持不變（CLAUDE.md、CI 不用改指令）。
- 可以只跑某一組，例如只跑聽力圖的測試。
- CLAUDE.md「結構」段落裡提到的測試位置同步更新。

### 不做
- 不改任何測試的斷言、測試資料、類別名稱、方法名稱。
- 不合併重複的輔助函式（例如好幾個類別各有自己的 `_make_submission`），不抽共用的 base class 或 fixture。
- 不換測試框架（不改用 pytest）、不加套件。
- 不補新測試、不刪舊測試。
- 不動正式程式碼（models、views、API……）。
- 前端測試（`frontend/src/*.test.*`）不搬：前端慣例是測試檔放在被測的檔案旁邊。
- 不順手修拆檔時看到的其他問題，看到的列在回報裡。

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本 phase 特別注意：
  - 測試是之後所有修改的安全網，這次搬家本身沒有測試保護，所以用「搬家前後的測試清單逐條比對」來證明沒漏、沒重複。

## 4. 行為描述

### 4.1 分組（依功能）

| 組別 | 內容 | 測試類別 |
|---|---|---|
| 計分與分級 | 門檻、分級、總分與分項計算、計分路徑 | ClassifyTests、ClassifyViewTests、ScoringAggregateTest、HistoryScorePathTests、SubscaleNoteTests |
| 網頁作答 | 送出、驗證、助聽器題、連按兩次、錯誤後留在網頁表單、React 接手 | ScreeningViewAcceptValueTests、EmptyQuestionnaireSubmissionTests、DuplicateAnswerSubmissionTests、HearingAidTests、TamperedAnswerTests、ReactAnswerPageTests、AnswerFlashTests、WebDoubleSubmitTests、WebFormErrorsStayTests |
| 帳號與權限 | 登入、註冊、`next`、出生年、未登入擋下、看別人的結果 | LoginRequiredTests、SubmissionResultAccessTests、LoginNextTests、RegisterFormTests、BirthYearMigrationTests |
| 資料完整性與 admin | 唯一限制、作答過的題目鎖定 | ModelsUniqueConstraintTests、AdminLockAnsweredTests |
| API | `/api/` 基礎、歷史與單筆、問卷題目、作答送出 | ApiFoundationTests、ApiSubmissionTests、ApiQuestionnaireDetailTests、ApiSubmitTests |
| 我的紀錄 | 分頁籤、趨勢圖頁 | HistoryTabsTests、TrendChartPageTests |
| IOI-HA | 規則與 fixture | IoiHaTests、IoiHaFixtureTests |
| 聽力圖 | 判讀規則、比較規則、API、新增／修改／比較頁 | AudiogramRuleTests、AudiogramCompareRuleTests、AudiogramApiTests、AudiogramEditApiTests、AudiogramPageTests、AudiogramEditPageTests、AudiogramComparePageTests |
| 畫面與內容 | 文案、無障礙、共用版型、逐頁動線、PWA | CopyTests、AccessibilityTests、RedesignLayoutTests、PageFlowTests、PwaTests |
| 設定與部署 | debug-toolbar、`ALLOWED_HOSTS` | DevChecksTests、AllowedHostsTests |

合計 43 個類別，每個只出現在一組。

## 5. 驗收條件

- [x] 假設搬家前跑全部後端測試得到 N 個測試、全部通過，當搬家後用同一個指令再跑，則一樣是 N 個、全部通過。
- [x] 假設搬家前後各列出所有測試的完整名稱（類別.方法），當比對兩份清單（不看所在檔案），則完全相同：沒有少、沒有多、沒有重複。
- [x] 假設搬家完成，當只跑「聽力圖」這一組，則只跑到聽力圖的 7 個類別，全部通過；其他組各自單獨跑也都通過。
- [x] 假設搬家完成，當比對每個測試類別搬家前後的內容，則除了檔案開頭的 import、「找專案裡其他檔案的路徑」、跨檔借用其他類別時前面加上檔名（例如 `test_answering.ReactAnswerPageTests.ANSWER_JS`；直接匯入類別的話，單獨跑某一組會混進別組的測試）之外，沒有任何差異。
- [x] 假設搬家完成，當跑 `ruff check .`，則沒有錯誤（包含沒用到的 import）。
- [ ] 假設 PR 開出去，當 CI 跑完，則 `backend`、`frontend` 兩個檢查都通過。（待 PR 開出去後確認）

## 6. 待決問題

- [x] ~~**1. 資料夾結構**~~ → A：一個測試資料夾，每組一個檔案（2026-10-16）
- [x] ~~**2. 第 4 節的分組**~~ → 照建議（2026-10-16）
- [x] ~~**3. 前端測試要不要一起搬？**~~ → 不搬（2026-10-16）
- [x] ~~**4. 什麼時候開工？**~~ → A：#48 已合併，從 `main` 開新分支（2026-10-16）
- [x] ~~**5. 跨檔借用其他類別的常數（實作時發現）**~~ → A：匯入整個檔案，參照前加檔名；驗收 4 已放寬（2026-10-16）

---

## 完成後回報（由 AI 填寫）

- **改了哪些檔案、為什麼**：
  - `screening/tests.py` 刪除，拆成 `screening/tests/` 底下 10 個 `test_*.py`（照第 4 節分組）＋空的 `__init__.py`。用暫存腳本以 `ast` 切出每個類別原文，再用 `ruff check --fix` 刪掉各檔沒用到的 import。
  - 7 處 `Path(__file__).resolve().parent…` 多一層 `.parent`（檔案往下移一層）。
  - 6 行跨檔借用改成 `test_answering.ReactAnswerPageTests…` 這種「檔名.類別」寫法（待決 5；當初說「直接匯入會讓總數變多」是錯的，跑全部時 Django 會去重，真正的問題是單獨跑一組會混進別組，見下方新概念）；其中 2 行因此超過 100 字，換行。
  - `claude.md`：規則 12 與「結構」段落改成 `screening/tests/`，補只跑一組的指令與跨檔借用的陷阱。
- **驗收條件對應的測試**（這次沒有新測試，用比對與實際執行驗證）：
  - 1：搬家前後同一個指令，都是 356 個、全部通過。
  - 2：搬家前後 `-v 2` 輸出的「類別.方法」清單 `diff` 相同，沒有重複。
  - 3：10 組各自單獨跑都通過（18／46／29／7／48／28／27／87／52／14，合計 356）；聽力圖組 87 個＝搬家前 `Audiogram*` 的數量。
  - 4：比對腳本逐一比對 48 個定義（43 類別＋5 個輔助函式），38 個一字不差，10 個只差允許的部分（還原後相同）。
  - 5：`ruff check .` 通過（另外 `ruff format --check screening/tests` 也通過）。
  - 6：待 PR 的 CI。
- **規格以外的決定**：
  - `PwaTests.test_no_service_worker_registration` 原本用 `p.name != "tests.py"` 排除自己，搬家後排除不到而失敗；改成 `p != Path(__file__).resolve()`（本人同意）。審查指出這比原本嚴格：其他 9 個測試檔現在也會被掃描。決定維持（本人同意），替代寫法是 `"tests" not in p.parts`。
- **這次用到的新概念**（各用一句話解釋）：
  - 測試探索（test discovery）：`unittest` 在套件裡找檔名符合 `test*.py` 的檔案，資料夾要有 `__init__.py`。
  - 匯入的測試類別會被當成這個檔案的測試：探索時檔案裡每個 `TestCase` 子類別都算，不管在哪裡定義；跑全部時 Django 會去重，但單獨跑一組會混進別組的測試（試驗：畫面組 52 → 59）。
  - `Path(__file__)`：用「這個檔案的位置」找其他檔案；檔案搬家，往上幾層也要跟著改。
  - 純結構重構的驗證：搬家沒有測試保護，用「搬家前後的測試清單與原始碼比對」證明沒漏、沒重複、沒改。
- **面試可能追問的 2–3 題**：Q87–Q89（見 `docs/interview.md`「測試」主題）。
- **建議寫進 decisions/ 的內容**：見對話（放「開發工具與流程」`tooling.md`）。
