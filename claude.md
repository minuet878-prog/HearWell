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
- **長的內容寫成檔案，對話裡只放摘要**：終端機畫面在長的 session 裡可能被洗掉，不能當保存的地方。超過一個畫面的內容（例如審查報告、長的計畫），寫進檔案，對話裡只放三到五行摘要和檔案路徑。
  - 流程裡已經指定位置的（規格檔、`docs/interview.md`），照原本的位置寫。
  - 沒有指定位置的，寫到 `docs/reviews/`，檔名對應規格檔（例如規格檔 `phase4_trend_chart.md` → `phase4_trend_chart_review.md`）。
  - 測試結果照第 7 步在對話裡貼出；全文太長時，貼通過／失敗數和失敗項目，全文另存。
  - 審查用的 `reviewer` subagent 是唯讀的，不能寫檔：它回傳報告，由你（主 session）存進 `docs/reviews/`。

## 工作流程（順序固定，不可跳步）

### 1. 開工先讀紀錄
讀 `docs/roadmap.md`，以及 `docs/decisions/` 裡跟這次任務相關的主題檔（先看 `README.md` 索引），用三行以內告訴我：現在做到哪、還欠什麼、這次打算做什麼。

### 2. 先把需求講清楚
- 動手前，照 `docs/specs/spec_template.md` 建立這次的規格檔 `docs/specs/phaseN_主題.md`（例如 `phase2_b1_hearing_aid.md`），狀態設為「草稿」。每個任務都要寫，小任務可以寫短。
- 需求寫成規格檔第 5 節的驗收條件（Given / When / Then，也就是劇本），還沒想清楚的列在第 6 節「待決問題」，給我確認。
- 一直問到沒有模糊的地方為止。寫不出劇本，代表需求還沒想清楚，退回來問我。
- 我確認後，把答案寫回規格檔、劃掉待決問題，狀態改成「已確認」。狀態不是「已確認」就不能開始實作。
- 涉及畫面或計算的需求，先用一兩句話複述你理解的內容。
- 畫面有多種做法時，先做一頁純 HTML 的比較頁讓我選，任務結束後刪掉。
- 討論需求時不要提會動到哪些檔案、怎麼實作，免得洩題（第 3 步要我自己預測）。

### 3. 開工前：我先預測
在 `docs/interview.md` 第二部分「開發紀錄」新增這次的章節：「這次要做什麼」只寫一句話，加上規格檔的連結（不重複抄劇本）；「我的預測」留空。
然後停下來，等我寫完預測（會改哪些檔案、新增哪些東西、最難的是哪裡）並說「寫好了」。讀過我的預測，才進第 4 步。

### 4. 先提計畫，等我點頭
改任何檔案之前，先說你要改哪些檔案、怎麼改。我確認後才動手。
審查或驗收之後要追加修改，一樣先提計畫、等我點頭。

### 5. 先寫測試
規格檔的每一條驗收條件至少對應一個測試。先確認測試會失敗，再寫實作讓它通過。

### 6. 寫最少的程式
動手前依序問自己，哪一題答「是」就停：
1. 這真的需要嗎？不需要就不寫。
2. 專案裡已經有了嗎？直接用。
3. 語言或框架內建就有嗎？用內建。
4. 一行能解決嗎？寫一行。
5. 以上都不行，才寫新的。

不要加我沒要求的功能、設定選項或抽象層。選技術時優先選主流、文件多的，不選新奇的。

### 7. 交出證據才能說完成
實際跑測試，貼出結果，再拿規格檔的驗收條件逐條打勾（直接勾在規格檔裡）。沒跑過就不能說「完成了」。

### 8. 請另一個 subagent 審查
派 `reviewer` subagent（定義在 `.claude/agents/reviewer.md`）檢查。交辦時只給規格檔路徑和要比對的分支或基準，不要附上你的實作理由或判斷，讓它獨立審查。檢查內容：有沒有 bug、有沒有多寫、有沒有漏掉驗收條件、有沒有做了規格「不做」清單裡的事。審查意見要逐項查證（能重現的就實際重現），分成「要修」「補測試」「不改」三類，每項說明理由，再告訴我。

### 9. 收尾
1. 刪掉比較頁和暫存檔。
2. 跑 `git status` 給我看，確認沒有不該進版控的東西。
3. 更新 `docs/roadmap.md`（做完什麼、下一步）。
   同時填寫規格檔最後的「完成後回報」，把狀態改成「已完成」。新概念和面試題在規格檔只列名詞和題目，完整內容（要點、預測、驗收練習）寫在 `docs/interview.md`。
4. **`docs/decisions/` 由我自己寫**：你只在對話裡列素材（情境、決策和理由、踩到的坑、建議放哪個主題檔），不要直接寫進檔案。寫完我會請你看；寫不出「為什麼」的地方，用問題引導我，不要替我寫。
5. 更新 `docs/interview.md`：
   - 第二部分「開發紀錄」這次的章節補上：
     - 「預測對照」：我的預測哪些對、哪些錯、錯在哪
     - 「改了什麼」：問題、做法、動到的檔案
     - 「面試題」：只列題號和所屬主題
     - 「驗收練習」：一個「蓋起來重講」的題目（例如一個請求從進來到回應經過哪些步驟），和一個「故意弄壞」的建議（改哪一行、讓我先預測哪個測試會失敗）
   - 第一部分「主題」：新概念加進對應主題的名詞表；面試題 2–3 題放進對應主題，每題留「我的回答」空白，要點用 `<details>` 折疊。題號全檔接續、不重編。沒有合適的主題就新增一個。
   - 更新開頭的目錄。
   回報時也附上新概念和面試題，讓我挑不熟的深入問。
6. 提出 commit message（Conventional Commits 格式），等我同意才 commit。
7. commit 之後提醒我做驗收練習：
   - 蓋起來重講：我講，你指出漏掉或講錯的地方。
   - 故意弄壞：由我自己改、自己跑測試、自己還原；你不要動檔案。結束後跑 `git status` 確認乾淨。
8. 問我這條分支要合併回 `main`、推到遠端、還是先放著。不要自己合併或 push。

### 遇到 bug
1. **先給我試**：只告訴我錯誤訊息和發生在哪裡，不要給原因或修法。等我自己試 20 分鐘，或我說「交給你」。
2. 我試完（或交給你）之後：不准猜、不准「改改看」。先找出根本原因並告訴我，確認後才修，而且要修在源頭。同一個原因造成的其他地方一併檢查。
3. 我自己找到原因的話，你只確認對不對、補充我漏掉的。

## 不可違反的規則

### 通用

1. **Git**：一律在分支上工作，不直接改 `main`。未經我同意不 commit、不 push。commit 的作者身分用我的 git 設定；環境裡沒有設定時先問我，不要自己填。
2. **不擅自動我的資料**：不刪除、不覆寫、不批次修改任何真實資料（資料庫、資料檔、匯出檔）。需要這樣做時先說明會影響什麼，等我同意。
3. **真實個資與病人資料不進版控**，也不寫進測試、範例或 log。測試一律用假資料。
4. **不碰我的服務**：不自己啟動、重啟或停掉我電腦上的伺服器和資料庫，需要時請我來做。
5. **試驗要先講**：臨時、探索用的修改，先說「這是試驗」，結束後主動還原。
6. **垃圾不進版控**：虛擬環境、`node_modules`、`.env`、`.claude`（`.claude/agents/` 除外：審查用的 subagent 定義要進版控）、log、暫存檔一律不加。
7. 密碼、金鑰、連線字串只放 `.env`，不寫進程式碼。

### HearWell 專屬

8. **所有查詢都要限定在 `request.user`**（view 與 API 都一樣）。這是 IDOR 防護（越權存取別人的資料），曾經出過漏洞。API 要有「非本人資料回 404」的測試。
9. **分級與計分只用規則式程式碼**。LLM 只能用在自然語言輸出，不能用在分類或計算。
10. **每個讀取分數的地方都走同一條計算路徑**（`Submission` 的計分方法），不要另寫一份聚合。API 由後端算好回傳，前端不重算。
11. **0 是合法分數，不能當「沒資料」的哨兵值**。空的 submission 要另外處理。
12. **不要在 shell 對正式資料庫做操作來驗證行為**，要驗證就寫進 `screening/tests/`。
13. 介面字級一律用 `rem`，不用 `px`（使用者多為 65 歲以上）。

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

- `User`（AbstractUser ＋ `birth_date`，允許 null ＋ `age` property）；引用時用 `settings.AUTH_USER_MODEL`
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
- 作答過的題目、有作答紀錄的問卷 `code`，在 admin 是唯讀的；Submission／Answer 在 admin 只能看，不能新增、修改、刪除。要改題目就新增一份問卷（新 pk、新 code），不要改舊的。
- 已上線的問卷不能加題（admin 沒擋，靠規則）：加了之後新作答的滿分會超過門檻表，變成「無法判讀」。
- 刪除帳號要走 `User.delete_with_data()`（交易內由下往上刪），不要直接 `user.delete()`：`Submission`、`Audiogram`、`Consent` 對 User 都是 `PROTECT`，會被擋下。
- `build.sh` 每次部署都會 `loaddata`，而且繞過 admin 的鎖：fixture 裡已上線的題目不能改，要改就新增一份問卷。
- 門檻（`scoring.THRESHOLDS`）第一次要改之前，先做規則版本號，不要直接改數字，否則歷史分級會被回溯改寫。
- Django shell 是 autocommit，沒有 rollback。
- `Sum` 沒有 `default=0` 時，沒資料會回 `None` 而不是 0（踩過三次）。
- macOS 檔名不分大小寫：git 追蹤的是小寫 `claude.md`，clone 到 Linux 會讀不到 `CLAUDE.md`。

## 參考文件

- `docs/decisions/` — 做過的決策、理由、踩過的坑，照主題分檔；`README.md` 是索引。
- `docs/roadmap.md` — 各 Phase 的待辦與目前進度。
- `docs/specs/` — 每個任務開工前的規格，照 `spec_template.md` 寫；狀態「已確認」才能實作。
- `~/.claude/plans/code-review-drf-react-claude-md-mellow-sky.md` — 最新一份 code review 報告（新 session 不會自動載入）。

## 目前階段

Phase 0–7 已完成（Phase 6 只剩時間型的 HSTS 拉長、e2e 列為必要檢查）。Phase 8 分享完成（C3 聽力報告、C1 家屬衛教頁、C1-B 分享聽力報告給家屬）。Phase 9 前端設計重整分四輪：第 1–3 輪（共用版型、資料呈現的錯誤、結構調整）完成，下一步第 4 輪增加豐富度。細節見 `docs/roadmap.md`。