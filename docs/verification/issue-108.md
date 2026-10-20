# #108：整站共用 UI token 更新（字體／圓角／陰影／間距）

日期：2026-10-20。規格：[#108](https://github.com/minuet878-prog/HearWell/issues/108)。基準：`b06ac9b`（main）；功能分支：`design/ui-refresh`；commit：`1bd96d9`。

狀態：自動測試與自審（Standards／Spec）已通過，**等本人人工驗收**。未操作真實資料或本機常駐服務；本機開發伺服器（埠 8001）由本次對話自行啟動並停止，過程中建立的測試帳號（`ui_refresh_preview`）已在驗證結束後刪除。本次不需 migration。

## 行為

- 全站本文與標題字體改用 Noto Sans TC（Google Fonts CDN，`layout.html` 新增 `<link>`），透過 Bootstrap 的 `--bs-body-font-family` 變數套用，CDN 連不上時 fallback 回系統字型。
- 以下共用 class 的圓角／陰影／間距數值微調，不改 HTML 結構、不改主色、不改觸控目標尺寸：
  - `.btn`：圓角改用 `--bs-btn-border-radius: 0.5rem`（原跟隨 Bootstrap 全域預設）。
  - `.link-card`：圓角 0.5rem → 0.75rem，padding 1rem → 1.1rem，新增淡陰影 `box-shadow: 0 0.125rem 0.375rem rgba(15, 23, 42, 0.08)`。
  - `.trend-summary`：padding 1rem 1.25rem → 1.25rem 1.5rem，圓角 0.5rem → 0.75rem。
  - `.home-band`：圓角 1rem → 1.25rem，padding 1.25rem → 1.5rem。
  - `.questionnaire-guide`：padding 0.5rem 1rem → 0.75rem 1.25rem，圓角 0.5rem → 0.75rem。
  - `.account-details`：欄位間距 `gap` 0.5rem 1rem → 0.625rem 1.25rem。
- `@media print` 新增 `.health-report * { box-shadow: none !important; }`，避免列印頁出現新陰影。
- `docs/accessibility/accessibility_baseline.md` 的「歷次量測」表格新增一列，記錄字體選用理由與「主色/對比色/觸控目標未變動，沒有重新量 axe 對比」。

## 驗收對照

勾選代表自動驗證或本次對話的人工檢查，不代替本人操作確認。

| 驗收條件（#108） | 驗證 | 證據 |
|---|---|---|
| 本文與標題文字使用 Noto Sans TC | ✅ 人工（DevTools） | 開發伺服器上 `getComputedStyle(document.body).fontFamily` 與 `getComputedStyle(h1).fontFamily` 皆回傳含 `"Noto Sans TC"` 的字型堆疊；Google Fonts `document.fonts` 顯示對應字重已 `loaded` |
| CDN 連不上時 fallback 回系統字型，不影響操作 | ⚠️ 未實測 | 設計上依賴瀏覽器字型堆疊 fallback 的原生行為（CSS 層級保證），本次沒有模擬斷網或封鎖字型網域；建議人工驗收時用瀏覽器封鎖 `fonts.googleapis.com` 後重新整理一次確認 |
| 共用 class 圓角／陰影／間距以外的屬性（主色、對比色、觸控目標 44×44px）不變 | ✅ 自動＋人工 | diff 只改 `padding`／`border-radius`／`box-shadow`／`gap`，未動任何色彩或 `min-height`／`min-width`；`screening.tests.test_pages`（含 `AccessibilityTests`）68 項全過；瀏覽器截圖確認按鈕與卡片視覺可點擊區域未縮小 |
| `styles.css` 色彩變數（`--bs-primary` 等）完全不變 | ✅ 自動 | `test_body_and_muted_text_color` 等既有色彩斷言測試通過；diff 本身沒有色彩變數的增刪改 |
| `.health-report` 列印頁不出現新陰影 | ✅ 自動（規則存在）／⚠️ 未實際列印 | 新增 `.health-report * { box-shadow: none !important; }`；本次沒有實際開啟瀏覽器列印預覽核對，建議人工驗收時用「列印或存成 PDF」確認 |
| React 渲染頁面共用同一份 `styles.css`，`frontend/` 不用改 | ✅ 自動 | `frontend/src` 內沒有任何 `.css` 檔（`find` 確認），本次未改動 `frontend/` 任何檔案 |
| `docs/accessibility/accessibility_baseline.md` 補充字體理由與微調說明 | ✅ | 「歷次量測」表格新增 2026-10-20 一列 |

## 測試與審查

- `py313/bin/python manage.py test --settings=config.test_settings`：612 項全過（31.4 秒，本機 PostgreSQL）。
- `py313/bin/python -m ruff check .`：全過。
- 前端（`npm test --prefix frontend`）、端對端（`e2e.main_flow`）：本次沒有改動 `frontend/` 或既有頁面結構，沒有重新跑；建議人工驗收時可省略，除非想確認列印／字體在真實瀏覽器下的觀感。
- 人工瀏覽器檢查（本次對話執行）：啟動 `.claude/launch.json` 的 `hearwell`（埠 8001）開發伺服器，註冊測試帳號後檢視首頁、問卷列表、帳號設定頁，確認圓角／陰影／字體套用、版面沒有跑掉；驗證後刪除測試帳號、停掉伺服器。
- 自審（`/mattpocock-skills:code-review`，基準 `main`）：
  - **Standards**：0 項硬性違規；3 項判斷性建議（圓角數值在三處重複可抽成變數、列印萬用選擇器範圍較大、陰影只加在 `.link-card` 是刻意的設計取捨），均不構成需要修改的問題。
  - **Spec**：0 項缺漏或加料；唯一提醒「標題字體」這條只靠 CSS 繼承，已補測確認 `h1` 的 Computed Font 確實是 Noto Sans TC。

## 人工驗收（待本人操作）

1. 用自己的開發伺服器（或本次對話同款 `.claude/launch.json` 的 8001 埠）開首頁、問卷列表、結果頁、我的紀錄、帳號設定，確認字體變粗變清楚、卡片圓角與陰影的視覺觀感是否符合預期。
2. 開「聽力報告」用「列印或存成 PDF」看列印預覽，確認沒有多出陰影、版面跟改動前一致。
3. （選用）瀏覽器封鎖 `fonts.googleapis.com` 後重新整理任一頁面，確認文字還是看得到、排版不跑掉（fallback 行為）。
4. 縮放到手機寬度或調整系統字級，確認圓角/陰影/間距調整後仍然不會造成左右捲動或觸控區域變小。
