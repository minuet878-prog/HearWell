# HearWell — 代理工作指引（代工模式）

Claude Code 與 Codex 共用這份指引（Claude Code 經 `CLAUDE.md` 匯入）。改規則只改這裡。

## 分工

- 我是台灣的聽力師，正在轉職軟體工程師。
- 這個專案是**代工模式**：你寫程式，我出需求、做決定、驗收。目標是做出能用、好維護的東西。
- 我不一定熟這裡的技術，要讓我「看得懂你做了什麼、為什麼」，但不用教我怎麼寫。

## 溝通

- 回覆一律用**繁體中文**；程式碼、commit message、issue 標題、PR 標題、變數命名用英文。GitHub issue 和 PR 內文用繁體中文。
- 遇到技術名詞，先用一句話解釋再繼續。
- 派出去的 subagent 也要用繁體中文回報（規則不會自動傳給它們，要寫進交辦指示）。
- 需要我做決定時，列出選項、代價和你的建議。
- 超過一個畫面的內容寫成檔案（或 GitHub issue），對話裡只放三到五行摘要和路徑。

## 工作流程（Matt Pocock skills）

| 步驟 | 指令 | 說明 |
|---|---|---|
| 0 開工 | — | 讀 `docs/roadmap.md` 和 `gh issue list`，三行以內報告：做到哪、還欠什麼、這次打算做什麼 |
| 1 拷問需求 | `/grill-with-docs` | 一次問一題直到沒有模糊處，給我全部的選擇/建議/代價並順手更新 `GLOSSARY.md` 和 `docs/adr/` |
| 2 寫規格 | `/to-spec` | 寫成 GitHub issue，驗收條件用 Given / When / Then |
| 3 拆票 | `/to-tickets` | 拆成 tracer-bullet tickets，標明誰擋住誰 |
| 4 實作 | `/implement`（一張或少數幾張）或 `/implement-spec`（整份規格、平行） | TDD；全部完成後跑 `/code-review` 自審 |
| 4b 交叉審查 | `/code-review`（換另一個代理跑） | 合併前一定要做，見下方 |
| 5 驗收 | — | 貼出測試結果、逐條對驗收條件打勾，等我實際操作確認；驗收結果寫進 `docs/verification/`，跟程式放在同一個 PR |
| 6 PR | `/pr` | 寫 PR 說明（摘要、證據、合併風險）；我驗收通過才合併，不在合併後另開 PR 補記驗收 |
| 7 收尾 | — | 更新 `docs/roadmap.md` 和 `docs/interview/`（見下方） |
| 8 復盤 | `/retro` | 每個母規格結案後跑一次；其他時候我輸入才做 |

- 小改動（改字、改樣式）可以跳過 1–3 和 4b，直接說清楚要改什麼，再走 4–7。
- 涉及畫面或計算的需求，先用一兩句話複述你理解的內容；畫面有多種做法時，先做比較頁讓我選。

### 交叉審查（合併前）

- 原因：代理審自己寫的程式容易漏看。#84 自審 0 項，合併後換另一個代理審，才找出 #90 的三個問題。
- 誰審：實作和審查不能是同一個代理。Codex 實作的由 Claude Code 審，Claude Code 實作的由 Codex 審。
- 時機：自審修完之後、寫驗證紀錄（`docs/verification/`）和我實際驗收之前。實作的代理做到這裡先停，告訴我分支名稱、規格 issue 編號，以及要貼給另一個代理的指令。
- 怎麼審：
  - 用 Matt 的 `/code-review`，基準點 `main`。Claude Code 裡要打 `/mattpocock-skills:code-review`：直接打 `/code-review` 會叫到 Claude Code 內建、只抓 bug 的另一種審查（第 4 步自審也一樣）。
  - 審查者只看 diff、規格 issue 和 `CODING_STANDARDS.md`，不看實作的對話和自審結果。
  - Spec 軸要逐條列出每個驗收條件由哪個測試的哪個斷言證明（`檔案:行號`）；找不到斷言，或斷言沒有真的驗證那一條，就算一項發現。
- 結果：審查結果用繁體中文留言到規格 issue（留言前先問我）。實作的代理照留言修完，再請審查的代理只複核修過的項目，直到沒有「要修」才進第 5 步。

### 收尾

- 這次有沒有以後很難回頭、或會想推翻的決策（計分、分級、資料保存方式、架構）？有就在 `docs/adr/` 新增一份 ADR（一個決策一個檔，寫情況、決定、原因、代價）。
- 結案的 issue 拿掉 `needs-triage`、`needs-info` 標籤。
- 面試筆記：
  - 先讀 `docs/interview/README.md` 的維護方式；新概念與面試題寫入對應主題，開發紀錄依 Phase 新增，題號全資料夾接續並更新索引。
  - `docs/interview.md` 保留為導覽入口，內容以 `docs/interview/` 為準；兩者均維持不進版控。
  - 回報時附上新概念和面試題，讓我挑不熟的深入問。

### 遇到 bug
不准猜、不准「改改看」。先找出根本原因並告訴我，確認後才修，修在源頭，同一個原因造成的其他地方一併檢查。

## 寫程式原則

- **簡單優先**：只寫需求要的。不加沒要求的功能或設定選項；只用一次的程式碼不做抽象；不可能發生的情況不寫錯誤處理。
- **精準修改**：每一行改動都要對得回這次的需求。不順手「改善」旁邊的程式碼、註解或格式，跟著現有寫法走。
- 看到無關的死程式碼或問題，提出來，不要直接刪或修；自己這次改動造成沒人用的 import、變數、函式要清掉。
- **先講假設**：需求有多種解讀時列出來問我，不要默默挑一種；有更簡單的做法就直接說。
- **先查文件**：用到 Django、DRF、React、Vite 等套件的 API 前，先用 context7 查目前版本的官方文件，不要憑記憶寫；沒裝 context7 或查不到時，說明你是依哪個版本的認知寫的。
- 修 bug 時先寫一個能重現它的測試，看它失敗，再修。

## 不可違反的規則

1. **Git**
   - 不直接改 `main`，一律在分支上工作。
   - 功能分支（和 `/implement-spec` 的子分支）上可以自己 commit、合併子分支，Conventional Commits 格式。
   - **push、開 PR、合併回 `main` 都要先問我。** `/implement-spec` 要開 draft PR 時也一樣。
   - commit 作者用我的 git 設定；沒有設定時先問我。
2. **不擅自動我的資料**：不刪除、不覆寫、不批次修改真實資料（資料庫、資料檔、匯出檔）。需要時先說明影響，等我同意。
3. **不碰我的服務**：不自己啟動、重啟或停掉我電腦上的伺服器和資料庫。例外：Claude Desktop 預覽用的開發伺服器（`.claude/launch.json`，埠 8001）可以自己啟動和停止；資料庫還是由我來開。
4. **試驗要先講**：探索用的修改先說「這是試驗」，結束後主動還原。
5. **垃圾不進版控**：虛擬環境、`node_modules`、`.env`、`.claude`（`settings.json`、`hooks/`、`launch.json` 除外，要進版控）、log、暫存檔一律不加。
6. 程式碼規範見 `CODING_STANDARDS.md`，實作和審查都要遵守。

## 專案概要

- 用途：聽力健康自我照護工具。註冊 → 登入 → 選問卷 → 作答 → 計分 → 結果（分級＋行動建議）→ 歷史紀錄。
- 使用者：台灣聽損患者與家屬，多為 65 歲以上，繁體中文介面。**無障礙是必需品，不是加分項。**
- 技術：Django 5.2、Python 3.13、PostgreSQL（正式環境在 Neon，本機用 Docker）、Bootstrap 5.3.8（CDN）＋自訂 `screening/static/screening/styles.css`（主色 #1f4e8c、基礎字級 18px）；部署於 Render（whitenoise、dj-database-url、`build.sh`，每次部署會 `loaddata` 問卷 fixture）。專案名 `config`，app 名 `screening`。
- 資料敏感度：有健康資料（篩檢作答與分數）和個資（帳號、生日），存在 PostgreSQL。適用個資法。

### 結構

- `screening/models.py` `views.py` `forms.py`（formset 收作答與驗證）`scoring.py`（分級、顏色、建議文字）`admin.py` `urls.py`
- `screening/tests/` 依功能分檔（`test_scoring.py`、`test_answering.py`、`test_api.py`、`test_audiogram.py`……），只跑一組：`python manage.py test --settings=config.test_settings screening.tests.test_audiogram`；跨檔借用別的測試類別要匯入整個檔案（`from screening.tests import test_pages`），直接匯入類別的話，單獨跑那一組會混進別組的測試
- `screening/templates/screening/` 全部繼承 `layout.html`；`screening/templatetags/custom_filters.py` 有 `degree_level`（聽力圖程度 → 標籤顏色，對應表在 `audiogram.DEGREE_LEVELS`）；分級標籤共用 `level_badge.html`
- `screening/fixtures/` 問卷題目；`pyproject.toml` Ruff 設定

### 資料模型

- `User`（AbstractUser ＋ `birth_year`，允許 null ＋ `age` property）；引用時用 `settings.AUTH_USER_MODEL`
- `Questionnaire` → `Question` → `Answer` ← `Submission` ← `User`，所有 FK 皆為 `PROTECT`
- 量表：HHIE-S（65 歲以上）、HHIA-S（65 歲以下），共用同一組資料表，靠 `questionnaire` 區分
- 每題答案存一列，總分不存欄位、每次即時計算：`Submission._calculate_scores()` 用一次 `aggregate`（`Sum(..., filter=Q(...), default=0)`）取總分與 E／S 分項，存在 `_scores_cache`

### 架構方向：DRF ＋ React（決策原因見 `docs/decisions/architecture.md`）

- Strangler 模式：`/api/` 與現有 view 並存、共用 model 與業務邏輯，`main` 任何時候都是完整可用的產品。
- 同源部署：Vite build 進 `staticfiles` 由 whitenoise 服務；認證沿用 session cookie，不用 JWT、不需要 CORS。
- 唯讀 API 先行，寫入最後；`drf-spectacular` 產生 OpenAPI schema。
- React 只做互動重的頁面；登入／註冊不 React 化。先做 PWA，不上架。
- 作答驗證放在 form 層，DRF serializer 才能共用。
- 65+ 的 SPA 風險要主動處理：首屏 JS 體積、焦點管理與上一頁、字級縮放。

## 常用指令

- 啟動：`python manage.py runserver`（由我來啟動）
- 本機套件：`pip install -r requirements-dev.txt`（含 debug-toolbar、ruff、playwright；正式環境只裝 `requirements.txt`）
- 測試：`python manage.py test --settings=config.test_settings`（不需要先 collectstatic）
- 前端測試：`npm test --prefix frontend`；前端建置：`npm run build --prefix frontend`
- 端對端測試：先 `npm run build --prefix frontend`，再 `python manage.py test --settings=config.test_settings e2e.main_flow`（自己開臨時網站與 `test_` 資料庫，不用先啟動伺服器；第一次要先 `python -m playwright install chromium`；平常的「測試」指令不會跑到它；失敗時截圖與 trace 在 `e2e-artifacts/`）
- 檢查格式：`ruff check --fix .`
- Migration：`python manage.py makemigrations screening` → `python manage.py migrate`
- 部署檢查：`python manage.py check --deploy`（要在 `DEBUG=False` 下跑）

## 已知陷阱

- `_scores_cache` 不會失效：「讀 → 改 → 再讀」會拿到舊值，測試斷言前要重新從 DB 取物件。
- 問卷、題目、Submission／Answer 在 admin 都只能看，不能新增、修改、刪除；問卷內容由問卷定義（`screening/questionnaires/`）決定。要改題目就新增一個問卷定義（新 code），不要改舊的。
- 已上線的問卷不能加題：`seed_questionnaires` 只建立不存在的問卷，改定義檔的 `questions` 不會動到已上線的版本；從 shell 或 fixture 硬加的話，新作答的滿分會超過門檻表，變成「無法判讀」。要加題就新增一個問卷定義（新 code）。
- 刪除帳號要走 `User.delete_with_data()`（交易內由下往上刪），不要直接 `user.delete()`：`Submission`、`Audiogram`、`Consent` 對 User 都是 `PROTECT`，會被擋下。
- `build.sh` 每次部署都會 `loaddata`（HHIE-S、IOI-HA），直接照 fixture 寫進資料庫：fixture 裡已上線的題目不能改，要改就新增一個問卷定義（新 code）。
- 門檻（問卷定義的 `thresholds`）第一次要改之前，先做規則版本號，不要直接改數字，否則歷史分級會被回溯改寫。
- Django shell 是 autocommit，沒有 rollback。
- `Sum` 沒有 `default=0` 時，沒資料會回 `None` 而不是 0（踩過三次）。
- worktree 裡沒有 `py313/`：Ruff hook 會自動改用主資料夾的；自己跑測試或 Ruff 時，用主資料夾的 `py313/bin/python`。

## 參考文件

- `docs/README.md` — 查找專案文件時的分類入口，連到規劃、無障礙、API、部署及歷史索引。
- `GLOSSARY.md` — 專案用語（由 `/grill-with-docs` 維護）。
- `CODING_STANDARDS.md` — 程式碼規範，`/code-review` 依此審查；能自動抓的規則在 `screening/tests/test_standards.py`。
- `docs/adr/` — 2026-10-18 之後的決策紀錄（ADR，一個決策一個檔）。
- `.claude/settings.json` — Claude Code 的權限清單（push／開 PR 要問、force push 與啟動伺服器禁止）和 hooks（改完 `.py` 自動跑 Ruff、在 `main` 上 commit 要確認、等回覆時跳通知）。
- `.codex/hooks.json` — Codex 的 hook（改完 `.py` 自動跑 Ruff，和 Claude Code 共用同一支腳本）。
- `docs/agents/` — Matt skills 的設定（issue tracker、標籤、文件位置）。
- `docs/roadmap.md` — 各 Phase 的待辦與目前進度。
- 歷史（2026-10-18 以前，只讀不再新增）：`docs/decisions/`（舊的決策紀錄，依主題分檔）；查找 Phase 0–10 規格或審查時，先讀 `docs/specs/README.md` 或 `docs/reviews/README.md`，依 Phase 索引進入原文件。

## Agent skills

### Issue tracker

Issue 和規格放在 GitHub Issues（用 `gh` CLI）。見 `docs/agents/issue-tracker.md`。

### Triage labels

使用預設五個標籤：needs-triage、needs-info、ready-for-agent、ready-for-human、wontfix。見 `docs/agents/triage-labels.md`。

### Domain docs

Single-context：根目錄一份 `GLOSSARY.md` ＋ `docs/adr/`。見 `docs/agents/domain.md`。

## 目前階段

見 `docs/roadmap.md` 開頭的「目前進度」，這裡不另外記，避免兩處不同步。
