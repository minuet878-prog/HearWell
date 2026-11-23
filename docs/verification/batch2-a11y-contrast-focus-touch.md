# 無障礙總檢與修正（舊聽力圖對比、註冊錯誤焦點、觸控尺寸與 200% 報告頁）

日期：2026-11-23；分支 `fix/a11y-contrast-zoom-and-focus`（從 `main` 的 `e5a90336` 開出）。
狀態：待本人驗收；**不需交叉審查**（不碰計分、分級、門檻、migration、權限）。

## 起因

清查全站改版與 `#741` 之後的無障礙基準線（`docs/accessibility/accessibility_baseline.md` 第 5.4 節）與 200% 字級回歸盲點：

1. 聽力圖比較頁「舊圖」線與符號原為 `#e8a59d`／`#9db5d6`，在正常聽力區綠底 `#e9f5ec` 對比僅 1.82:1／1.87:1（低於 WCAG 2.1 非文字標準 3:1）。
2. 註冊表單驗證失敗時，Django 預設把 `autofocus` 留在 `username`，焦點不會移到第一個有錯的欄位。
3. 本人聽力報告頁 `/report` 未列入 320px＋200% 字級 e2e 回歸檢查。
4. 20 頁即時 Playwright 掃描抓到 `/qa` 搜尋輸入框（43px）與選配指引章節返回連結（26px）未達 44px 觸控尺寸。

## 改了什麼

| 項目 | 原本 | 現在 |
|---|---|---|
| 舊聽力圖顏色（[AudiogramChart.jsx](../../frontend/src/AudiogramChart.jsx)、[site.css](../../frontend/src/site.css)） | `#e8a59d`（1.82:1）／`#9db5d6`（1.87:1） | 本人於比較頁選定方案 A：`#cc5f56`（綠底 3.51:1／白底 3.93:1）、`#5980b5`（綠底 3.62:1／白底 4.05:1），維持虛線 |
| 註冊表單錯誤焦點（[forms.py](../../screening/forms.py)、[accounts.py](../../screening/views/accounts.py)） | 送錯時 `autofocus` 永遠留在 `username` | `RegisterForm.focus_first_error()` 依畫面順序把 `autofocus` 移到第一個錯欄；首次打開仍不設 `autofocus` |
| 觸控尺寸（[site.css](../../frontend/src/site.css)、[chapter.html](../../screening/templates/screening/guide/chapter.html)） | `.form-control`／`.form-select` 約 42–43px；指引返回連結 26px | 輸入框與下拉設 `min-height: var(--spacing-touch)`；指引返回連結加上 `.inline-link` |
| 基準線與 e2e（[accessibility_baseline.md](../accessibility/accessibility_baseline.md)、[main_flow.py](../../e2e/main_flow.py)） | 最後量測停在 2026-10-16；`/report` 沒跑 200% 測試 | 補記第三次量測（20 頁全過）；`test_batch2_pages_fit_a_phone_at_double_text_size` 納入 `/report`（含巢狀 `<details>` 展開） |

## 驗證

- 先寫測試看它失敗、再改（TDD）：
  - `AudiogramChart.test.jsx`：驗證舊右耳 `#cc5f56`、舊左耳 `#5980b5`；前端 47 個檔案、799 項測試全過。
  - `test_accounts.RegisterFormTests.test_focus_moves_to_first_error_field`：驗證首次載入無 `autofocus`，以及 `password2`、`email`、`roc_birth_year`、`username` 出錯時焦點皆移到第一個錯欄。
- 端對端測試：19 項 `fit_a_phone_at_double_text_size` e2e（含 `/report`、`/register`、`/audiograms/compare`）全過；20 頁即時 Playwright 掃描無 `h1`／`alt`／標籤／320px 捲動／觸控高度問題。
- 全部測試：Django 全套測試通過；`ruff check .`、`ruff format --check .` 全過；`npm run build --prefix frontend` 成功。

## 本人驗收

- [ ] 本機打開「聽力圖比較」頁，確認舊圖虛線（方案 A）清楚可見且與新圖實線層次分明。
- [ ] 本機打開「註冊」頁，填一個有效使用者名稱、故意讓兩次密碼不同並送出，確認游標自動停在「確認密碼」欄。
- [ ] 本機打開任一「選配指引」章節與「問答小助手」，確認頂端返回連結與搜尋框好點擊、版面自然。
