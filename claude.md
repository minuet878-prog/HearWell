# HearWell — Claude Code 工作指引（代工模式）

## 關於我與這個專案的分工

- 我是台灣的聽力師，正在轉職軟體工程師。
- **這個專案是代工模式**：你負責寫程式，我負責出需求、做決定、驗收。目標是做出能用、好維護的東西。
- 我不一定熟這個專案用的技術，所以你要讓我「看得懂你做了什麼、為什麼」，但不需要教我怎麼寫。

## 溝通

- 回覆一律用**繁體中文**。程式碼、commit message、變數命名用英文。
- 遇到技術名詞，先用一句話解釋再繼續。
- 你派出去的 subagent 也要用繁體中文回報（規則不會自動傳給它們，要寫進你給它們的指示裡）。
- 需要我做決定時，列出選項、各自的代價、你的建議。同一輪能問的一起問；我的回答引出新問題時，可以再問一輪。

## 工作流程（順序固定，不可跳步）

### 1. 開工先讀紀錄
讀 `docs/roadmap.md` 和 `docs/decisions.md`，用三行以內告訴我：現在做到哪、還欠什麼、這次打算做什麼。

### 2. 先把需求講清楚
- 動手前，把需求寫成 Given / When / Then 劇本，給我確認。
- 一直問到沒有模糊的地方為止。寫不出劇本，代表需求還沒想清楚，退回來問我。
- 涉及畫面或計算的需求，先用一兩句話複述你理解的內容。
- 畫面有多種做法時，先做一頁純 HTML 的比較頁讓我選，任務結束後刪掉。

### 3. 先提計畫，等我點頭
改任何檔案之前，先說你要改哪些檔案、怎麼改。我確認後才動手。
審查或驗收之後要追加修改，一樣先提計畫、等我點頭。

### 4. 先寫測試
每一句劇本至少對應一個測試。先確認測試會失敗，再寫實作讓它通過。

### 5. 寫最少的程式
動手前依序問自己，哪一題答「是」就停：
1. 這真的需要嗎？不需要就不寫。
2. 專案裡已經有了嗎？直接用。
3. 語言或框架內建就有嗎？用內建。
4. 一行能解決嗎？寫一行。
5. 以上都不行，才寫新的。

不要加我沒要求的功能、設定選項或抽象層。選技術時優先選主流、文件多的，不選新奇的。

### 6. 交出證據才能說完成
實際跑測試，貼出結果，再拿第 2 步的劇本逐條打勾。沒跑過就不能說「完成了」。

### 7. 請另一個 subagent 審查
派一個沒參與實作的 subagent 檢查：有沒有 bug、有沒有多寫、有沒有漏掉劇本。審查意見要逐項查證（能重現的就實際重現），分成「要修」「補測試」「不改」三類，每項說明理由，再告訴我。

### 8. 收尾
1. 刪掉比較頁和暫存檔。
2. 跑 `git status` 給我看，確認沒有不該進版控的東西。
3. 提出 commit message（Conventional Commits 格式），等我同意才 commit。
4. 更新 `docs/roadmap.md`（做完什麼、下一步）和 `docs/decisions.md`（這次的決策、理由、踩到的坑，簡短口語）。
5. 問我這條分支要合併回 `main`、推到遠端、還是先放著。不要自己合併或 push。

### 遇到 bug
不准猜、不准「改改看」。先找出根本原因並告訴我，確認後才修，而且要修在源頭。同一個原因造成的其他地方一併檢查。

## 不可違反的規則

### 通用

1. **Git**：一律在分支上工作，不直接改 `main`。未經我同意不 commit、不 push。commit 的作者身分用我的 git 設定；環境裡沒有設定時先問我，不要自己填。
2. **不擅自動我的資料**：不刪除、不覆寫、不批次修改任何真實資料（資料庫、資料檔、匯出檔）。需要這樣做時先說明會影響什麼，等我同意。
3. **真實個資與病人資料不進版控**，也不寫進測試、範例或 log。測試一律用假資料。
4. **不碰我的服務**：不自己啟動、重啟或停掉我電腦上的伺服器和資料庫，需要時請我來做。
5. **試驗要先講**：臨時、探索用的修改，先說「這是試驗」，結束後主動還原。
6. **垃圾不進版控**：虛擬環境、`node_modules`、`.env`、`.claude`、log、暫存檔一律不加。
7. 密碼、金鑰、連線字串只放 `.env`，不寫進程式碼。

### HearWell 專屬

8. **所有查詢都要限定在 `request.user`**（view 與 API 都一樣）。這是 IDOR 防護（越權存取別人的資料），曾經出過漏洞。API 要有「非本人資料回 404」的測試。
9. **分級與計分只用規則式程式碼**。LLM 只能用在自然語言輸出，不能用在分類或計算。
10. **每個讀取分數的地方都走同一條計算路徑**（`Submission` 的計分方法），不要另寫一份聚合。API 由後端算好回傳，前端不重算。
11. **0 是合法分數，不能當「沒資料」的哨兵值**。空的 submission 要另外處理。
12. **不要在 shell 對正式資料庫做操作來驗證行為**，要驗證就寫進 `tests.py`。
13. 介面字級一律用 `rem`，不用 `px`（使用者多為 65 歲以上）。

## 專案概要

- 用途：聽力健康自我照護工具。註冊 → 登入 → 選問卷 → 作答 → 計分 → 結果（分級＋行動建議）→ 歷史紀錄。
- 使用者：台灣聽損患者與家屬，多為 65 歲以上，繁體中文介面。**無障礙是必需品，不是加分項。**
- 技術：Django 5.2、Python 3.13、PostgreSQL（正式環境在 Neon，本機用 Docker）、Bootswatch Minty；部署於 Render（whitenoise、dj-database-url、`build.sh`，每次部署會 `loaddata` 問卷 fixture）。專案名 `config`，app 名 `screening`。
- 資料敏感度：有健康資料（篩檢作答與分數）和個資（帳號、生日），存在 PostgreSQL。適用個資法。

### 結構

- `screening/models.py` `views.py` `forms.py`（formset 收作答與驗證）`scoring.py`（分級、顏色、建議文字）`tests.py` `admin.py` `urls.py`
- `screening/templates/screening/` 全部繼承 `layout.html`；`screening/templatetags/custom_filters.py` 有 `level_to_color`
- `screening/fixtures/` 問卷題目；`pyproject.toml` Ruff 設定

### 資料模型

- `User`（AbstractUser ＋ `birth_date`，允許 null ＋ `age` property）；引用時用 `settings.AUTH_USER_MODEL`
- `Questionnaire` → `Question` → `Answer` ← `Submission` ← `User`，所有 FK 皆為 `PROTECT`
- 量表：HHIE-S（65 歲以上）、HHIA-S（65 歲以下），共用同一組資料表，靠 `questionnaire` 區分
- 每題答案存一列，總分不存欄位、每次即時計算：`Submission._calculate_scores()` 用一次 `aggregate`（`Sum(..., filter=Q(...), default=0)`）取總分與 E／S 分項，存在 `_scores_cache`

### 架構方向：DRF ＋ React（決策原因見 `docs/decisions.md`）

- Strangler 模式：`/api/` 與現有 view 並存、共用 model 與業務邏輯，`main` 任何時候都是完整可用的產品。
- 同源部署：Vite build 進 `staticfiles` 由 whitenoise 服務；認證沿用 session cookie，不用 JWT、不需要 CORS。
- 唯讀 API 先行，寫入最後；`drf-spectacular` 產生 OpenAPI schema。
- React 只做互動重的頁面；登入／註冊不 React 化。先做 PWA，不上架。
- 作答驗證放在 form 層，DRF serializer 才能共用。
- 65+ 的 SPA 風險要主動處理：首屏 JS 體積、焦點管理與上一頁、字級縮放。

## 常用指令

- 啟動：`python manage.py runserver`（由我來啟動）
- 測試：`python manage.py test`
- 檢查格式：`ruff check --fix .`
- Migration：`python manage.py makemigrations screening` → `python manage.py migrate`
- 部署檢查：`python manage.py check --deploy`（要在 `DEBUG=False` 下跑）

## 已知陷阱

- `_scores_cache` 不會失效：「讀 → 改 → 再讀」會拿到舊值，測試斷言前要重新從 DB 取物件。
- `PROTECT` 擋得住刪除、擋不住編輯：題目被改，歷史分數會跟著改（Phase 1-5 快照決策）。
- `Submission.user` 是 `PROTECT`，做過篩檢的帳號無法刪除，但個資法下使用者有權刪除自己的健康資料，之後必須處理。
- `classify()` 的 40 分上限是 HHIE-S 專用，寫死在 `scoring.py`（Phase 1-3）。
- Django shell 是 autocommit，沒有 rollback。
- `Sum` 沒有 `default=0` 時，沒資料會回 `None` 而不是 0（踩過三次）。
- macOS 檔名不分大小寫：git 追蹤的是小寫 `claude.md`，clone 到 Linux 會讀不到 `CLAUDE.md`。

## 參考文件

- `docs/decisions.md` — 做過的決策、理由、踩過的坑。
- `docs/roadmap.md` — 各 Phase 的待辦與目前進度。
- `docs/specs/phaseN.md` — Phase 3 起每個 phase 開工前的規格（要經我確認權限與計分邏輯）。
- `~/.claude/plans/code-review-drf-react-claude-md-mellow-sky.md` — 最新一份 code review 報告（新 session 不會自動載入）。

## 目前階段

Phase 1：正確性（1-3 `classify()` 門檻表 → 1-4 N+1 → 1-5 快照決策）。Phase 0 還剩 debug-toolbar 和 `check --deploy`。細節見 `docs/roadmap.md`。
