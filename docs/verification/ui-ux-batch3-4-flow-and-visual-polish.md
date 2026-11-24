# UI/UX Design Review 第三批與第四批：動線流暢度、認知負荷與視覺細節

日期：2026-11-24。工作目錄：`ui_ux_design_review` worktree。依據：[UI/UX Design Review 第三批與第四批拷問決定](../planning/redesign/ui-ux-batch3-4-grill-decisions.md)。

狀態：本人實際操作驗收通過（2026-11-24）。

- **不需交叉審查**：本批改動僅涉及前端互動、畫面提示、無障礙報讀與 CSS 樣式細節，未觸及計分或分級邏輯、門檻、資料庫 migration 或權限檢查。
- 沒有操作真實資料。測試均在臨時測試資料庫上執行。

## 行為與驗收對照

勾選代表自動測試已驗證，不代替本人實際操作確認。

### 第三批：動線流暢度、認知負荷與互動打磨（C1–C9）

| # | 項目與驗收條件 | 驗證 | 證據 |
|---|---|---|---|
| **C1** | **聽力圖輸入第 1 步即時驗證**：在第 1 步按「下一步：標右耳」時即驗證來源與日期（未選來源、未填日期、無效日期、未來日期），有錯時留在第 1 步、顯示 `role="alert"` 錯誤訊息，且三個日期欄位標上 `aria-invalid="true"` | ✅ 自動 | `frontend/src/AudiogramApp.test.jsx`（第 1 步驗證與 `aria-invalid` 斷言） |
| **C1** | **「改好了，回確認存檔」捷徑**：曾到達第 4 步（確認存檔）後，點「改哪一種／改日期／改右耳／改左耳」跳回第 1–3 步時，顯示次要按鈕「改好了，回確認存檔」直達第 4 步；若在第 1 步把日期改壞，按捷徑同樣會先攔截驗證 | ✅ 自動 | `frontend/src/AudiogramApp.test.jsx`（捷徑顯示與跳轉斷言） |
| **C1** | **刪除點位語音報讀**：點圖上既有記號、按「清除 ○○」按鈕或從數值表下拉選單改回空白時，`[role="status"]` 報讀「已清除 `<耳別><傳導> <頻率> Hz`」 | ✅ 自動 | `frontend/src/AudiogramApp.test.jsx`（三種刪除途徑報讀斷言） |
| **C2** | **分級結果頁回看歷史顯示日期與配戴狀態**：從歷史紀錄重開 `HHIE-S`、`HHIA-S`、`THI` 結果頁（`not just_saved and not result.is_guest`）時，`.result-banner` 頂部顯示 `YYYY/MM/DD・沒戴助聽器`（未填配戴狀態則只顯示日期）；剛送出、訪客結果與非分級問卷不顯示 | ✅ 自動 | `screening/tests/test_result_pages_redesign.py` |
| **C3** | **語言香蕉區清單選取捲回圖表、耳別高亮與報讀、圖說補充**：「用清單選」點選任一群後平滑捲回 `.audiogram-chart`（尊重 `prefers-reduced-motion`）；選中耳別按鈕為深藍底白字（`var(--color-primary)` / `#fff`），切換耳別時 `aria-live="polite"` 報讀「已切換到右耳／左耳」；圖說首句加上「紅線（右耳）或藍線（左耳）是您的聽力圖。」 | ✅ 自動 | `frontend/src/SpeechBananaApp.test.jsx`；`e2e/main_flow.py` (`SpeechBananaListTest`, `SpeechBananaEarTest`) |
| **C4** | **趨勢圖數字白邊、資料點高亮與錯誤訊息 `role="status"`**：`.trend-score` 加上白色描邊（`paintOrder="stroke"`、`stroke="#fff"`、`strokeWidth={4}`）；`<Line>` 開啟 `activeDot` 繪製放大圓點與外圈光暈（`.trend-dot-halo` + `.trend-dot-active`）；載入失敗訊息加上 `role="status"` | ✅ 自動 | `frontend/src/TrendChart.test.jsx` |
| **C5** | **健康報告「全部展開／全部收合」按鈕**：個人報告 `/report` 與分享報告 `/shared/<token>` 在 `.report-rows` 頂部提供 `#report-fold-toggle` 次要按鈕，一鍵展開或收合所有頂層 `.report-fold`（不動內層 `.report-answers`），並同步更新按鈕文字與 `aria-expanded` | ✅ 自動 | `screening/tests/test_report_redesign.py` |
| **C6** | **意見回饋頁首屏精簡與即時字數提示**：移除「您是從○○過來的」（後端照舊記錄 `page`）；匿名提示改為表單上方單行次要文字「內容匿名保存 90 天」；緊急就醫提醒移至送出按鈕下方；輸入框下方提供即時字數提示 `已輸入 N / 1,000 字`（停打 1 秒後更新 `role="status"`，打字時隱藏靜態 `最多 1,000 字`） | ✅ 自動 | `screening/tests/test_feedback.py`；`screening/tests/test_about.py`；`frontend/src/password-count.test.js` |
| **C7** | **輪播卡片（card-stack）切卡報讀新標題與非首張卡 `inert`**：切換卡片時 `.card-stack-position` 內附加 `.visually-hidden` 的 `：<卡片標題>` 讓螢幕閱讀器連同張數一起唸出；`questionnaire.html` 非首張卡在伺服器輸出時即帶 `inert`；`learn.html` 維持無額外 `<h2>` | ✅ 自動 | `frontend/src/card-stack.test.js`；`screening/tests/test_card_stack.py`；`e2e/main_flow.py` (`LearnStackT754Test`) |
| **C8** | **觸控 `:hover` 防殘留與底部分頁列防抖動**：`a:hover`、`.btn:hover`、`.btn-link:hover`、`.site-nav a:hover`、`.site-footer-links a:hover` 包入 `@media (hover: hover)`，且 `.btn:hover` 與 `.btn:focus-visible` 拆開；`tab-bar.js` 加入 `14px` 捲動門檻避免微幅回彈抖動 | ✅ 自動 | `frontend/src/tab-bar.test.js`；`e2e/main_flow.py` (`StyleInBrowserTest`) |
| **C9** | **跨頁用語與語意修正**：`account.html` 統一稱呼 `email`（含 `aria-label="補上 email"`）；`SimulatorApp.jsx` 句子顯示區補上 `aria-live="polite"`；`AnswerApp.jsx` 接續作答標題由 `<h3>` 改為 `<h2>`；訪客首頁主按鈕維持「開始」 | ✅ 自動 | `screening/tests/test_account_login_pages.py`；`screening/tests/test_account_settings.py`；`frontend/src/SimulatorApp.test.jsx`；`frontend/src/AnswerApp.test.jsx` |

### 第四批：視覺質感、細節精修與程式整潔（D1–D4）

| # | 項目與驗收條件 | 驗證 | 證據 |
|---|---|---|---|
| **D1** | **等寬數字對齊（`tabular-nums`）**：為 `.table`、`.audiogram-reading-value`、`.result-number`、`.gauge-score`、`.result-bar-value`、`.journey-tile-score`、`.countdown-gauge-number`、`.question-number`、`.password-count`、`.feedback-count`、`.score-chip` 補上 `font-variant-numeric: tabular-nums` | ✅ 自動 | `frontend/src/styles/` 各模組檔；`npm run build --prefix frontend` |
| **D2** | **同心圓角精算與 `--radius-*` token 收斂**：`.site-account-item` 內圓角設為 `calc(var(--radius-badge) - 0.375rem)`；`.records-switch a`、`.ear-switch :is(a, button)`、`.simulator-switch button` 內圓角設為 `calc(var(--radius-tab) - 0.25rem)`；各樣式檔散落的硬編碼圓角收斂為 `--radius-*` token | ✅ 自動 | `frontend/src/styles/` 各模組檔；`e2e/main_flow.py` (`StyleInBrowserTest`) |
| **D3** | **中文標題平衡斷行與頁尾微調**：`h1–h4` 與 `.h1–.h4` 補上 `text-wrap: balance`；有「回到頂端」按鈕時 `.site-footer` 底部預留空間由 `44px` 改為 `var(--spacing-button)`（`56px`）；手機版 `.site-footer-links` 間距放寬為 `0.5rem` | ✅ 自動 | `frontend/src/styles/base.css`、`shell.css`；`e2e/main_flow.py` (`StyleInBrowserTest`) |
| **D4** | **共用腳本小邊界修正**：`in-view.js` 在無待播動畫頁面初次 `check()` 即 `disconnect()` `ResizeObserver`；`scroll-hint.js` 為 `.scroll-box` 關聯 `aria-describedby="scroll-hint-N"`；`switch-slide.js` 點擊當前分頁（`aria-current`）時不將 `switching` 設為 `true` | ✅ 自動 | `frontend/src/in-view.test.js`；`frontend/src/scroll-hint.test.js`；`frontend/src/switch-slide.test.js` |

## 測試結果

- 前端建置 `npm run build --prefix frontend`：成功（`site.css` 366.65 kB，各 entry 均在預算內）。
- 前端單元測試 `npm test --prefix frontend`：47 個測試檔、**802 項測試全過**。
- 後端單元測試 `python manage.py test --settings=config.test_settings --parallel`：**3293 項測試全過**（skipped=1）。
- 端對端瀏覽器測試 `e2e.main_flow`（`StyleInBrowserTest`、`SpeechBananaListTest`、`SpeechBananaEarTest`、`LearnStackT754Test`）：**74 項全過**。
- 程式碼風格與格式檢查 `ruff check .`、`ruff format --check .`：**全過**。

## 人工驗收清單

請在瀏覽器（建議用手機寬度 390×844，若看到舊樣式請按 `Cmd + Shift + R` 重新整理）確認以下動線：

1. **聽力圖輸入（`/audiograms/new`）**：
   - 第 1 步不填直接按「下一步：標右耳」，應立刻顯示紅框錯誤提示並留在第 1 步。
   - 填好走完到第 4 步「確認存檔」，點「改右耳」回到第 2 步，下方應出現「改好了，回確認存檔」按鈕，點了直接回第 4 步。
2. **歷史結果頁（`/my_hearing` → 點開任一筆過去的 HHIE-S / HHIA-S / THI 紀錄）**：
   - 分數色塊上方內側應有一行小字顯示 `YYYY/MM/DD・沒戴助聽器`（或 `有戴助聽器`）。
3. **語言香蕉區（`/audiograms/<id>/speech-banana`）**：
   - 左右耳切換鈕選中時為深藍底白字；圖說開頭有「紅線（右耳）或藍線（左耳）是您的聽力圖。」；展開下方「用清單選」點任一注音群，畫面會自動捲回上方圖表與結果框。
4. **趨勢圖（`/my_hearing`）**：
   - 折線上的分數數字有白邊不與右側分級字重疊；手指或滑鼠移到資料點上有放大外圈高亮。
5. **健康報告（`/report`）**：
   - 紀錄區塊上方有「全部展開」按鈕，點一下全部展開並變成「全部收合」，再點一下全部收起。
6. **意見回饋（`/feedback`）**：
   - 手機第一個畫面即可看到輸入框（上方僅留小鳥對話與一行淡字「內容匿名保存 90 天」，緊急就醫框移到送出按鈕下方）；打字時輸入框下方即時顯示 `已輸入 N / 1,000 字`。
7. **帳號設定（`/account`）**：
   - Email 列標籤與按鈕已統一為 `email`。
