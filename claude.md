這是一份現職為聽力師想要轉職軟體工程師的人的 side project，請依照現職人員的要求給我建議，
並且最好可以與底層概念相連（比如資料結構/演算法…等）。

專案：HearWell — 聽力健康自我照護工具

## 互動規則（最重要）

- **不要直接寫程式碼給我**。用問題引導我思考，讓我自己寫。只在我寫完之後指出錯誤。
- **引導問題一次只問一題**。問完就停，等我答完、你回饋完，才問下一題。不要一次列 3～5 題。
- 純 API 細節（方法名、import 路徑）不必用問題包裝，可以直接問我要不要講。
- 用 Plan Mode（Shift+Tab 切換）。
- `docs/decisions.md` 的條目要**簡短口語**，不要寫成長篇技術分析報告。review 報告可以詳細，decisions.md 不行。

## 目前進度（2026-09-21）

功能已完整可跑的一條線：註冊 → 登入 → 選問卷 → 作答 → 計分 → 看結果（含分級與行動建議）→ 歷史紀錄。

- Django 5.2 + Python 3.13，專案名 `config`，app 名 `screening`
- Model 全部 migrate 完成（0001–0010），含 UniqueConstraint / CheckConstraint / 複合索引
- 8 個 template，全部繼承 `layout.html`；Bootswatch Minty
- `forms.py` 用 formset 收作答；`scoring.py` 負責分級/顏色/建議文字
- `tests.py` 11 個測試（classify 邊界、跨使用者存取隔離、login_required、formset 流程、兩個 UniqueConstraint）
- 部署設定齊全：whitenoise、dj-database-url、`build.sh`、prod 安全設定（DEBUG=False 時強制 SECRET_KEY）
- `docs/decisions.md` 記錄每個決策的理由與踩到的坑；`docs/roadmap.md` 記錄還沒開始的功能構想

## 接下來要做（依序，詳見 ~/.claude/plans/ 的 review #4）

**Phase 0 — 讓自動檢查恢復作用**（不新增功能）
1. ruff 排除 migrations（現在 `ruff check .` 有 31 個錯誤全在自動產生的 migration 裡，等於 linter 失效）
2. 擴充 ruff 規則集（`B`/`DJ`/`TID`/`RUF`）
3. 補計分聚合測試（E 滿分 / S 滿分 / 混合 / 0 個 answer）—— 09-09 的 `default=0` 至今「改了但沒驗證」
4. 裝 django-debug-toolbar
5. 在 Render 環境跑 `manage.py check --deploy`

**Phase 1 — 正確性**
6. 空 submission 顯示成「無影響」（正式 DB 有 4 筆）—— 擋住新的 ＋ 清掉既有
7. 作答驗證從 view 搬到 form 層（重複作答會 500、`zip` 位置耦合）—— **搬到 form 而非留在 view，DRF serializer 才能共用**
8. `classify()` 的 40 分上限改成門檻表，決定這個上限該住哪
9. `my_hearing` 的總分與等級來自兩條獨立查詢 → 收斂成單一計算路徑
10. 決定要不要存分數快照（題目被編輯後歷史分數會回溯改寫）

**Phase 2 — 產品價值（仍用 Django template）**
11. A3 分項解讀（情緒/社交哪個偏高 → 不同解讀）—— 投報率最高、也最需要臨床背景
12. 未登入動線：登入後回到 `?next=`，首頁 CTA 不要繞回原地
13. 改用 `UserCreationForm`，順便收 `birth_date`
14. A1 年齡導引（依 age 推薦 HHIE-S / HHIA-S）
15. 文案錯字、英文殘留、作答頁用 `__str__` 當題目文字（30 字會被截斷）
16. 無障礙基礎（字級、對比、focus、觸控目標）

**Phase 3 — DRF 唯讀 API** → **Phase 4 — React（從趨勢圖開始）** → **Phase 5 — 寫入 API / Audiogram / 家屬版**

## 架構方向：DRF + React（已決定，2026-09-21）

- **漸進導入**，不全站重寫。Django template 繼續服務首頁/登入/註冊/結果頁，React 只做互動重的頁面（趨勢圖 → 問卷作答 → Audiogram）
- **同源部署**：Vite build 產物進 `staticfiles`，whitenoise 一起服務。Render 一個服務、$0
- **認證沿用 session cookie**，不用 JWT。理由：HttpOnly cookie 的 XSS 暴露面小於 localStorage token，而且登出能真正撤銷
- **CORS 不需要**（同源），CSRF 沿用 Django 現有機制
- **Strangler 模式**：`/api/` 與現有 view 並存，共用 model 與業務邏輯。任何時間點 main 都是完整可用的產品
- **唯讀 endpoint 先行**，寫入（作答提交）最後做
- 用 `drf-spectacular` 產 OpenAPI schema —— 把介面從「約定」變成可檢查的「產物」
- **65+ 使用者 × SPA 的三個風險**要主動處理：首屏 JS 體積、焦點管理與上一頁、字級縮放（用 `rem` 不用 `px`）
- 登入/註冊**不要**React 化：SPA 的 auth 最麻煩、加值最低

## 常用指令

- `python manage.py runserver` — 啟動開發伺服器
- `python manage.py makemigrations screening` — 產生 migration
- `python manage.py migrate` — 套用 migration
- `python manage.py shell` — Django shell（**autocommit，破壞性操作一律 `atomic()` ＋ 最後 `raise` 做 dry run**）
- `python manage.py test` — 跑測試
- `python manage.py check --deploy` — 部署前安全檢查（要在 `DEBUG=False` 下跑）
- `ruff check --fix .` — 檢查並修正格式

## 專案結構

- `config/` — Django 專案設定（settings.py, urls.py, wsgi.py）
- `screening/` — 主要 app
  - `models.py` `views.py` `forms.py` `scoring.py` `admin.py` `tests.py` `urls.py`
  - `templates/screening/` — 8 個 template，全部繼承 `layout.html`
  - `templatetags/custom_filters.py` — `level_to_color` filter
  - `migrations/` — 0001–0010
- `docs/decisions.md` — 已經做了什麼、為什麼這樣做、踩到什麼坑（這是這個 repo 最有價值的檔案）
- `docs/roadmap.md` — 還沒開始、但已經想過方向的功能（不進版控）
- `py313/` — 虛擬環境（不進版控）
- `pyproject.toml` — Ruff 設定
- `build.sh` — Render 部署腳本（pip install → collectstatic → migrate）
- `questions_fixture.json` — HHIE-S 十題的 fixture

## 資料模型

- `User`（AbstractUser + `birth_date` + `age` property）
- `Questionnaire` → 多個 `Question`（FK, PROTECT）
- `User` → 多個 `Submission`（FK, PROTECT）
- `Questionnaire` → 多個 `Submission`（FK, PROTECT）
- `Submission` → 多個 `Answer`（FK, PROTECT）
- `Answer` → `Question`（FK, PROTECT）
- 每題答案存成一列（正規化），不是欄位
- 約束：`Question(question_number, questionnaire)` 唯一、`Answer(submission, question)` 唯一、`category` 與 `score` 各有 CheckConstraint
- 索引：`Submission(user, -created_at)` 複合索引
- 計分：`Submission._calculate_scores()` 用 `Sum("score", filter=Q(question__category=...), default=0)` 一次 aggregate 拿三個值，結果存在 `_scores_cache`

## 設計決策（完整版見 docs/decisions.md）

- 使用者引用用 `settings.AUTH_USER_MODEL`，不直接寫 `User`
- `birth_date` 允許 null（註冊時不強制）—— 但 A1 年齡導引需要它，Phase 2 要開始收
- 總分不另存欄位，每次從 answers 即時計算 —— 代價是每個讀取點都必須走同一條計算路徑（Phase 1-9 要收斂）
- HHIE-S 和 HHIA-S 共用同一組表，靠 `questionnaire` 欄位區分
- `category` 欄位區分 emotional / social 分項
- `aggregate(Sum)` 對空集合回傳 `None`，一律加 `default=0`；用 `filter=` 而不是 `Case/When`（兩種「空」才會被同一個 default 包住）
- **但 `default=0` 有後遺症**：0 個 answer 的 submission 會顯示成「總分 0 → 無影響」。0 是合法分數，不能當「沒資料」的哨兵值（Phase 1-6）
- `_scores_cache` 永不失效：在單次 request 內正確，但 shell 和測試裡「讀→改→再讀」會拿到舊值，斷言前要重新從 DB 取物件
- `classify()` 的 40 分上限是 HHIE-S 專用（10 題 × 4 分），寫死在 `scoring.py`（Phase 1-8 要改成門檻表）
- `on_delete=PROTECT` 全面採用：擋得住刪除，**擋不住編輯**（題目改了歷史分數會漂移）
- `Submission.user` 是 PROTECT，所以做過篩檢的帳號無法刪除 —— 個資法下「刪除自己的健康資料」不是可選功能
- Shell 是 autocommit，沒有 test DB 也沒有 rollback。要驗證行為就寫進 `tests.py`

## 目標使用者

- 台灣的聽損患者及其家屬
- 年齡層偏高（65+），介面要清楚、字體要大
- 繁體中文介面
- 量表內容基於 HHIE-S（65 歲以上）和 HHIA-S（65 歲以下）
- 這個族群讓無障礙從「加分項」變成「必需品」，也是不做全站 SPA 的理由之一

## Code review 報告

四份都在 `~/.claude/plans/`，新 session 不會自動載入，需要時要主動去讀：

1. `model-zippy-lovelace.md` — 第一輪，最完整。安全性 S1–S9、model M1–M6、重構 R1–R9、命名，外加功能規劃 A/B/C/D
2. `code-review-cheerful-bubble.md` — 第二輪，8 項，密碼驗證/DB 約束/template 繼承/存取控制
3. `claude-code-review-claude-md-code-rebie-majestic-snail.md` — 第三輪，F-1～F-12 ＋ 前兩輪結案盤點
4. `code-review-drf-react-claude-md-mellow-sky.md` — **第四輪（最新）**，G-1～G-8 ＋ DRF/React 導入順序（Phase 0–5）
