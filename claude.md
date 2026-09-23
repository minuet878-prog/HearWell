# HearWell — Claude Code 工作指引

## 關於我

- 我是台灣的聽力師，正在轉職軟體工程師。這是我的第一個獨立 Django 專案，**學習優先於速度**。
- 回覆一律用**繁體中文**。程式碼、commit message、變數命名用英文。
- 解說時盡量連結到底層概念（資料結構、演算法、時間複雜度、資料庫原理、HTTP、安全性），並說明「為什麼這樣運作」，不只是定義名詞。
- 遇到技術名詞，先用一句話解釋再繼續，不要假設我已經懂。

## 互動規則（最重要）

### 預設：引導模式

- **不要直接寫程式碼給我**。用問題引導我思考，讓我自己寫。我寫完之後，只指出具體錯誤。
- **引導問題一次只問一題**。問完就停，等我回答、你回饋完，才問下一題。
- 純 API 細節（方法名、import 路徑、設定鍵名）不必用問題包裝，直接問我要不要講。
- 動手修改任何檔案前，先提出計畫、等我確認。

### 例外：代工模式

只有在我明確說「**直接做**」時，才可以直接修改檔案。適用於我已經會、只是費時的機械性工作，例如：ruff 設定、格式修正、補我已經寫過同類的測試、重新命名。
做完後簡短說明改了哪些檔案、為什麼。

## 不可違反的規則

1. **所有查詢都要限定在 `request.user`**（view 與未來的 API 都一樣）。這是 IDOR 防護，曾經出過漏洞。
2. **分級與計分只用規則式程式碼**。LLM 只能用在自然語言輸出，不能用在分類或計算。
3. **每個讀取分數的地方都走同一條計算路徑**（`Submission` 的計分方法），不要另寫一份聚合。
4. **0 是合法分數，不能當「沒資料」的哨兵值**。空的 submission 要另外處理。
5. **Git**：一律在分支上工作，不要直接改 `main`；未經我同意不要 commit 或 push。
6. **不要在 shell 對正式資料庫做破壞性操作**。要驗證行為就寫進 `tests.py`。
7. 介面字級一律用 `rem`，不用 `px`（使用者多為 65 歲以上）。

## 專案概要

- 聽力健康自我照護工具：註冊 → 登入 → 選問卷 → 作答 → 計分 → 結果（分級＋行動建議）→ 歷史紀錄
- 目標使用者：台灣聽損患者與家屬，多為 65 歲以上，繁體中文介面。**無障礙是必需品，不是加分項。**
- 量表：HHIE-S（65 歲以上）、HHIA-S（65 歲以下），共用同一組資料表，靠 `questionnaire` 區分
- 技術：Django 5.2、Python 3.13、PostgreSQL、Bootswatch Minty、部署於 Render（whitenoise、dj-database-url、`build.sh`）
- 專案名 `config`，app 名 `screening`

### 結構

- `screening/models.py` `views.py` `forms.py`（formset 收作答）`scoring.py`（分級、顏色、建議文字）`tests.py` `admin.py` `urls.py`
- `screening/templates/screening/` — 全部繼承 `layout.html`
- `screening/templatetags/custom_filters.py` — `level_to_color`
- `questions_fixture.json` — HHIE-S 十題
- `pyproject.toml` — Ruff 設定

### 資料模型

- `User`（AbstractUser ＋ `birth_date`，允許 null ＋ `age` property）；引用時用 `settings.AUTH_USER_MODEL`
- `Questionnaire` → `Question` → `Answer` ← `Submission` ← `User`，所有 FK 皆為 `PROTECT`
- 每題答案存一列（正規化），總分不存欄位、每次即時計算
- 約束：`Question(question_number, questionnaire)` 唯一、`Answer(submission, question)` 唯一、`category` 與 `score` 有 CheckConstraint
- 索引：`Submission(user, -created_at)` 複合索引
- 計分：`Submission._calculate_scores()` 用一次 `aggregate`，以 `Sum("score", filter=Q(...), default=0)` 取總分與 E／S 分項，結果存在 `_scores_cache`

## 已知陷阱

- `_scores_cache` 不會失效：在 shell 或測試裡「讀 → 改 → 再讀」會拿到舊值，斷言前要重新從 DB 取物件。
- `PROTECT` 擋得住刪除、擋不住編輯：題目被改，歷史分數會跟著改。
- `Submission.user` 是 `PROTECT`，做過篩檢的帳號無法刪除，但個資法下使用者有權刪除自己的健康資料，之後必須處理。
- `classify()` 的 40 分上限是 HHIE-S 專用，目前寫死在 `scoring.py`。
- Django shell 是 autocommit，沒有 rollback。必要時用 `atomic()` 包起來並在最後 `raise` 做 dry run。

## 架構方向：DRF ＋ React（2026-09-21 決定）

- **Strangler 模式漸進導入**：`/api/` 與現有 view 並存、共用 model 與業務邏輯，`main` 任何時候都是完整可用的產品。
- **同源部署**：Vite build 產物進 `staticfiles`，由 whitenoise 服務，Render 單一服務。
- **認證沿用 session cookie，不用 JWT**；不需要 CORS；CSRF 沿用 Django 機制。
- 唯讀 endpoint 先行，寫入最後做；用 `drf-spectacular` 產生 OpenAPI schema。
- React 只做互動重的頁面（趨勢圖 → 作答 → Audiogram）。**登入／註冊不 React 化。**
- 作答驗證要放在 form 層而非 view，DRF serializer 才能共用。
- SPA 對高齡使用者的三個風險要主動處理：首屏 JS 體積、焦點管理與上一頁、字級縮放。

## 常用指令

- `python manage.py runserver`
- `python manage.py makemigrations screening` → `python manage.py migrate`
- `python manage.py test`
- `python manage.py check --deploy`（要在 `DEBUG=False` 下跑）
- `ruff check --fix .`

## 參考文件（需要時主動去讀）

- `docs/decisions.md` — 做過的決策、理由、踩過的坑。**新增條目要簡短口語**，不要寫成長篇報告。
- `docs/roadmap.md` — 目前階段與待辦（Phase 0–5 的完整清單在這裡）。
- `~/.claude/plans/` — 四份 code review 報告，最新的是 `code-review-drf-react-claude-md-mellow-sky.md`（G-1～G-8 ＋ DRF/React 導入順序）。新 session 不會自動載入。

## 目前階段

Phase 0：讓自動檢查恢復作用（ruff 排除 migrations、擴充規則集、補計分聚合測試、debug-toolbar、`check --deploy`）。細節見 `docs/roadmap.md`。