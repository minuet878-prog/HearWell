# Roadmap

還沒做、但已經想過方向的功能構想。跟 decisions/ 不一樣——這裡是「還沒開始做」
的待辦，decisions/ 記的是「已經做了、為什麼這樣做」。等真的開始動手某一項，
再把過程搬去 decisions/ 對應的主題檔。

**閱讀順序**：先看「開發階段」確認目前在哪個 phase，再看該 phase 底下要做的功能。
功能不再另外排優先順序，一律以所屬 phase 為準。

---

## 開發階段（Phase）

**目前進度：Phase 6 進行中**（Phase 0–5 完成並合併，2026-10-16；2026-10-16 重新規劃：Phase 6 穩固 → Phase 7 個資 → Phase 8 分享；Phase 6 CI 完成（2026-10-16）；Phase 6 第 2–5 項、錯誤監控、端對端測試、無障礙重新量測完成；Phase 6 只剩時間型的 HSTS；Phase 7 同意書與隱私權說明頁完成（2026-10-17）；資料匯出完成（2026-10-17）；帳號與資料刪除完成（2026-10-17），Phase 7 完成；Phase 8 C3 聽力報告完成（2026-10-17）；C1 家屬版拆成 C（家屬衛教頁，2026-10-17 完成）與 B（分享聽力報告給家屬，2026-10-17 完成），Phase 8 完成；Phase 9 前端設計重整（依本人的設計檢討分四輪）第 1–3 輪（共用版型、資料呈現的錯誤、結構調整）完成（2026-10-17）；第 4 輪拆四份（4a 首頁、4b 問卷卡片、4c 聽力圖縮圖、4d IOI-HA 逐題解讀）完成，Phase 9 完成（2026-10-18））

### 兩個已定案的方向（2026-10）

1. **Phase 3–5 交給 AI 代工**：每個 phase 開工前，先在 `docs/specs/phaseN.md`
   寫好規格（可由 AI 擬稿，必須經過本人確認權限與計分邏輯後才開工）。
   實作在獨立分支進行，測試通過、人工驗收後才合併回 main。
2. **app 形式先做 PWA**：可加到手機主畫面的網頁 app，不上架 App Store／Google Play。
   因此維持現有架構：同源部署、session cookie 驗證，不需要 CORS、不需要 token。
   未來若要上架原生 app，再於 DRF 加上 token 驗證即可，endpoint 不必重寫。

架構總方向（strangler pattern、同源部署等）的決策原因記在 decisions/architecture.md（待補）。

### Phase 0：恢復 linting／檢查
- [x] ruff 排除 migrations
- [x] ruff 擴充規則集（B / DJ / TID / RUF）
- [x] 計分聚合測試
- [x] 裝 debug-toolbar（只裝本機：`requirements-dev.txt`；規格 `docs/specs/phase-00/phase0_dev_checks.md`，2026-10-15）
- [x] `check --deploy`：每次部署在 `build.sh` 最前面跑，警告也算失敗；同時開 HSTS（1 小時、含子網域）
- [x] 鎖定 Render 的 Python 版本：`.python-version` 3.13.15（原本 Render 自動用 3.14.3）
- 沒做完的三項（HSTS 拉長、`ruff` 搬家、`ALLOWED_HOSTS` 空字串）→ Phase 6

### Phase 1：正確性（完成）
Phase 3 的前置條件：API 化會把這裡的 500 和 N+1 直接暴露出去。
- [x] 1-1 空 submission 不存（PR #5）
- [x] 1-2 作答驗證搬到 formset（PR #6）
  - 尾巴：補 `assertContains` 測試，確認錯誤訊息真的出現在畫面上；
    F-6 位置耦合（POST 順序被打亂會對錯題）
- [x] 1-3 `classify()` 改成門檻表（`Questionnaire.code` ＋ `scoring.THRESHOLDS`，滿分＝最後一級上限）
- [x] 1-4 `my_hearing` N+1 → 計分公式只剩 `_score_expressions()` 一份，列表 annotate、單筆 aggregate
- [x] 1-5 快照決策：題目作答過就鎖（admin），門檻將來用規則版本號，`completed_at` 等 D2（見 decisions/scoring.md）

### Phase 2：產品價值（仍用 Django template）（完成）
- [x] **結果頁分項說明**（取代 A3）：分項分數下方註明「僅供參考，沒有正式的解讀標準」
- [x] **B1 助聽器配戴標記**：作答頁第一題前必填「有戴／沒戴」，結果頁與歷史頁顯示，
  舊紀錄顯示「未記錄」（`Submission.wearing_hearing_aid`，見 `docs/specs/phase-02/phase2_b1_hearing_aid.md`）
- 以下從 code review 報告補回，不做的話寫一句原因再刪：
  - [x] 未登入動線：登入／註冊後回到 `?next=`（只接受本站網址），登入頁說明、首頁提示
    （見 `docs/specs/phase-02/phase2_login_next.md`）
  - [x] 註冊改用 `UserCreationForm`，選填民國出生年（存西元 `birth_year`，取代 `birth_date`；見 `docs/specs/phase-02/phase2_register_form.md`）
    - `LoginView`、同名註冊 500 → Phase 6
    - 還沒做：Django 內建訊息（密碼規則、欄位說明）用「你」，跟站內「您」不一致；要改得覆寫驗證器或翻譯檔
  - [x] 錯字、英文殘留、孤兒 `</li>`、作答頁題目被 `__str__` 截斷成 30 字（見 `docs/specs/phase-02/phase2_copy_fixes.md`）
    - 範圍外、還沒處理：首頁只寫 HHIE-S、沒提 HHIA-S（內容正確性）；分數旁的半形冒號；
      ~~註冊頁 placeholder 拼錯 `Cofirmation`~~（改用 `UserCreationForm` 後已不存在）
  - [x] 無障礙基準線：量測方法與結果見 `docs/accessibility/accessibility_baseline.md`；已修內文／`text-muted` 對比、分級與錯誤文字顏色、
    作答頁 `fieldset`／`legend`、選項統一為橫排大按鈕（見 `docs/specs/phase-02/phase2_a11y_baseline.md`）
    - 量到沒修的項目、下次量測要補的狀態 → Phase 6 重新量測

### Phase 3：DRF 唯讀 API（AI 代工）（完成）
- [x] 第 1 批：DRF＋drf-spectacular、`/api/` 預設要登入、問卷列表、schema 檔與比對測試（驗收 1–6）
  - 坑：DRF 的 zh_Hant 翻譯會蓋掉 Django 核心翻譯（全站），用專案 `LOCALE_PATHS` 蓋回
- [x] 第 2 批：歷史紀錄（cursor 分頁，`-created_at, -id`）、單筆結果（驗收 7–18）
  - 已知限制：時間完全相同的紀錄往回翻（`previous`）可能不正確，實際上不會發生，接受
- `/api/` 與既有 template view 並存，不改動既有頁面。
- 只做讀取（GET），寫入留到 Phase 5。
- 優先做 Phase 4 趨勢圖需要的資料（使用者自己的歷次作答與分數）。
- 權限原則：未登入不可呼叫；只能取得自己的資料（防 IDOR）。
- 計分沿用 Submission 的 QuerySet／property，由後端算好回傳，前端不重算。
- 細節見 `docs/specs/phase-03/phase3.md`。

### Phase 4：React 前端 + PWA（AI 代工）（完成）
- [x] 第 1 批：B2 趨勢圖（Vite＋React＋Recharts，只在「我的聽力」頁載入；問卷 API 加 `levels`；Render 上建置）
  - 正式站看得到圖（2026-10-15 確認）；還沒核對：build log 的 Node 版本是 `.node-version` 的 24.21.0（不是就代表 Python 服務沒讀這個檔）
  - Django 測試改用 `--settings=config.test_settings`（不需先 collectstatic）
  - JS 體積 brotli 141 KB（含 React）；若之後要壓，可考慮較小的圖表套件或自己畫 SVG
- [x] 第 2 批：PWA（規格 `docs/specs/phase-04/phase4.md` 第 2 批）
  - 只有 manifest＋圖示（B1 耳朵），不用 service worker、不做離線；全螢幕、先到首頁
  - 說明頁「把 HearWell 加到手機主畫面」（iPhone 提醒第一次要再登入）
  - 手機驗收 24–26 通過（2026-10-15）：iPhone 按鈕名稱與說明頁一致；`apple-mobile-web-app-capable` 保留
- [x] 介面改版第 1 批：共用版型（規格 `docs/specs/phase-04/phase4_ui_redesign.md`）
  - 原版 Bootstrap 5.3.8＋自訂 `styles.css`：深藍主色 #1f4e8c、18px、系統字型；拿掉 Bootstrap JS
  - 導覽：首頁／開始篩檢／我的紀錄（未登入：首頁／登入／註冊）；寬螢幕上方、手機底部分頁列；320px 不需左右捲動
  - 無障礙基準線第 3 節 7 項全部處理；趨勢圖改版（摘要框、每點標分數、淡分級底色）
- [x] 介面改版第 2 批：逐頁動線（規格 `docs/specs/phase-04/phase4_ui_flow.md`）
  - 首頁：開始篩檢在最上面、三步驟、免責聲明，文案只寫真的有的功能、不寫量表名稱
  - 選問卷頁：適合對象、題數、時間（`scoring.QUESTIONNAIRE_INFO`，依問卷代碼；為 IOI-HA 預留）
  - 作答頁：「第 n 題／共 N 題」；結果頁：分級色塊在上、下一步按鈕、作答明細收合
  - 審查留下的觀察：結果頁的分級文字不是標題（`<h…>`），axe 沒標出，暫不改
- [x] 小任務：作答時竄改 `form-TOTAL_FORMS` 會 500（規格 `docs/specs/phase-04/phase4_fix_total_forms.md`）：每張子表單都必須驗證（`empty_permitted=False`）
- Vite build 進 staticfiles，由 whitenoise 提供，維持單一 Render 服務。
- 只有互動需求高的頁面用 React；login／register 維持 Django template。
- **B2 趨勢圖**：第一個 React 頁面，把多次填答的分數畫成折線圖。
  圖表函式庫在 Phase 4 規格中決定。
- **PWA 化**：加入 manifest（app 名稱、圖示、主題色）與 service worker，
  做到「可加到主畫面」即可。資料需登入且要即時，初期不追求完整離線。
- API 未登入時的 `detail` 是英文（DRF 沒有翻譯）；React 要顯示給使用者時，前端自己決定中文訊息。
- **D1 無障礙（基本要求）**：目標族群偏年長，React 頁面從一開始就要顧及
  字級、按鈕大小、對比度，不留到最後補。

### Phase 5：寫入 API + 第一批大功能（AI 代工）（完成）
- [x] **寫入 API：作答送出**（規格 `docs/specs/phase-05/phase5_api_submit.md`，2026-10-15）
  - `POST /api/submissions/`：收據編號（`Idempotency-Key` header，UUID、必填）防重複，重送回 200、內容不同回 409；只收 HHIE-S／HHIA-S
  - `GET /api/questionnaires/{id}/`：題目全文與選項（React 作答頁要用）
  - 驗證與存檔共用網頁版的 `AnswerFormSet`（`save()` 是全有或全無）
  - 待辦：開放 IOI-HA 寫入時，要補「答案倒序送出、每題選項不同」的測試（目前依題號排序沒有測試保護）
  - 網頁版作答連按兩次（F-10）→ Phase 6
- [x] **README 重寫**（規格 `docs/specs/phase-05/phase5_readme.md`，2026-10-15）：內容對齊目前程式碼；開頭數據改依文獻（四成、可達 10 年），出處列在最下面「參考資料」
- [x] **React 作答頁＋D2 作答中途儲存**（規格 `docs/specs/phase-05/phase5_react_answer.md`，2026-10-16）
  - HHIE-S／HHIA-S 一題一頁，同一個網址：Django 表單是 JS 失敗時的備用，拿到題目才換成 React 版；IOI-HA 維持網頁版
  - 上一頁＝上一題（`history.pushState`，重新整理後沿用已存在的紀錄）；送出走寫入 API，帶收據編號
  - 中途儲存存在瀏覽器 `localStorage`：綁帳號、7 天、別的帳號打開或登出就刪，收據編號一起保存
  - 建置輸出改到 `static/screening/frontend/`（三個進入點：趨勢圖、作答頁、登出）；作答頁 brotli 約 61 KB
  - 不改（審查 F6、F9）：送出失敗後按上一題，錯誤訊息會留在前一題；CSRF token 過期也顯示「登入已經過期」
  - 之後可以考慮：存在伺服器的中途儲存（換裝置接著答）；React 版 IOI-HA（API 要先開放 IOI-HA 寫入）
  - 修正（規格 `docs/specs/phase-05/phase5_answer_flash.md`，2026-10-16）：載入時不再先閃過全部題目。表單前的 inline script 先藏表單、顯示「題目載入中…」；React 拿到題目才接手，失敗或 5 秒內沒接手就放回網頁表單（之後才拿到題目也不接手）
  - 網頁表單驗證失敗後被 React 接手（審查 1-3）→ Phase 6
- [x] **聽力圖輸入 第 1 批**（規格 `docs/specs/phase-05/phase5_audiogram.md`，2026-10-16）
  - 新增：選符號（左右耳 × 氣導／骨導）後在圖上按住拖曳，放大鏡顯示數值；拖過下緣＝無反應（氣導 120、骨導只到 80）；遮蔽開關（ASHA △ □ [ ]）；再點一下刪除＋清除鈕；可收合的數值表給鍵盤與螢幕閱讀器
  - 檢視：每耳四頻平均、程度、類型（規則沿用 `~/audiogram_tool`，後端算），含無反應時加註；清單依檢查日期新到舊；另頁確認後刪除
  - 入口是導覽列最後一項「聽力圖」（不放「我的紀錄」的分頁籤）
  - 手機人工驗收（驗收 11）已通過（2026-10-16）
  - 已知：Mac 觸控板＋Chrome 偶爾在放開前就放掉指標鎖定，已改成用最後顯示的值結束拖曳；為什麼會先放掉還沒查明
- [x] **聽力圖輸入 第 2 批：修改、比較**（規格 `docs/specs/phase-05/phase5_audiogram_2.md`，2026-10-16）
  - 修改：檢視頁「修改這張聽力圖」→ 沿用新增頁的編輯器、帶入原本的點和日期；`PUT /api/audiograms/{id}/` 整張取代（全有或全無、不需要收據編號）
  - 比較：清單頁「比較聽力圖」（少於兩張不能按）；兩個下拉選單、預設最新兩張、新舊依檢查日期；一次一耳，舊的用同耳色淡色虛線；對照表逐頻率列差值（新 − 舊），一邊沒值寫「—」、有無反應寫「無法比較」；不標色、不寫「變差」
  - 不改（審查 2）：修改頁拖曳原本有遮蔽的點，會變成目前開關的遮蔽狀態（第 1 批的輸入規則）
  - 之後可以考慮：四頻平均的趨勢折線圖、三張以上比較
- C1 家屬版 → Phase 8

### Phase 6：穩固（技術債＋工程面）← 目前
順序依「先做的能保護後做的」：CI 先上，後面每項修正都有它把關。
- [x] **CI**（規格 `docs/specs/phase-06/phase6_ci.md`，2026-10-16）：GitHub Actions，PR 和合併進 `main` 時跑 Django 測試（PostgreSQL 18）、`ruff check`、前端測試與建置
  - GitHub ruleset：`main` 必須通過 `backend`、`frontend` 才能合併；Render 改成「CI 通過後才部署」
  - 待合併後確認：`main` 上也有跑（驗收 9 後半）、Render 等 CI 通過才部署（驗收 11）
  - 改 job 名稱要同時改 ruleset 的必要檢查，不然 PR 會卡在「等待檢查」
- [x] `ruff` 從正式環境的 `requirements.txt` 移到 `requirements-dev.txt`（原 Phase 0；規格 `docs/specs/phase-06/phase6_ruff_dev_only.md`，2026-10-16）
  - 一起刪掉 `click`、`h11`（只有沒在用的 `uvicorn` 需要）
  - CI 加「只裝正式清單」檢查：`check --deploy`＋`gunicorn --check-config config.wsgi`；抓不到 `brotli`（只在 collectstatic 用）
  - 待合併部署後確認：Render 安裝清單沒有 ruff、網站正常（驗收 5）
- [x] `ALLOWED_HOSTS` 設成空字串時 `check --deploy` 抓不到（原 Phase 0；規格 `docs/specs/phase-06/phase6_allowed_hosts.md`，2026-10-16）
  - 正式環境沒設也會報錯（原本安靜用本機預設）；空的一律報錯；去空白、丟空項
  - Render 部署成功，本人確認（驗收 7）
- [x] 網頁版作答連按兩次（F-10）（原 Phase 5；規格 `docs/specs/phase-06/phase6_web_double_submit.md`，2026-10-16）
  - 沿用 `Submission.idempotency_key`：每張作答頁一個收據編號，同頁重送（不論答案）轉到第一筆＋一次性說明；沒 JS 也有效
  - 「送出中…」按鈕回饋（`submit-button.js`），10 秒或按上一頁回來時恢復
  - 本人手機確認通過（驗收 13）
- [x] 網頁表單驗證失敗被 React 接手（審查 1-3，原 Phase 5；規格 `docs/specs/phase-06/phase6_web_form_errors_stay.md`，2026-10-16）
  - 驗證沒過重新顯示的頁面不送 React（view 傳 `use_react=False`），留在網頁表單，錯誤、已選答案、收據編號都在
  - 沒處理：只漏答助聽器題時頂端沒有錯誤摘要，只有該題紅字
- [x] 測試依功能分資料夾（規格 `docs/specs/phase-06/phase6_tests_by_feature.md`，2026-10-16）
  - `screening/tests.py`（約 5,000 行、43 個類別）拆成 `screening/tests/` 10 個檔，只搬家不改內容；356 個測試搬家前後清單相同
  - 只跑一組：`python manage.py test --settings=config.test_settings screening.tests.test_audiogram`
  - PR #49 CI 兩個檢查通過（驗收 6）
- [x] 登入改用內建 `LoginView`、同時同名註冊不再 500（原 Phase 2；規格 `docs/specs/phase-06/phase6_login_view.md`，2026-10-16）
  - 畫面、文字、`next` 動線不變；改變的只有：登入失敗後使用者名稱留在欄位裡、游標移到密碼欄
  - 只收 GET、POST（`LoginView` 繼承的 PUT 會被當成 POST，要另外限制）
  - 註冊撞車：顯示和一般同名一樣的訊息；不是名字被用走的 `IntegrityError` 照樣丟出
  - 已知限制：大小寫不同的名字（`Alice`／`alice`）同時註冊，資料庫只擋完全相同的名字，會建出兩個帳號（機率比同名撞車更低）
- [x] **錯誤監控**（原功能構想總表；規格 `docs/specs/phase-06/phase6_error_monitoring.md`，2026-10-16）：Sentry 免費版、資料放歐盟，有 `SENTRY_DSN` 才啟用
  - 只送錯誤類型、出錯位置、網址路徑與方法；`logger.error` 只送樣板。不送錯誤訊息、標頭（含 `X-CSRFToken`）、查詢字串、表單、cookie、IP、使用者、變數值、麵包屑、使用統計
  - 管理員測試網址 `/monitoring-test`（其他人 404）
  - 正式站已設 `SENTRY_DSN`，測試網址收得到 email（驗收 9，本人 2026-10-16 確認）；PR #51 CI 通過（驗收 6）
  - 之後可以考慮：前端（React）錯誤監控，要先評估 JS 體積
- [x] **端對端測試**（原功能構想總表；規格 `docs/specs/phase-06/phase6_e2e.md`，2026-10-16）：Playwright（Python）＋`StaticLiveServerTestCase`，Chromium 手機大小，一條主要動線（註冊 → HHIE-S → 結果 → 我的紀錄）
  - CI 獨立檢查 `e2e`，先不列為必要；**觀察一兩週（到 2026-10-30 左右）沒有偶發失敗，再加進 ruleset 的必要檢查**
  - PR #52：CI 的 `e2e` 通過；故意失敗一次確認截圖與 trace 可下載
  - 之後可以加：聽力圖、IOI-HA、JS 關閉時的表單、WebKit／桌機大小
- [x] **無障礙基準線重新量測**（原 Phase 2；規格 `docs/specs/phase-06/phase6_a11y_remeasure.md`，2026-10-16）
  - 2026-10-16 量完（報告 `docs/accessibility/accessibility_baseline.md` 第 5 節）：25 個頁面狀態 axe 違規全部 0；Phase 2 列的 7 項中 6 項確認已修、1 項部分已修
  - 新量到 11 項待辦（報告 5.4），最重的：聽力圖比較頁表格 320 px 撐寬整頁、舊聽力圖淡色 1.82:1、作答頁錯誤焦點與摘要、登入失敗訊息沒關聯欄位
  - 本人挑 1、3、4、5，同日修完並重量（報告 5.5）：比較頁 320 px 不捲動、作答錯誤摘要列出題目連結並取得焦點、登入失敗訊息關聯兩欄；其餘 7 項留在報告 5.4
- 時間型，不佔順序：HSTS 時效逐步拉長（`config/settings.py` 的 `SECURE_HSTS_SECONDS`）：
  觀察 1 週沒問題 → 86400（1 天，2026-10-22 起）→ 再 1 週 → 604800（1 週）→ 再 1 週 → 31536000（1 年）（原 Phase 0）

### Phase 7：個資與信任
Phase 8 分享、臨床端檢視的前置條件：資料要給別人看之前，先有同意、匯出、刪除。
- [x] **同意書與隱私權說明頁**：處理健康資料前取得明確同意（2026-10-17，分支 `feat/consent-privacy`，規格 `docs/specs/phase-07/phase7_consent_privacy.md`）
  - 上線閘門（驗收 16）已處理：營運者、信箱、地區（美國俄亥俄州）已填，測試防止【待補】再出現
  - 要寫出錯誤監控用到的第三方服務（Sentry，資料放歐盟；只送錯誤類型、位置、網址路徑，不送個資與作答，見 `docs/specs/phase-06/phase6_error_monitoring.md`）
- [x] **資料匯出**：使用者下載自己的全部紀錄，跟刪除權是一組（2026-10-17，分支 `feat/data-export`，規格 `docs/specs/phase-07/phase7_data_export.md`）
  - 「我的紀錄」頁按鈕＋隱私權說明頁連結 → 一個 JSON 檔（帳號、同意、問卷每題與分數、聽力圖每個點）；未同意新版說明的人也能下載
  - 沒做：易讀報告（Phase 8 C3）、API；隱私權說明頁仍寫「寄信要求複本」，自助下載是多一個管道
  - 順手修：e2e「我的紀錄」斷言的偶發失敗（React 趨勢圖重複分級文字）。e2e 列必要檢查的觀察期（約 10-30）從這次修正後重新算
- [x] **帳號與資料刪除**（2026-10-17，分支 `feat/account-deletion`，規格 `docs/specs/phase-07/phase7_account_deletion.md`）
  - 真的刪除、不匿名化；再輸入一次密碼；帳號、問卷與答案、聽力圖、同意紀錄一次刪光（交易），登出，其他裝置也失效；裝置上的作答暫存一起清
  - 未同意新版說明的人也能刪；管理員帳號不能自己刪（先移除管理員權限）
  - 說明頁：可以自己刪除；備份（Neon History window）6 小時內清除。改 History window 要同步改說明頁
  - 沒做：有人寄信要求刪除時的管理指令（真的有人寄信再做，可以直接呼叫 `User.delete_with_data()`）

### Phase 8：分享
需要 Phase 7 的同意機制。
- [x] **C3 聽力報告**（2026-10-17，分支 `feat/c3-report`，規格 `docs/specs/phase-08/phase8_c3_report.md`）：列印友善的網頁，瀏覽器印出或存成 PDF
  - 版面 C：重點摘要框 → 聽力圖（畫圖）→ HHIE-S／HHIA-S（最近一次＋最近 5 次）→ 配戴前後 → IOI-HA → 免責聲明；入口在「我的紀錄」
  - 只呈現網站已有的分數、分級、判讀，不加新判讀；假資料印出來是 A4 兩頁
  - 沒做：分享連結（留給 C1）、伺服器產生 PDF
  - 之後可以考慮：健康資料頁面全站加 `never_cache`（共用電腦登出後按上一頁仍看得到快取；目前報告、我的紀錄、結果頁都沒加，審查 4）
- **C1 家屬版**：2026-10-17 討論後決定做 B（家屬看得到結果）＋ C（給家屬的溝通與陪伴內容），不做家屬問卷、家屬協助作答
  - [x] **C：給家人的溝通與陪伴頁**（2026-10-17，分支 `feat/c1-family-guide`，規格 `docs/specs/phase-08/phase8_c1_family_guide.md`）：`/family` 不用登入，三段內容（說話方法、陪伴配戴助聽器、什麼時候要馬上就醫）由 AI 擬稿、本人審定，出處逐一查證；「傳給家人」按鈕用手機分享
    - 改文字要經本人審，測試逐字比對出處；之後可以加「看懂篩檢結果」「照顧者也要照顧自己」
  - [x] **B：分享聽力報告給家屬**（2026-10-17，分支 `feat/c1-family-share`，規格 `docs/specs/phase-08/phase8_c1_family_share.md`）：報告頁上方產生分享連結（確認後才產生、一次一個、7 天、可取消、看得到開啟次數）；家人先到封面（擋 LINE 預覽）再看報告，不顯示名稱與出生年；匯出含分享紀錄
    - 驗收 24 手機 LINE 實測通過（2026-10-17）
    - 沒做：多個連結、記錄是給誰、自訂期限；本人自己打開也算一次（審查 1-2，照規格）

### Phase 9：前端設計重整（完成）
來源：本人的「HearWell 前端設計檢討」（2026-10-17）。每個元素分量差不多、沒有分組，看起來散。分四輪、一輪一份規格：
- [x] **第 1 輪：全站共用的版型**（2026-10-17，分支 `feat/ui-shared-layout`，規格 `docs/specs/phase-09/phase9_ui_refresh_1_shared.md`）
  - 內容最大寬度 40rem；間距只用 Bootstrap 原有的值；全站淺灰頁尾（給家人看、加到主畫面、隱私權說明、免責聲明、聯絡信箱）
  - 程度標籤：問卷分級三色；聽力圖程度正常綠、輕度與中度黃褐、中重度以上紅、資料不足灰（本人臨床判斷，對應表在 `audiogram.DEGREE_LEVELS`）
  - 可點擊卡片統一（整張可點＋「›」）：選擇問卷、我的紀錄、聽力圖列表；每頁一顆實心按鈕
  - 首頁的「給家人看」「加到主畫面」移到頁尾（本人實作後追加）；首頁免責聲明那段留到第 3、4 輪
  - 之後可以清：`styles.css` 的 `.text-success／warning／danger` 覆寫可能已沒人用（審查 2-2）
- [x] **第 2 輪：資料呈現的錯誤**（2026-10-17，分支 `feat/ui-data-display`，規格 `docs/specs/phase-09/phase9_ui_refresh_2_data.md`）
  - HHIE-S 趨勢圖：沒戴實線、有戴虛線、未記錄只畫點，不跨狀態連線；摘要框只跟同一種狀態的上一次比
  - 橫軸以天為單位、最多最近五天，同一天的紀錄在同一條直線上（同天同狀態只畫最後一筆）；提示框、紀錄卡片加時間（橫軸只寫日期）；日期間至少 27px；以上是本人驗收時追加分級底色邊界畫在 9、25（HHIE-S 總分是偶數，「最高分＋1」；別份問卷要畫趨勢圖時改請後端給 `min`）
  - IOI-HA：格線改成元素、畫在每列正中間（e2e 量得到）；加「7 題都是分數越高，代表助聽器的效益越好」
  - 沒做：摘要框同日比較時加時間（審查 1-2，符合規格）；常模灰框蓋住框內格線（改之前就這樣）
- [x] **第 3 輪：結構調整**（2026-10-17，分支 `feat/ui-structure`，規格 `docs/specs/phase-09/phase9_ui_refresh_3_structure.md`）
  - 帳號設定頁（只看不改）：入口在頁首名稱與頁尾；下載資料、刪除帳號從「我的紀錄」搬過來；同意閘門放行；隱私權說明頁改寫位置
  - 問卷切換改成分開的小膠囊、自動換行（本人提醒問卷會變多）
  - 首頁：副標改講為什麼；「可達 10 年」改成不帶數字的一句話（沒有出處）；首頁的免責半句拿掉（頁尾有）
  - 趨勢圖分級文字改到圖下方的圖例（左上角在手機只有一筆時會壓到點、圖外右側會讓圖太窄，審查後本人決定）
  - 沒做：修改帳號資料；「前往同意」同意後回帳號設定（審查 4）；頁首深藍底上的鍵盤焦點框顏色（審查 6，原本就這樣）
- **第 4 輪：增加豐富度**：本人決定拆四份
  - [x] **4a 首頁**（2026-10-18，分支 `feat/ui-home-richness`，規格 `docs/specs/phase-09/phase9_ui_refresh_4a_home.md`）：淡藍底插圖區（耳朵聲波 SVG）、三張步驟卡片＋圖示（寬螢幕橫排、窄螢幕直排）、「結果長這樣」示意圖（HHIE-S 假分數 18 分，分級與建議取自 `classify`／`get_advice`）、淡藍底信任區塊（不具名，本人決定）；審查後修 200% 字級時卡片撐出畫面（`minmax(min(12rem, 100%), 1fr)`）
  - [x] **4b 問卷卡片與選擇引導**（2026-10-17，分支 `feat/ui-questionnaire-cards`，規格 `docs/specs/phase-09/phase9_ui_refresh_4b_questionnaire_cards.md`）：引導「第一次使用，請從 HHIE-S 開始；已經戴助聽器的人，可以再做 IOI-HA。」（本人審定）；卡片圖示（耳朵／助聽器／夾板，inline SVG）；題數、時間標籤；順序固定 HHIE-S、IOI-HA、其他照建立先後（原本資料庫沒指定順序）
  - [x] **4c 聽力圖縮圖**（2026-10-17，分支 `feat/ui-audiogram-thumbnails`，規格 `docs/specs/phase-09/phase9_ui_refresh_4c_audiogram_thumbnails.md`）：列表卡片左側 6×4.5rem 的氣導縮圖（右紅左藍，本人確認），伺服器畫 SVG（`screening/audiogram_thumbnail.py`），連線規則同大圖；右耳左耳各一行（手機上標籤與「右耳：」分兩行，本人可接受）
  - [x] **4d IOI-HA 逐題解讀**（2026-10-18，分支 `feat/ui-ioi-ha-items`，規格 `docs/specs/phase-09/phase9_ui_refresh_4d_ioi_ha_items.md`）：結果頁「低於常模」的題目，在回答下方加一段白話解讀（7 段，AI 擬稿、本人修改確認，存在 `scoring.IOI_HA_BELOW_NORM_NOTES`）；在範圍內、高於常模、未分組不顯示；出處區加「逐題解讀由聽力師依臨床經驗撰寫，不能取代個別諮詢。」；聽力報告與家屬分享版不放（本人決定，之後可再評估）
  - 注意：檢討文件建議的「有戴助聽器 → IOI-HA；沒有 → HHIE-S」引導不正確（HHIE-S／HHIA-S 依年齡；IOI-HA 是已配戴者的效益），做選問卷引導時要重寫

### Phase 10：PWA 使用體驗
- [x] **返回鍵與下拉重整**（2026-10-18，分支 `feat/pwa-back-refresh`，規格 `docs/specs/phase-10/phase10_pwa_back_refresh.md`）
  - 只在從主畫面打開（全螢幕）時出現；一般瀏覽器分頁本來就有，不重複放
  - 上一頁：藍色標題列左側的外框按鈕，首頁沒有；判斷用 `navigation.canGoBack`，舊 iPhone 用 `history.length`，不能退就回首頁（審查後拿掉 0.5 秒計時器，本人選 A）
  - 下拉重整：頁頂、單指、沒放大、頁面內容沒有表單欄位才作用；標題列的登出不算
  - 沒做：重新整理按鈕、左右滑動手勢、service worker
  - 驗收 14 實機（iPhone、Android）本人通過；舊 iPhone 沒有 Navigation API 時，「切回 app 時頁面被重新載入」後按上一頁可能沒反應（罕見，可按導覽列首頁）

### 無障礙修正（#70–#74，2026-10-20）

- #70–#73 已實作，2026-10-20 本人人工驗收通過並結案：HHI 結果等級標題、登入 autocomplete、唯一主標題及跳到主要內容；正常進頁不搶走 skip link 焦點，錯誤提示沿用。
- #74 已查證，2026-10-20 本人人工驗收通過並結案：歷史清單對輔助科技提供全部日期／分數；23 筆頁面與三筆瀏覽器測試確認，不新增重複清單或改動圖表。
- PR #88 已合併，backend／frontend／e2e 全數通過；測試、審查與人工驗收結果見[驗證紀錄](verification/issues-70-74.md)。

### Phase 10 之後
不預先排。從下面的「待定」和「功能構想總表」挑。

---

## 不做的項目

- **A3 分項解讀（2026-10-14 取消）**：HHIE-S 的情緒／社交分項沒有正式的解讀標準，
  量表只有總分的切點。自己訂門檻來解讀分項，等於自創臨床判讀，所以不做。
  結果頁仍然顯示兩個分項的分數，並註明沒有正式的解讀標準。

---

## 待定：尚未排入任何 phase

- **A1 年齡導引**：註冊已經可以選填出生年（`User.birth_year`，西元），但還沒用到。等真的要做第二份問卷、
  知道實際需要哪些條件時，再一起設計成通用機制。
  - 注意：`age` 是「今年 − 出生年」，生日還沒過的人會多 1 歲；64 歲的人可能被分到 65+ 的量表
  - 舊帳號大多沒有出生年，要決定沒有年齡時怎麼導引
- **C2 衛教內容**：提供聽力保健的教育性文章／資訊。
- **200% 字級的左右捲動**（4a 審查發現，2026-10-18）：頁尾 email 連結在 320px、200% 字級時撐到約 394px（每一頁都有，`main` 就這樣）；聽力圖結果 `.ear-results` 的 `minmax(14rem, 1fr)` 寫法相同，可能同樣問題（未重現）。另外 Phase 10 的 CI（Linux 預設字型較寬）發現：標題列「HearWell」（`.site-brand` 1.75rem 粗體、單字不能斷行）約 337px、被切掉；底部分頁列「聽力圖」也超出畫面（Mac 字型較窄，本機量不到；要在 CI 或 Linux 字型下驗）。e2e 可沿用 4a 的 `add_style_tag` 放大字級做法。
- **HHIE-S 出處**：網站上目前只有 IOI-HA 有出處頁；要補需本人提供原文與中文版出處（4a 規格另記）。
- 以及下方各個「待定」段落。

---

## 待定：新增其他中文版問卷（IOI-HA / APHAB / COSI、耳鳴相關量表）

**2026-10-19 進度**：成人問卷第一批為 HHIA-S＋SSQ12-TW，計分、分級、年齡推薦及每份問卷各保留一組比較的方向已確認；第二批 APHAB＋SADL，COSI 後續再做。規格見 [#76](https://github.com/minuet878-prog/HearWell/issues/76)，訪談與來源紀錄見 [questionnaire-comparison.md](planning/adult-assessment/questionnaire-comparison.md)。已依本人確認的拆法建立子議題 [#77–#84](https://github.com/minuet878-prog/HearWell/issues/76)，依賴與內容見 [拆票紀錄](planning/adult-assessment/ticket-plan-adult-assessment.md)。[#77 來源與使用條件定稿](https://github.com/minuet878-prog/HearWell/issues/77) 已依本人審定結案；[#78 HHIA-S 作答與結果](https://github.com/minuet878-prog/HearWell/issues/78) 已實作並通過 Django 571 項、前端 180 項與兩項 HHIA-S 瀏覽器測試，兩軸審查無發現，2026-10-19 本人人工驗收完成並結案；年齡推薦依本人指示留至 #80（[驗證紀錄](verification/issue-78.md)）；[#79 SSQ12-TW](https://github.com/minuet878-prog/HearWell/issues/79) 與 [#80 年齡及用途推薦](https://github.com/minuet878-prog/HearWell/issues/80) 已實作並通過 Django 584 項、前端 182 項、瀏覽器 21 項與完整 Ruff，審查補修已完成，2026-10-19 本人人工驗收完成並結案（[驗證紀錄](verification/issues-79-80.md)）；[#81 常模固定依據](https://github.com/minuet878-prog/HearWell/issues/81) 與 [#82 HHI 手選比較](https://github.com/minuet878-prog/HearWell/issues/82) 已實作，2026-10-20 本人人工驗收通過（[驗證紀錄](verification/issues-81-82.md)）；[#83 SSQ12 比較](https://github.com/minuet878-prog/HearWell/issues/83) 與 [#84 成人報告整合](https://github.com/minuet878-prog/HearWell/issues/84) 已實作，待本人人工驗收（[驗證紀錄](verification/issues-83-84.md)）；後續仍依原生阻擋關係推進。

2026-10-20 CI 後續：已重現並修復報告表格在較寬字型下的窄畫面溢出，本人／家屬同步補回歸；待推送後確認 CI，見[修復紀錄](verification/issues-83-84.md#ci-後續修復報告表格溢出2026-10-20)。

**構想**
除了 HHIE-S，未來想加入助聽器相關的標準化量表（IOI-HA、APHAB、COSI）跟耳鳴
相關問卷。

- [x] **IOI-HA 七題版**（規格 `docs/specs/phase-04/phase4_ioi_ha.md`，2026-10-15 完成）：用沒戴助聽器時的 HHIE-S 分組、逐題比常模、不算總分；
  題目逐字核對（驗收 23）與原量表授權（待決 12b）本人已於合併前確認
- [x] **我的紀錄依問卷分開**（規格 `docs/specs/phase-04/phase4_history_by_questionnaire.md`，2026-10-15 完成）：每份問卷一個分頁（各有網址）、HHIE-S 配戴前後差值與配戴狀態形狀、IOI-HA 常模圖；
  驗收 20 本人確認通過。已知限制：趨勢圖只讀 API 最新 20 筆

**跟現有架構的關係**
Questionnaire/Question/Answer 這套結構理論上可以重複使用（不同問卷、不同題目、
一樣的作答/計分流程），但幾個地方目前是寫死成 HHIE-S 專用，真的要加第二份問卷時
需要一起解決：

- 門檻表已經以 `Questionnaire.code` 分開（1-3），新問卷要在 `scoring.THRESHOLDS` 加一組
- 第一次要調整既有門檻時，先做規則版本號（Submission 記下當時的版本），見 1-5 的決定
- Category（emotional/social）是 HHIE-S 專屬的分類，其他問卷的分項可能完全不同
  （例如 APHAB 分 easy listening/background noise/reverberation/aversiveness，
  跟 HHIE-S 的兩分類邏輯不一樣）
- A1 年齡導引需要的「適用條件」，不同問卷可能不只是年齡
- 計分方式本身可能不同——HHIE-S 是簡單加總，其他量表不一定是同樣的計分邏輯

**先不要在這裡猜答案**——等真的要做第一份新問卷的時候，把這些寫死的地方一起
攤開來看，才會知道「通用機制」實際上要長什麼樣，不要在只有一份問卷的情況下
抽象設計。

---

## 待定：助聽器補助流程指引

**構想**
提供助聽器補助申請的流程說明/指引（例如政府補助資格、申請步驟）。

**性質**
比較接近內容型功能（跟 C2 衛教內容性質相近），不太涉及新的資料結構，
主要工作量在內容本身（補助規定會隨政策變動，需要有更新機制或至少標明
資料時效性）。

---

## 待定：問答小助手（免費版，不呼叫 AI API）

**構想**
讓使用者可以直接問問題，包含兩種性質不同的問題：
1. 操作性問題（「這個網站怎麼用」）
2. 臨床相關問題（「我這個分數代表什麼意思」「我該去看醫生嗎」）

**為什麼不用真的 AI（呼叫外部 API）**
AI API 是按使用量（token）計費的持續性成本，跟目前「免費方案、零成本」的階段
不符。而且不管操作性問題還是臨床問題，答案的範圍其實都是有限、自己列得出來的，
不需要「自由生成」這種能力。

**決定的方向：FAQ + 關鍵字比對，兩種問題都用同一套機制**
- 自己先準備一批「常見問題 + 審核過的固定答案」
- 使用者輸入問題，系統用關鍵字比對找到最相關的那一條，直接顯示預先寫好的答案
- 完全零成本，內容 100% 由自己審核掌控，不會有 AI「幻覺」出錯誤資訊的風險
- 代價：使用者用詞如果跟預先準備的關鍵字對不上，可能找不到答案

**跟其他功能的關係**
臨床相關問題的答案內容，可以直接沿用 A2（行動建議，已完成）的文字當起點。

**其他還沒想的事**
- 介面上要不要明確標示「這不是醫療診斷，請諮詢專業聽力師」這類免責聲明
- 如果未來想升級成 RAG，這批問答內容可以直接當作知識庫的起點

**為什麼現在先不做**
等累積更多審核過的建議文字之後再設計，會更有基礎。

---

## 聽力圖輸入（Phase 5）

**狀態**：第 1 批、第 2 批完成（2026-10-16，規格 `docs/specs/phase-05/phase5_audiogram.md`、`phase5_audiogram_2.md`）。趨勢折線圖、三張以上比較還沒做。下面是最初的構想，保留當紀錄。

**構想**
病人照著手上的聽力檢查報告，用點選的方式在網頁上重現聽力圖（不是填數字表單，
是真的在座標軸上點）。

**跟現有系統的關係**
完全獨立的功能，不掛在 Submission 底下，只跟 User 關聯。

**已經確認的規格**
- X 軸：固定頻率刻度（125/250/500/1000/2000/4000/8000 Hz，可能加 750/1500/3000/6000）
- Y 軸：固定 dB 刻度，不是自由點選
- 左耳/右耳、氣導/骨導都要涵蓋，右側按鈕切換目前要標記的符號
- 資料結構預期會是「一個 model 代表整次檢查（類似 Submission），另一個 model
  代表每個資料點（類似 Answer，欄位大概是耳朵/頻率/導程/dB 值）」，但還沒定案

**技術方向**
- 點擊輸入介面以 React 元件實作，細節在 Phase 5 規格中決定
- 判讀邏輯（自動判斷聽損程度/類型）用 rule-based 程式碼，不用 LLM；
  可參考獨立的聽力圖小工具已定案的臨床規則

**開發方式**
開獨立分支（例如 `feature/audiogram`），範圍大、開發期間會有一段時間是半成品，
不該影響 main 的穩定性。做完、測試過，再合併回 main。

---

## 待定：功能構想總表（2026-10-16 整理，尚未排入任何 phase）

上面已經有段落的項目（A1、C2、C3、新問卷、補助指引、問答小助手、聽力圖輸入、
C1、D2、React 作答頁）不在這裡重複；2026-10-16 排進 Phase 6／7 的項目已搬走。工作量：小／中／大。

### 追蹤與紀錄
- **情境日記**（中）：記錄在哪些情境聽不清楚。最初規劃的核心功能之一。
- **定期重測提醒**（中）：例如每半年提醒一次重新篩檢。email 或 PWA 推播
  （推播需要 service worker，跟 Phase 4「不用 service worker」的決定要一起重新評估）。

### 就醫與資源
- **就醫地圖**（中）：健保署「健保特約醫事機構」開放資料（每日更新、有 OAS 文件），
  依縣市、診療科別列出耳鼻喉科。定期抓回存進自己的資料庫，不要每次請求即時呼叫；
  重抓要冪等（更新既有資料，不重複新增）。
  - 限制：有耳鼻喉科不代表有聽力師或完整聽檢，文案不能寫成「可做聽力檢查的地方」
- **身障鑑定醫院、輔具中心查詢**（中）：全國名冊沒有鑑定類別，有類別的是各縣市版本、
  格式不一；輔具中心只有附檔，數量少，可手動整理成 fixture。跟「補助流程指引」相關。

### 衛教與 AI
- **問答小助手 RAG 版**（大）：知識庫只用本人審核過的內容；回答附來源段落；
  超出範圍要拒答；要有 eval 驗證正確性。LLM 只負責語言輸出，不做分級或計分。
- **助聽器相關內容**（小～中）

### 聽力檢測與聽力圖
- **聽力圖照片辨識 → 判讀 → 衛教**（大）：先只做北榮固定格式的報告；手動輸入當備援。
- **數字噪音測驗**（digits-in-noise）（大）：有文獻驗證的遠端篩檢，對耳機校正的要求比純音低。
- **純音自我篩檢**（大）：耳機與音量無法校正，結果可信度有限，可能涉及醫療器材法規。先查法規再說。
- **環境噪音分貝計**（中）：手機麥克風未校正，只能當參考值，用於噪音防護衛教。
- **聽損／助聽器模擬**（大）：讓家屬體驗聽損者聽到的聲音。

### 家屬與臨床端
- **臨床端檢視**（大）：病人同意後，聽力師可看篩檢紀錄。核心難點是權限與同意機制。
- **台語語音轉寫給臨床人員**（大）：病人台語主訴轉中文紀錄（例如 Breeze-ASR-26）。

### 無障礙與語言
- **台語語音問卷**（大）：唸題目、語音作答；答案是固定選項，辨識難度較低。
  要處理：戴耳機、放慢語速、大按鈕。
- **題目朗讀**（TTS）（小～中）：先做國語版，可當台語版的前導。
- **字級切換按鈕**（小）
- 無障礙基準線量到沒修的項目，見 Phase 6。

### 帳號、隱私與法規
- 同意書、資料匯出、帳號與資料刪除 → Phase 7
- **上架原生 app**（大）：需要加上 token 驗證（見「兩個已定案的方向」第 2 點）。

### 工程面（使用者看不到，但對作品集有分量）

- [x] **面試筆記分類整理**（2026-10-19）：本機筆記改為 `docs/interview/`，按主題與開發 Phase 拆檔，保留題號索引與原 `docs/interview.md` 入口；延續不進版控。
- [x] **歷史規格與審查整理**（2026-10-19）：44 份規格（含模板）與 51 份審查依 Phase 歸檔，新增[規格索引](specs/README.md)與[審查索引](reviews/README.md)，修正文件及註解引用；原內容與結論保留。
- [x] **其餘文件分類與總覽**（2026-10-19）：新增[文件入口](README.md)，成人問卷研究歸入 `planning/adult-assessment/`、量測紀錄歸入 `accessibility/`、私有部署筆記歸入 `deployment/`；補齊既有目錄索引，更新引用並保留私有筆記忽略設定。
- CI、錯誤監控、端對端測試 → Phase 6
- **分數快取或改存欄位**（中）：目前每次即時計算；使用者大量增加時的優化，要先想清楚
  快取何時失效（`_scores_cache` 已經有不會失效的坑）。
- **匿名統計後台**（中）：不辨識個人，看整體分數分布。
- Docker 化與 VPS 部署：另一個學習專案在進行，見該專案紀錄。
