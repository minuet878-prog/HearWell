# 4a 首頁：實作計畫

規格：[phase9_ui_refresh_4a_home.md](../../specs/phase-09/phase9_ui_refresh_4a_home.md)（已確認，2026-10-18）

## 要改的檔案

| 檔案 | 改什麼 |
|---|---|
| `screening/views.py` | `index()` 多傳示意圖要用的三個值：`classify(18, "hhie-s")`、`max_score("hhie-s")`、`get_advice(level)`。18 分寫成常數 `HOME_PREVIEW_SCORE = 18`。不另寫分級或建議文字（規格 4.2「文字來源」、規則 9／10）。 |
| `screening/templates/screening/index.html` | 照 4.1 重排：<br>1. `<section class="home-band">`：耳朵聲波 SVG（比較頁 A-1 那張，`aria-hidden="true"`、`focusable="false"`）→ h1 → 副標 → 開始篩檢 →（未登入）註冊提示<br>2. `<ol class="step-cards">`：三張卡片，各有號碼、圖示 SVG（夾板、勾選框、長條圖，`aria-hidden`）、原本文字<br>3. `<h2>結果長這樣</h2>` ＋ `<figure class="result-preview">`：左上「示意圖」標籤、分級色塊沿用結果頁的 `result-banner-{{ level }}` 顏色、「HHIE-S 總分 18 分（滿分 40）」、建議前 40 字（模板 `slice:":40"`）加「……」、`<figcaption>實際結果依您的回答而定。</figcaption>`。「示意圖」和說明都是看得見的文字，螢幕閱讀器自然念得到。<br>4. 及早了解那一句（`<p>`，白底）<br>5. `<section class="home-band">`：h2「由聽力師開發」＋兩點 `<ul>`<br>拿掉原本的卡片和「本網站由執業聽力師開發……」 |
| `screening/static/screening/styles.css` | 刪掉只給首頁用的 `.steps` 規則；新增 `.home-band`（淡藍底 #eef3fa、圓角、內距）、`.step-cards`（grid，`repeat(auto-fit, minmax(12rem, 1fr))`：寬時三欄、窄時自動一欄）、`.step-icon`、`.result-preview`／`.preview-tag`。全部 `rem`。 |
| `screening/tests/test_pages.py` | 首頁測試：<br>• 更新 `HOME_ORDER`（加插圖、示意圖、信任區塊，拿掉舊句）<br>• **改** `test_home_has_no_scale_names_or_missing_features`：舊的 phase4 規則「首頁不出現 HHIE-S」跟這次規格衝突（示意圖與信任區塊都寫了 HHIE-S），改成只檢查 HHIA-S 和沒做的功能<br>• 新增驗收 1–7 的測試 |
| `e2e/main_flow.py` | 驗收 8：320px 三張步驟卡片上下直排（同一個 x、y 遞增）。「不需左右捲動」現有測試已經涵蓋首頁 `/`。 |

## 驗收條件 → 測試

| # | 測試 | 怎麼驗 |
|---|---|---|
| 1 | `test_home_illustration_first_and_hidden`（未登入／已登入各一次） | 插圖 `<svg aria-hidden="true"` 出現在 h1 之前 |
| 2 | 更新後的 `HOME_ORDER` 兩個順序測試 | 插圖 → 標題 → … → 信任區塊 |
| 3 | `test_home_step_cards` | 三個 `<li>` 各有號碼、`aria-hidden` 圖示、原文字 |
| 4 | `test_home_result_preview_uses_real_scoring` | 期望值從 `classify(18, "hhie-s")`、`get_advice()[:40]` 算，不寫死文字；有「示意圖」與說明 |
| 5 | `test_home_shows_no_user_data` | 使用者 A 有 30 分的紀錄 → `<main>` 裡沒有 A 的帳號名稱、「總分 30」、作答日期 |
| 6 | `test_home_trust_block` | 標題、兩點文字；沒有「出處都列在說明頁」與舊句 |
| 7 | `test_home_band_backgrounds` | 插圖區與信任區塊在 `home-band` 裡；步驟卡片與示意圖不在 |
| 8 | e2e `test_home_step_cards_stack_on_a_phone` | 320px 下三張卡片 x 相同、y 遞增 |
| 9 | 人工 | 你在手機 320px、200% 字級看；axe 0 |

## 順序

1. 先改／寫測試，跑一次確認新測試失敗。
2. 改 view、模板、CSS，跑全部 Django 測試＋前端測試＋build＋e2e。
3. 驗收 1–8 打勾，請你做第 9 條。
