# UI/UX 無障礙底線、舊框架清理與高齡防錯修復（無 issue）

日期：2026-11-23。基準：`e5a90336`（main）；分支：`improve_ui_ux`。

狀態：本人實際操作驗收通過（2026-11-23）。

- 不需交叉審查：未更動計分、分級、門檻、migration 或存取權限（只調整前端樣式／互動腳本、模板結構與 `RegisterForm` 驗證失敗時的 `autofocus` 屬性）。
- 未操作真實資料。自動化測試均在臨時測試資料庫上執行。

## 改動項目

### 第一批：無障礙底線與舊框架清理

| 項目 | 改動內容 |
|---|---|
| 清理殘留 Bootstrap 樣式與補齊 `.form-select-lg` | 移除 `site.css` 殘留的 Bootstrap 藍（`#0d6efd`、`#86b7fe`、`rgba(13, 110, 253, ...)`、`rgba(49, 132, 253, ...)`），統一改用 `--color-primary` 與 `--color-muted`；`.alert-warning`／`.alert-danger` 對齊 `--color-mild*`／`--color-severe*`、`--radius-medium` 並加上警告圖示；補定義 `.form-select-lg`。 |
| 全站鍵盤焦點與系統高對比模式相容 | 於 `@layer base` 建立統一 3px 高對比 `:focus-visible` 外框（深藍大卡內使用白色外框，並排除 skip-link 落腳的 `main[tabindex="-1"]` 避免整個頁面主區亮框），拆開 `.btn:hover` 與 `.btn:focus-visible` 且保留實色 `outline` 以相容 Windows 高對比模式。 |
| 鍵盤焦點防遮擋（WCAG 2.4.11） | `<main>` 內可聚焦元素加上 `scroll-margin-top`（避開浮動頁首）與手機版 `scroll-margin-bottom`（避開底部分頁列）。 |
| 頭像選單鍵盤關閉與無障礙名稱 | `site-header.js` 補上 `focusout` 監聽，Tab 離開選單自動收合且不搶回焦點；`layout.html` 展開選單按鈕的 `aria-label` 改為 `帳號選單：{{ user.username }}`。 |
| 44×44px 觸控目標補齊 | `.form-control`／`.form-select`、`.form-check`（搭配 1.5rem 核取方塊）與頁尾 `mailto:` 連結補上 `min-height: var(--spacing-touch)`。 |
| 健康報告摺疊列不嵌套 `<h2>` | `report_content.html` 與 `report_graded_fold.html` 的 `<summary>` 內改用 `<span class="report-fold-title">`，展開區內的真實 `<h2>`/`<h3>` 螢幕版改為視覺隱藏（保留讀螢幕標題大綱，列印維持顯示）。 |
| 註冊錯誤聚焦與第三方登入錯誤聚焦 | `RegisterForm` 無條件移除預設 `username` 的 `autofocus`，改由 `add_error` 動態將 `autofocus` 設在畫面順序第一個出錯欄位；`login.html`／`register.html` 的 `sign_in_error` 紅框加上 `tabindex="-1" autofocus`。 |

### 第二批：高齡防錯與關鍵互動修復

| 項目 | 改動內容 |
|---|---|
| 防誤觸離開保護 | `AudiogramApp.jsx` 有未存檔變更時加入 `beforeunload` 與離開連結確認提示；`AnswerApp.jsx` 訪客模式已作答未送出時加入 `beforeunload` 與 `.site-leave` 點擊確認。 |
| 聽損模擬器音訊狀態與正常聽視覺區分 | `simulator-engine.js` 檢查 HTTP 失敗並提供 `onReady`／`onError` 回呼；`SimulatorApp.jsx` 顯示「聲音載入中…」與載入失敗紅字提示；切換「正常聽」時於 `.simulator-chips` 標記 `data-inactive` 弱化程度按鈕選中樣式。 |
| 作答頁缺選提示位置與 SSQ12 滑桿 | `AnswerApp.jsx` 將「請先選一個答案」移至 `<fieldset>` 內題目正下方並串接 `aria-describedby`；SSQ12 滑桿未作答時支援鍵盤 Enter／空白鍵直接選 5 分，選「不適用」時標記 `data-na="true"` 淡化滑桿。 |
| 聽力圖放大鏡定位修正 | `AudiogramChart.jsx` 放大鏡 `top` 計入 `-20 dB` 的 `rise` 偏移，並對左右邊緣頻率（≤500 Hz／≥4000 Hz）加上 `data-edge` 往內對齊避免裁切。 |
| iPhone PWA 下拉重整保護 | `.pwa-pull` 補上 `env(safe-area-inset-top)`；`pwa-nav.js` 加上 16px 起拉顯示門檻與橫滑取消判斷。 |
| 送出中按鈕防呆與深藍卡連結按下對比 | `page-loading.js` 防範 `event.submitter` 為空與 `href="#"` 誤觸、維持 `.btn-primary.is-sending:disabled` 深藍底白字，逾時還原時若焦點落回 `body` 則歸還給按鈕；`site.css` 修正 `.hero-card a:not(.btn):active` 改用半透明白底避免白字消失。 |

## 測試結果

- 後端完整測試（PostgreSQL）`python manage.py test --settings=config.test_settings --parallel`：3,292 項全過（skipped=1）。
- 前端測試 `npm test --prefix frontend`：47 個測試檔、811 項測試全過。
- 端對端測試（受影響類別）`python manage.py test --settings=config.test_settings --parallel 4 ...`：20 項全過（含 `StyleInBrowserTest`、`SiteHeaderTest`、`WhiteCardRuleTest`、`JumpHighlightTest`、`NewUserScreeningTest`、`GuestSaveWithLineTest`、`GuestSaveWithGoogleTest`）。
- 前端建置 `npm run build --prefix frontend`：建置成功。
- 格式與靜態檢查：`ruff check .` 與 `ruff format --check .`（739 檔）全過。

## 改了的既有測試（配合無障礙結構與位置調整）

- `screening/tests/test_site_header.py`、`frontend/src/site-header.test.js`、`e2e/main_flow.py`（5 處按鈕）：頭像選單按鈕 `aria-label` 更新為 `帳號選單：<username>`（無 JS 連結仍為 `帳號設定：<username>`）。
- `screening/tests/test_report.py`、`screening/tests/test_report_redesign.py`、`screening/tests/test_report_parts.py`、`e2e/main_flow.py`（`WhiteCardRuleTest`）：配合 `<summary>` 不再嵌套 `<h2>`，改以 `.report-fold-title` 比對並更新大綱層級斷言（`h2` 分區 → `h3` 內容）。
- `e2e/main_flow.py`（`StyleInBrowserTest`）：更新原鎖定舊 Bootstrap 色與 42.5px 高度之斷言，改驗證全站 `--color-mild`／`--color-severe`／`--color-muted`、`--color-primary` 焦點／勾選色與 49.5px（`2.75rem`）觸控高度。
- `frontend/src/AnswerApp.test.jsx`（2 處 `#326 C5`）：配合「請先選一個答案」移進 `<fieldset>` 緊接題目下方，更新位置斷言。

## 人工驗收

2026-11-23 本人於 `http://127.0.0.1:8001/` 實際操作驗收完成。
