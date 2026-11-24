# UI/UX Design Review 第三＋第四批　拷問決定（2026-11-24）

[回功能規劃](../README.md)

- 日期：2026-11-24，本人逐題點選定案。
- 範圍：接續第一、二批（無障礙底線、舊框架清理與高齡防錯修復），完成第三批「動線流暢度、認知負荷與互動打磨（C1–C9）」與第四批「視覺質感、細節精修與程式整潔（D1–D4）」。
- 流程：不另開 GitHub issue，記錄決定後直接於分支以 TDD 實作並撰寫驗證紀錄（不碰計分、分級、門檻、migration 或存取權限，不需交叉審查）。

---

## 第三批：動線流暢度、認知負荷與互動打磨

| # | 題目 | 決定 |
|---|---|---|
| C1 | 聽力圖輸入第 1 步即時驗證、回確認存檔捷徑與刪點朗讀 | ① **第 1 步即時驗證**：在第 1 步按「下一步：標右耳」（或回確認存檔捷徑）時，先檢查是否已選來源（`請選擇這是哪一種`）與是否填寫有效且非未來的檢查日期（`請填寫檢查日期`／`檢查日期不對，請照報告再填一次`／`檢查日期不能是未來`），有錯即留在第 1 步顯示錯誤框，並為出錯的日期輸入框加上 `aria-invalid="true"`；第 2、3 步不擋點位數量，維持在第 4 步按「存檔」時才檢查「請至少標記一個點」。<br>② **回確認存檔捷徑**：只要曾到達過第 4 步（確認存檔），從第 4 步點「改哪一種／改日期／改右耳／改左耳」跳回第 1～3 步時，提供「改好了，回確認存檔」按鈕（若在第 1 步按此按鈕，同樣先通過第 1 步來源與日期驗證才跳回第 4 步）。<br>③ **刪除點位讀螢幕朗讀**：三種刪點途徑（圖上同位置再點一下刪點、按「清除 ○○」按鈕、數值輸入表下拉改回「未標記」）一律將 `screenReaderText` 設為 `已清除 <耳別><傳導> <頻率> Hz`（例如 `已清除 右耳氣導 1000 Hz`）。 |
| C2 | 分級結果頁回看歷史紀錄顯示作答日期與配戴狀態 | 只在**分級問卷（HHIE-S、HHIA-S、THI）的結果頁**、且為**回看歷史紀錄（`not just_saved` 且非訪客結果 `not submission.result.is_guest`）**時，在彩色分數框（`.result-banner`）內最上方以單行次要文字顯示 `YYYY/MM/DD・沒戴助聽器` 或 `YYYY/MM/DD・有戴助聽器`（若配戴狀態為未記錄 `None`，則只顯示 `YYYY/MM/DD`）。剛送出（`just_saved`）、訪客結果頁與其他三種結果頁（SSQ12、IOI-HA、SADL）維持原樣不加。 |
| C3 | 語言香蕉區「用清單選」捲動、切耳高亮與朗讀、圖說補強 | ① 點下方「用清單選」的注音群按鈕後，畫面捲回聽力圖容器頂端（`.audiogram-chart`，開啟 `prefers-reduced-motion: reduce` 時用 `behavior: "instant"`，一般用 `"smooth"`）。<br>② 左右耳切換（`.ear-switch`）選中狀態改為實心深藍底白字（對齊全站新版切換器視覺），切換左右耳時透過 `role="status"` 區域報讀 `已切換到右耳`／`已切換到左耳`。<br>③ 圖說補上紅／藍線說明：`紅線（右耳）或藍線（左耳）是您的聽力圖。黃色是語言香蕉區，是說話聲通常落在的範圍。斜線蓋住的部分和虛線框的注音，這一耳沒戴助聽器時可能不容易聽到。` |
| C4 | 趨勢圖分數數字防重疊、點選高亮與載入失敗報讀 | ① `.trend-score` 加上白色外描邊（`paintOrder: "stroke"`, `stroke: "#fff"`, `strokeWidth: 4`, `strokeLinejoin: "round"`），避免分數點落在右側時與色帶右上角的分級簡稱重疊。<br>② `Line` 開啟 `activeDot`，在觸控／游標指到資料點時以放大外圈高亮該點（保留圓形／方形／三角形區分）。<br>③ 載入失敗訊息 `<p>` 補上 `role="status"`（且錯誤狀態下外層不標 `aria-hidden="true"`）。 |
| C5 | 健康報告螢幕版「全部展開／全部收合」按鈕 | 在本人聽力報告頁（`/report`）與家人分享報告頁（`/shared/<token>`）的「列印或存成 PDF」按鈕下方（報告摺疊區上方），新增一顆次要按鈕（`.btn-outline-primary`）「全部展開」，點擊後展開所有頂層 `.report-fold` 並將按鈕文字切換為「全部收合」（不展開內層的「最近一次逐題回答」子摺疊，若使用者手動點開／收合全部 `.report-fold` 時按鈕文字亦同步更新）。 |
| C6 | 意見回饋頁表單前提示精簡、急症框下移與即時字數提示 | ① 畫面上**刪除**「您是從『○○』過來的。」提示框（後端仍照常記錄來源頁種類到資料庫）。<br>② 匿名保存提示改為淡字（次要文字 `text-(--color-muted)`）放在小鳥對話與表單輸入框中間，文字精簡為：`內容匿名保存 90 天`。<br>③ 紅底急症就醫框（`urgent_box.html`）移到表單「送出」按鈕下方，讓手機首屏直接看到留言輸入框。<br>④ 留言輸入框下方在有打字時動態顯示 `已輸入 N / 2,000 字`（套用 `tabular-nums`，停止打字 1 秒後更新 `role="status"` 供讀螢幕報讀；未打字或無 JS 時維持顯示 `最多 2,000 字`）。 |
| C7 | 輪播卡片（`card-stack`）切卡報讀新標題與初始 `inert` | ① `card-stack.js` 切換卡片時，將 `.card-stack-position`（`aria-live="polite"`）文字更新為 `第 N 張，共 M 張：<卡片標題>`（畫面上若只顯示張數或連同標題，確保 `aria-live` 同步報讀新卡片標題）。<br>② `questionnaire.html` 的非首張輪播卡在 HTML 初始補上 `inert`（與 `learn.html` 一致）。<br>③ `learn.html` 下方白卡清單維持 `#469` 決定的無標題清單，不另加 `<h2>` 小標。 |
| C8 | 觸控 `:hover` 殘留防護與底部分頁列防抖動 | ① 將 `base.css` 與 `shell.css` 中未包進 `@media (hover: hover)` 的 `:hover` 規則（`a:hover`、`.btn:hover`、`.btn-link:hover`、`.site-nav a:hover`、`.site-footer-links a:hover`）統一包進 `@media (hover: hover)`，並將 `.btn:hover` 與 `.btn:focus-visible` 拆開（`:focus-visible` 只顯示焦點環、不變換 hover 底色）。<br>② `tab-bar.js` 加入 `14px` 捲動距離門檻（`Math.abs(y - lastY) >= 14` 才切換 `data-hidden` 并更新 `lastY`；頂端與底端 `mustShow(y)` 仍立即顯示）。 |
| C9 | 跨頁用語統一、模擬器句子切換報讀與作答頁標題層級 | ① `account.html` 上方「我的帳號」區塊的「電子郵件」改為「email」（補上按鈕 `aria-label` 改為 `補上 email`），與同頁下方的「email 重測提醒」「補上 email」完全一致；其餘頁面維持既有「email／信箱」自然分工。<br>② `SimulatorApp.jsx` 的句子編號與聲別（`.simulator-caption`）補上 `aria-live="polite"`。<br>③ `AnswerApp.jsx` 的「您上次答到第 N 題，要接著答嗎？」從 `<h3 className="h4 ...">` 改為 `<h2 className="h4 ...">`，避免頁面 `<h1>` 下直接跳 `<h3>`。<br>④ 訪客首頁藍色大卡主按鈕維持 `#741` 定稿的「開始 ›」不動。 |

---

## 第四批：視覺質感、細節精修與程式整潔

| # | 題目 | 決定 |
|---|---|---|
| D1 | 等寬數字對齊（`font-variant-numeric: tabular-nums`） | 為 `.table`、`.audiogram-reading-value`、`.result-number`、`.gauge-score`、`.question-number`、`.password-count`、`.feedback-count`，以及首頁與紀錄頁的分數／天數（`.journey-tile-score`、`.countdown-number`、`.score-chip`、`.result-bar-value`）統一加上 `font-variant-numeric: tabular-nums`。 |
| D2 | 同心圓角精算與 `--radius-*` 收斂 | ① 修正有內距容器的內層同心圓角：`.site-account-item` 改為 `calc(var(--radius-badge) - 0.375rem)`（`0.625rem`）；`.records-switch a`、`.ear-switch :is(a, button)`、`.simulator-switch button` 改為 `calc(var(--radius-tab) - 0.25rem)`（`1.25rem`）。<br>② 收斂散落的硬編碼圓角至既有 `--radius-*` token（例如 `0.75rem` → `var(--radius-medium)`、`1rem` → `var(--radius-badge)` 等；保留列印小卡 `2mm`、頁尾拱門半圓與小鳥鵝卵石不對稱圓角）。 |
| D3 | 中文標題平衡斷行（`text-wrap: balance`）與頁尾微調 | ① 在 `base.css` 為 `h1`–`h4` 與 `.h1`–`.h4` 統一補上 `text-wrap: balance`。<br>② `shell.css` 中有 `.back-to-top` 時頁尾底部預留高度從 `var(--spacing-touch)`（44px）改為 `var(--spacing-button)`（56px），完全避開 56px 高的「回到頂端」按鈕。<br>③ 手機版 `.site-footer-links` 的 `gap` 從 `0.25rem` 放寬為 `0.5rem`（並調整 `li` 的 `flex-basis` 為 `calc((100% - 1rem) / 3)`，確保 320px 手機仍維持最多三格一排不擠壓）。 |
| D4 | 共用腳本小邊界與死樣式確認 | ① `in-view.js`：先建立 `ResizeObserver` 再執行首次 `check()`（若無待播元素則在首次 `check()` 即 `disconnect()`，或僅在 `waiting.length > 0` 時 `observe`）。<br>② `scroll-hint.js`：為每個產生的 `.scroll-hint` 賦予唯一 `id`（如 `scroll-hint-1`），並在對應 `.scroll-box` 補上 `aria-describedby`。<br>③ `switch-slide.js`：點擊帶有 `aria-current="page"`（或 `aria-current="true"`）的當前分頁連結時，`switching` 設為 `false`。<br>④ 死樣式清理與 `site.css` 拆分已在 PR #764（ADR 0080）完成，直接標記完成。 |
