# 0080 前端樣式拆分、字重精簡為 400／700、共版腳本整併與啟用 CSS 壓縮

日期：2026-11-23（本人審定，Batch 3 `/grill-with-docs` Q1–Q8）

> 補充 [ADR 0008](0008-tailwind-css.md) 與 [ADR 0014](0014-self-hosted-font.md)：建置輸出仍為單一 `site.css` 與自託管字型，但精簡字重、拆分原始碼並恢復壓縮。

## 情境

隨著頁面改版累積，前端樣式與共版資源出現四個瓶頸：

1. `frontend/src/site.css` 膨脹到 9,264 行單檔，編輯、搜尋與審查成本高。
2. Noto Sans TC 同時載入 `400`、`500`、`600`、`700` 四個字重，產生 420 組 `@font-face` 與 840 個字型切檔（`.woff2`＋`.woff`）；`@font-face` 經 brotli 壓縮達 20,260 bytes，距預算上限（20,405 bytes）只剩 145 bytes，但全站只剩 16 處零星使用 `500`／`600`。
3. `frontend/vite.config.js` 為了讓測試比對精確的 `rgba(..., 0.5)`，關掉了 Tailwind 與 Vite 的 CSS 壓縮，導致每頁多傳數十 KB 空白與註解。
4. `layout.html` 在每一頁各發起 4 個共版 Vite module 請求（`pwa-nav.js`、`page-loading.js`、`switch-slide.js`、`scroll-helpers.js`）。

## 決定

- **字重精簡**：Noto Sans TC 只保留 `400` 與 `700`。原本 3 處 `600`（`.btn-provider`、桌面版 `.site-nav a`、`.audiogram-symbol`）與標題預設 `h1`–`h6` 改為 `700`；其餘 12 處 `500`（含 `.learn-card > p`）改為 `400`。
- **樣式拆分**：`frontend/src/site.css` 改為入口檔，依原本的層疊順序 `@import` `frontend/src/styles/` 下的 10 個領域檔（`base.css`、`shell.css`、`forms-and-cards.css`、`results-and-charts.css`、`audiogram-and-report.css`、`family-and-account.css`、`results-redesign.css`、`guide-and-print.css`、`journey-and-screening.css`、`tools-and-hero.css`），並移除 5 個未使用的死 CSS class（`.more-group-title`、`.result-level`、`.recommended-block`、`.recommended-label`、`.recommended-list`）。建置輸出仍為單一 `screening/static/screening/frontend/site.css`。
- **共版腳本整併**：把 `pwa-nav`、`page-loading`、`switch-slide`、`scroll-helpers` 整併為單一 Vite 入口 `frontend/src/site-shell-main.js`（輸出 `site-shell.js`），各子模組仍維持獨立檔案與單元測試，並以各自 `try / catch` 隔離錯誤。`copy-link.js`（純靜態檔）與 `logout.js`（登入後才載入）維持分開。
- **啟用 CSS 壓縮**：移除 `frontend/vite.config.js` 的 `optimize: false` 與 `cssMinify: false`，恢復 Tailwind 與 Vite（Lightning CSS）預設壓縮。
- **測試同步**：新增 `screening/tests/helpers.py` 的 `site_css_files()`／`read_site_css()`，讓 `test_standards.py` 與各樣式測試自動掃描 `frontend/src/` 下所有 `.css` 檔並檢查不可有未被 `site.css` 匯入的孤兒樣式檔。

## 理由

- 建置後的 `site.css` 未壓縮從 631 KB 降到 365.8 KB（-42.0%），gzip 從 168.5 KB 降到 96.5 KB（-42.7%），字型切檔減半（420 → 210 個 `.woff2`），並把 `@font-face` brotli 裕度從 145 bytes 拉回 748 bytes。
- 每頁減少 3 個共版 JS 模組請求，且整併後 `site-shell.js` gzip 比原本 4 支合計再少 13.7%。
- 拆分後的每個 CSS 檔約 560–1,370 行，維持原層疊順序不改動既有畫面。

## 代價

- 未來若要在介面上使用 `500` 或 `600` 的中等字重，瀏覽器會對應到 `400` 或 `700`，除非另行評估加回字重與預算。
- 直接讀 CSS 原始碼的測試不能只讀 `frontend/src/site.css`，必須透過 `read_site_css()`（Python）或掃描 `frontend/src/styles/*.css`（Vitest）。
