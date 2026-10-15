# Phase 4 規格：React 趨勢圖與 PWA

- **狀態**：第 1 批完成（驗收 17 待合併部署後確認）；第 2 批未開始
- **分支**：`feat/react-trend-chart`（第 1 批）、第 2 批另開
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-15

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

讓使用者在「我的聽力」頁一眼看出自己歷次篩檢分數的變化、落在哪個分級（B2 趨勢圖），這是第一個 React 元件；第 2 批讓網站可以加到手機主畫面（PWA）。65 歲以上的使用者在字級放大、螢幕閱讀器、慢網路、JS 失敗時都要能用。

## 2. 範圍

### 第 1 批：趨勢圖（`feat/react-trend-chart`）
- 前端建置環境（React＋圖表套件 Recharts），產物跟網站同一個服務提供（同源），部署時在 Render 上建置。
- 問卷列表 API 多回傳各分級的上限與文字（`levels`），趨勢圖的分級區間由此而來。
- 「我的聽力」頁、卡片列表上方加趨勢圖與一句文字摘要。

### 第 2 批：PWA（另開分支，開工前補這一節的細節與劇本）
- 可加到主畫面：app 名稱、圖示、主題色。

### 不做
- 登入、註冊、首頁、作答頁、結果頁改成 React。
- 任何寫入 API、作答 React 化、中途儲存（Phase 5）。
- 離線使用、推播通知、上架 App Store／Google Play。
- 情緒／社交分項畫在圖上（A3 已決定分項沒有正式解讀標準）。
- 圖上的篩選、切換、縮放、時間範圍選擇。
- 除了 `levels` 以外修改 API 的欄位或行為。
- 前端重算分數或分級；前端另存一份門檻數字。
- 修改現有卡片列表的內容或行為。
- 「變好／變差」之類的評價用詞。

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本 phase 特別注意：
  - **第 10 條**：分數、分級文字、分級界線都來自 API；前端只負責畫。
  - **第 11 條**：0 分畫在 0 的位置，不能被當成「沒資料」略過。
  - **第 13 條**：字級用 `rem`；瀏覽器放大到 200% 不爆版、不需要左右捲動。
  - **漸進增強**：JS 關閉或載入失敗時，「我的聽力」頁的卡片列表照常可用。
  - **只在需要的頁面載入 React**：其他頁面不多載任何 JS。
  - 分級不能只靠顏色辨識（區間底色要有文字標籤）。
  - 新增的前端套件寫進版控、固定版本。

## 4. 行為描述

### 4.1 問卷列表 API 加上 `levels`（`GET /api/questionnaires/`）

| 項目 | 內容 |
|---|---|
| 誰可以使用 | 不變（未登入 403） |
| 回傳 | 每份問卷多一個 `levels`，依分數由低到高 |
| 需要計算的資料 | 由誰計算：後端　　來源：`scoring.THRESHOLDS`（唯一一份門檻表） |
| 沒有門檻表的問卷 | `"levels": []` |

```json
{"id": 1, "code": "hhie-s", "name": "HHIE-S", "levels": [
  {"code": "normal", "text": "無/極輕微影響", "max": 8},
  {"code": "mild_to_moderate", "text": "輕度到中度影響", "max": 24},
  {"code": "severe", "text": "顯著影響", "max": 40}
]}
```

（第 1 批 Phase 3 的驗收 3「沒有其他欄位」隨之改成包含 `levels`。）

### 4.2 趨勢圖（「我的聽力」頁）

| 項目 | 內容 |
|---|---|
| 位置 | 卡片列表上方 |
| 誰可以使用 | 頁面本來就要登入；只看到自己的（API 已限制） |
| 資料 | 最近 20 筆（`/api/submissions/` 第一頁）中，**跟最新一筆同一份問卷**的紀錄 |
| 畫法 | 橫軸日期（`YYYY/MM/DD`，舊→新由左到右），縱軸總分 0 到該問卷最高級的 `max`；背景依 `levels` 畫帶狀區間，每條帶子有分級文字；圖標題含問卷名稱 |
| 每個點 | 點選或滑過時顯示日期、總分、分級文字 |
| 文字摘要（圖下方） | 見下表 |
| 0 筆 | 不顯示圖與摘要，維持原本的「您還沒有做過篩檢紀錄」 |
| 載入失敗 | 圖的位置顯示「趨勢圖暫時無法顯示，下方的紀錄不受影響。」 |
| 問卷沒有門檻表 | 照畫折線，沒有區間底色；縱軸上限用資料中的最高分 |
| **不能**顯示 | 分項分數；評價用詞 |

文字摘要：

| 情況 | 摘要 |
|---|---|
| 1 筆 | 最近一次 2026/10/14：18 分，輕度到中度影響。再做一次篩檢，就能看到分數的變化。 |
| 比上一次高 | 最近一次 2026/10/14：18 分，輕度到中度影響，比上一次增加 6 分。 |
| 比上一次低 | ……比上一次減少 6 分。 |
| 一樣 | ……和上一次相同。 |

（「上一次」＝圖上倒數第二個點。）

> 2026-10-15 介面改版：摘要改成圖上方的摘要框、分行呈現（資訊不變），見 `phase4_ui_redesign.md` 4.5。

## 5. 驗收條件（第 1 批）

API
- [x] 1. 假設 HHIE-S 有門檻表，當已登入呼叫問卷列表，則該問卷的 `levels` 依序是 normal／mild_to_moderate／severe，`max` 為 8／24／40，文字與網頁相同。
- [x] 2. 假設問卷沒有門檻表，則 `levels` 是 `[]`，不會 500。
- [x] 3. schema 檔已更新；Phase 3 的 API 測試（改寫驗收 3 後）全部通過。

頁面（伺服器端）
- [x] 4. 假設 JS 沒有執行，當打開「我的聽力」頁，則卡片列表與原本相同；沒有紀錄時仍顯示「您還沒有做過篩檢紀錄」。
- [x] 5. 假設打開首頁、登入、註冊、問卷列表、作答頁、結果頁，則都沒有載入趨勢圖的 JS；只有「我的聽力」頁有。

趨勢圖（前端）
- [x] 6. 假設 0 筆紀錄，則不顯示圖與摘要。
- [x] 7. 假設 1 筆紀錄，則畫出一個點，摘要是「1 筆」那一句。
- [x] 8. 假設 3 筆紀錄（12、18、0 分，由舊到新），則折線由左到右依序是 12、18、0，0 分的點畫在 0 的位置；摘要是「最近一次……：0 分，無/極輕微影響，比上一次減少 18 分。」
- [x] 9. 假設最近兩次分數相同，則摘要結尾是「和上一次相同。」；增加時是「比上一次增加 N 分。」
- [x] 10. 假設 API 有 21 筆紀錄，則圖上只有最近 20 筆。
- [x] 11. 假設最近 20 筆裡有兩份問卷的紀錄，則圖只畫跟最新一筆同一份問卷的紀錄，標題是該問卷名稱。
- [x] 12. 假設 `levels` 有三級，則背景有三條帶狀區間，界線在 8、24 分，每條都有分級文字；假設 `levels` 是 `[]`，則沒有區間、折線照畫。
- [x] 13. 假設 API 回錯誤或網路失敗，則顯示「趨勢圖暫時無法顯示，下方的紀錄不受影響。」，頁面其他部分照常。
- [x] 14. 分數與分級文字都直接取自 API 回應（測試用與門檻表不同的假文字，畫面要顯示假文字）。

無障礙與部署（人工驗收，結果記入 `docs/accessibility_baseline.md`）
- [x] 15. 瀏覽器放大到 200%，「我的聽力」頁不需左右捲動，圖上文字跟著放大；axe-core 在該頁沒有新增問題。
- [x] 16. 記錄「我的聽力」頁新增的 JS 體積（壓縮後）。→ 2026-10-15 實量：未壓縮 569 KB、gzip 168 KB、brotli 141 KB（含 React 與 Recharts）
- [ ] 17. Render 部署成功，正式環境「我的聽力」頁看得到趨勢圖；現有 Django 測試全部通過。

## 6. 待決問題

- [x] ~~怎麼切批次？~~ → 兩批：第 1 批趨勢圖、第 2 批 PWA
- [x] ~~圖上畫什麼？~~ → 總分＋分級區間底色（有文字標籤）
- [x] ~~畫多少筆？~~ → 最近 20 筆
- [x] ~~0～1 筆怎麼辦？~~ → 0 筆不顯示圖；1 筆畫一個點並說明
- [x] ~~分級界線從哪來？~~ → 後端 API（問卷列表加 `levels`）
- [x] ~~圖表套件？~~ → Recharts
- [x] ~~部署怎麼建置？~~ → Render 上建置。已查證（PR #22 部署 log，2026-10-15）：Render 的 Python 服務建置時會裝 Node.js 24.14.1（預設版本）
- [x] ~~文字替代？~~ → 圖下一句摘要＋原本的卡片列表
- [x] ~~多份問卷？~~ → 只畫跟最新一筆同一份問卷的紀錄
- [x] ~~摘要用詞？~~ → 列數字＋增減幾分，不用評價用詞
- [x] ~~載入失敗？~~ → 一句說明

---

## 完成後回報（由 AI 填寫）

### 第 1 批（`feat/react-trend-chart`）

- **改了哪些檔案、為什麼**：
  - `frontend/`（新）：`package.json`／`package-lock.json`（React 19.3.0、Recharts 3.10.1、Vite 8.3.2、Vitest 5.0.3 等，固定版本、挑發布滿兩週的版本）；`vite.config.js`（產物輸出到 `screening/static/screening/trend/trend-chart.js`，固定檔名，collectstatic 加雜湊）；`src/trend.js`（挑資料、產生摘要，純函式）；`src/TrendChart.jsx`（抓 API、畫圖、錯誤訊息）；`src/main.jsx`（掛到 `#trend-chart`）；兩個測試檔。
  - `screening/api/serializers.py`：問卷列表加 `levels`（直接讀 `scoring.THRESHOLDS`）；作答紀錄裡的問卷欄位不變。
  - `screening/templates/screening/my_hearing.html`：有紀錄才放 `#trend-chart` 和 `<script type="module">`。
  - `build.sh`：移除 PR #22 的試驗行，改成 `npm ci --include=dev` → `npm run build` → collectstatic。
  - `.node-version`（新）：`24.21.0`。
  - `config/test_settings.py`（新）：測試改用一般靜態檔儲存，不需要先 collectstatic。
  - `.gitignore`：`node_modules/`、建置產物。
  - `claude.md`：測試指令加 `--settings=config.test_settings`，新增前端測試與建置指令。
  - `docs/api/schema.yaml`：重新產生（`levels`）。
  - `screening/tests.py`：`TrendChartPageTests`（6 個）；改寫 Phase 3 問卷列表測試（多 `levels`）。
- **驗收條件對應的測試**（Django＝`screening/tests.py`，前端＝`frontend/src/*.test.js(x)`）：
  1. `test_questionnaire_levels_come_from_thresholds`
  2. `test_levels_empty_without_thresholds`
  3. `test_committed_schema_is_up_to_date`、`ApiFoundationTests.test_questionnaire_list`
  4. `test_history_page_works_without_js`、`test_history_page_without_submissions_has_no_chart`
  5. `test_only_history_page_loads_chart_js`、`test_chart_js_path_matches_vite_output`
  6. 前端 `renders nothing without submissions`（伺服器端也不放 JS，見 4）
  7. 前端 `shows one point and how to see a change`、`summarize` 1 筆
  8. 前端 `draws a point for every submission, including a score of 0`（0 分的點在繪圖區底部）、`selectPoints` 順序
  9. 前端 `summarize` 增加／減少／相同
  10. 前端 `only uses the first page (latest 20)`（20 筆上限由 API 分頁保證）
  11. 前端 `follows the newest submission's questionnaire`、`selectPoints` 過濾
  12. 前端 `shows the summary, the title and a labelled band per level`（斷言區間 0–8、8–24、24–40）、`draws no bands when the questionnaire has no levels`
  13. 前端兩個錯誤測試（API 錯誤、網路失敗）
  14. 前端 `shows the API's level text, not a recomputed one`、`selectPoints` 假文字
  15. 人工驗收（本人，2026-10-15）：200% 不需左右捲動、axe-core 無新增問題、浮動框分數正確
  16. 實量記錄於本規格第 5 節
  17. 合併部署後由本人確認
- **規格以外的決定**：
  - 實作時發現：Django 測試原本就依賴 collectstatic（清單裡沒有的靜態檔會 500）。AI 一開始提議 `WHITENOISE_MANIFEST_STRICT = False`，實測無效（非 strict 仍要讀檔算雜湊），本人選擇改用測試專用設定。
  - Node 固定 24.21.0：jsdom 30 要求 ≥24.15，Render 預設 24.14.1 不夠；本機是 v26，主版本不同，風險低。
  - `npm ci --include=dev`：避免 Render 若設 `NODE_ENV=production` 時跳過建置工具。
  - 審查後修：沒有門檻表且全部 0 分時縱軸變成 [0, 0]、點畫在中間 → 上限至少 1。
  - 人工驗收時本人發現：同一天多筆紀錄時，浮動框顯示當天第一筆 → 橫軸改用 `id`、顯示時換回日期。
- **這次用到的新概念**：Vite／前端建置、漸進增強、manifest 靜態檔與內容雜湊、jsdom、測試專用設定、退化的範圍、「失敗的原因要對」。
- **面試可能追問的 2–3 題**：Q34、Q35、Q36。要點見 `docs/interview.md`。
- **建議寫進 decisions/ 的內容**：見對話（由本人撰寫）。
