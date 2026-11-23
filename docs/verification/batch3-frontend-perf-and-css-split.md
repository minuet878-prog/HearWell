# 驗證紀錄 — Batch 3：前端效能優化與樣式拆分

- 分支：`refactor/frontend-perf-and-css-split`（自 `main` `e5a90336` 分出）
- 日期：2026-11-23
- 相關決策：[ADR 0080](../adr/0080-frontend-css-split-font-weights-and-shell-bundle.md)（Batch 3 `/grill-with-docs` Q1–Q8）
- 交叉審查：不需交叉審查（未觸及計分／分級、門檻、會動資料的 migration 或權限規則）

## 變更摘要

1. **拆分 `frontend/src/site.css` 並移除死 CSS**
   - 將原 9,264 行單檔依原層疊順序拆成 `frontend/src/styles/` 下 10 個領域檔（`base.css`、`shell.css`、`forms-and-cards.css`、`results-and-charts.css`、`audiogram-and-report.css`、`family-and-account.css`、`results-redesign.css`、`guide-and-print.css`、`journey-and-screening.css`、`tools-and-hero.css`），`site.css` 作為入口檔依序 `@import`。
   - 移除 5 個全站未使用的死 CSS class：`.more-group-title`、`.result-level`、`.recommended-block`、`.recommended-label`、`.recommended-list`（同時將 `.result-banner > div:not(.result-level)` 簡化為 `.result-banner > div`）。
   - 新增 `screening/tests/helpers.py` 的 `site_css_files()` 與 `read_site_css()`，更新全部 11 支讀取 CSS 原始碼的測試（9 支 Python、2 支 Vitest）；`test_standards.py` 同步改為遞迴掃描 `frontend/src/**/*.css` 並確保沒有未被 `site.css` 匯入的孤兒樣式檔。
2. **精簡 Noto Sans TC 字重為 `400` 與 `700`**
   - 移除 `@fontsource/noto-sans-tc/500.css` 與 `600.css` 匯入。
   - 原 3 處 `600`（`.btn-provider`、桌面版 `.site-nav a`、`.audiogram-symbol`）與 `h1`–`h6` 改為 `700`；其餘 12 處 `500`（含 `.learn-card > p`）改為 `400`。
   - 更新 `e2e/main_flow.py` 的 `StyleInBrowserTest.test_body_font_comes_from_our_own_host` 只驗證自託管 `400` 與 `700`。
3. **整併共版 4 支 Vite 腳本為 `site-shell.js`**
   - 建立 `frontend/src/site-shell-main.js`，以各自 `try / catch` 隔離執行 `in-view`、`pwa-nav`、`page-loading`、`switch-slide`、`back-to-top`、`jump-highlight`、`scroll-hint`、`tab-bar`、`site-header`、`account-menu`；保留各子模組與既有單元測試不變，移除舊的 4 支 `*-main.js` 包裝檔。
   - `layout.html` 改為單一 `<script type="module" src="{% static 'screening/frontend/site-shell.js' %}"></script>`；`copy-link.js` 與 `logout.js` 維持分開。
   - 更新 `screening/tests/test_pages.py` 與 `e2e/main_flow.py:10116`。
4. **重新開啟 Tailwind 與 Vite 內建 CSS 壓縮**
   - 移除 `frontend/vite.config.js` 的 `optimize: false` 與 `cssMinify: false`。
   - `StyleInBrowserTest` 所有既有色彩與焦點環斷言（`rgba(31, 78, 140, 0.5)` 等）皆無需放寬即全數通過；`--logo-glyph` 的 `url%28` 亦維持完好。
   - `SlidingPillTest.test_slow_page_without_render_blocking_never_fades_the_pill` 因 `site.css` 縮小 42% 後在 6x CPU 降速下每次都能於首次繪製前解析完成，改用 16x 降速確認無 `<link rel="expect">` 時 `switch-reveal.js` 仍正常跳過過場。
5. **文件更新**
   - 新增 [ADR 0080](../adr/0080-frontend-css-split-font-weights-and-shell-bundle.md)，更新 `CODING_STANDARDS.md` 第 21 條與 `AGENTS.md` 樣式來源說明。

## 建置前後體積比較

| 指標 | 改動前 | 改動後 | 變化 |
|---|---:|---:|---:|
| `site.css` 總大小（未壓縮） | 631,085 B | 365,832 B | **-42.0%**（-265 KB） |
| `site.css` 總大小（gzip） | 168,451 B | 96,528 B | **-42.7%**（-71.9 KB） |
| `site.css` 總大小（brotli） | 45,415 B | 44,053 B | -3.0% |
| 純 CSS 規則（不含 `@font-face`，未壓縮） | 202,621 B | 158,482 B | **-21.8%** |
| 純 CSS 規則（gzip / brotli） | 31,095 / 24,898 B | 28,498 / 24,042 B | -8.4% / -3.4%（預算 28,459 B，裕度 +4,417 B） |
| `@font-face` 規則數 / `.woff2` 檔數 | 420 / 420 | 210 / 210 | **-50.0%**（共少 420 個靜態字型檔） |
| `@font-face` CSS（gzip / brotli） | 135,464 / 20,260 B | 67,406 / 19,657 B | **-50.2%** / -3.0%（預算 20,405 B，裕度由 145 B → 748 B） |
| 共版 Vite JS 請求數 | 4 支 | 1 支（`site-shell.js`） | **每頁少 3 個模組請求** |
| 共版 Vite JS 合計（gzip / brotli） | 3,730 / 3,093 B | 3,220 / 2,756 B | -13.7% / -10.9% |

## 自動化測試證據

| 測試項目 | 指令 | 結果 |
|---|---|---|
| 前端建置 | `npm run build --prefix frontend` | 通過（818ms；`data:` URI 無裸 `url(`） |
| 前端單元與體積測試 | `npm test --prefix frontend` | **47 / 47 檔、799 / 799 通過**（含 `bundle.test.js`、`components.test.js`、`AnswerApp.test.jsx`） |
| 後端與規範測試 | `py313/bin/python manage.py test --settings=config.test_settings --parallel` | **3,287 通過、1 跳過**（含 `test_standards.py` 全 CSS 掃描與孤兒檔檢查） |
| Playwright 瀏覽器測試（相關 6 大類） | `StyleInBrowserTest`、`LoadingIndicatorTest`、`SlidingPillTest`、`SiteHeaderTest`、`PlayInViewTest`、`GettingOnTheHomeScreenTest` | **85 / 85 通過**（初次跑完發現字型測試與慢速降級測試 2 處需同步，更新後 3/3 重驗全過） |
| 格式與靜態檢查 | `py313/bin/ruff check .` & `py313/bin/ruff format --check .` | 通過（739 檔符合格式） |

## 負責人驗收清單

- [ ] 以本機伺服器開啟首頁、問卷清單、結果頁、我的紀錄、了解頁卡片堆疊，目視確認移除 `500`／`600` 字重後的視覺層次符合預期
- [ ] 在手機寬度或 DevTools 確認頁首霧玻璃返回鍵、頭像選單、底部分頁列、載入條、滑動膠囊與回頂端按鈕皆正常（皆由 `site-shell.js` 啟動）
- [ ] 在 DevTools Network 分頁確認只載入單一 `site.css`、`site-shell.js`、且字型只向本站載入 `400` 與 `700`
