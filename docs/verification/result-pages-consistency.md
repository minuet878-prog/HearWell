# THI 色帶與結果頁一致化

日期：2026-10-23；分支 `feat/result-pages-consistency`（從 `origin/main` 開出）。
狀態：自動驗證完成；**不需交叉審查**（只改分級的顯示顏色和畫面，不改分級規則、門檻、資料或權限；本人可改判要審）；**等本人實際操作驗收**。

## 範圍

來自結果頁與助聽器驗證流程的審查（對話中整理，沒有開 issue）。本人選 THI 色帶做法 A，並要求做結果頁一致化 R1–R4、R6。R5、R7、R8、F1–F7 不在這次。

| 項目 | 需求 | 改了哪裡 |
|---|---|---|
| A THI 色帶 | 同色系分深淺＋白線；圖例五格對得上五條色帶；分數條也跟著變五段 | `definition.py` 的 `shade()`、API 的 `levels[].shade`、`trend_chart.html`、`score_bar.html`、`TrendChart.jsx`、`site.css`；ADR 0018 |
| R1 標題 | 標題改問卷主題，副標「名稱・日期 作答・有沒有戴」，跟 SSQ12 一樣 | 共用 `result_header.html`，六個結果頁都用 |
| R2 摺疊 | 統一成有框、高度 ≥ 44px 的樣式 | 「分數細節與作答明細」「看全部 12 題的回答」「其他 n 項」改用 `.phone-choice` |
| R3 結尾按鈕 | 看我的紀錄（主）→ 看／印聽力報告 → 回首頁；各頁特有的（比較）放前面 | 共用 `result_actions.html`，六個結果頁都用 |
| R4 SSQ12 | 「分數越高越好」只講一次 | 有「比上一次」那行時，不再另外寫一句 |
| R6 IOI-HA 量表 | 兩端加「較差」「較好」 | `ioi_ha_item.html`；文字放在 `ioi_ha.py` 的 `SCALE_ENDS`（規範第 9 條） |

## 驗收條件對照

| 條件 | 證明 |
|---|---|
| A：API 給 THI 五級「淺、淺、深、淺、深」 | `test_thi_history.py` `test_trend_chart_levels_from_the_api_shade_two_levels_sharing_a_colour` |
| A：圖例中度、極重度標成深色 | `test_thi_history.py` `test_tab_has_a_trend_chart_with_five_bands_in_three_colours` |
| A：趨勢圖五條色帶的顏色與白線 | `TrendChart.test.jsx`「fills the deeper shade where the API says so」 |
| A：分數條五段的實際顏色與白線、圖例色塊的實際顏色 | e2e `StyleInBrowserTest.test_thi_bar_and_legend_shade_levels_sharing_a_colour` |
| R1：六頁標題與副標；THI 不再叫「篩檢結果」 | `test_result_pages.py` 的 header、title 兩個測試 |
| R2：每個摺疊都是有框的；THI 結果頁兩個摺疊高度 ≥ 44px | `test_result_pages.py` dropdown 測試；上面那個 e2e |
| R3：六頁結尾三顆按鈕與順序；「比較」在結尾列之前 | `test_result_pages.py` 的 closing row 與 comparison 測試 |
| R4：有上一次時只講一次；沒有上一次時照樣說明 | `test_result_pages.py` 兩個 SSQ12 測試 |
| R6：IOI-HA 七題都有兩端標示 | `test_result_pages.py` `test_ioi_ha_scale_names_its_two_ends` |

## 自動驗證

| 檢查 | 結果 |
|---|---|
| `python manage.py test --settings=config.test_settings` | 1073 個全部通過；新測試先確認在改之前失敗 |
| `npm test --prefix frontend` | 217 個全部通過 |
| `ruff check .` | 通過 |
| `e2e.main_flow`（先 `npm run build`） | 103 個全部通過 |

改動後原本沒過的舊測試，都是寫死了舊的 HTML 或 API 格式，改法不放寬要保護的東西：

- API 分級（`test_api`、`test_history`、`test_hhia_s`、`test_questionnaire_definitions`）：每一級多了 `shade`。`docs/api/schema.yaml` 重新產生。
- 兩級同色的假問卷（`test_life_impact`）：第二級多了深色 class。
- 頁面標題（`test_pages`）：「篩檢結果」改成「HHIE-S 結果」；「看我的紀錄與趨勢」的連結多了 `?questionnaire=hhie-s`。
- HHIA-S（`test_recommendations`）：按鈕改成「看我的紀錄」，因為 HHIA-S 沒有趨勢圖。
- IOI-HA（`test_ioi_ha`）：「其他 n 項」多了 class；沒有常模分組時不再顯示「接下來」；報告與紀錄連結搬到結尾列。
- SADL（`test_sadl`）：出處要在「回首頁」之後（原本是「選擇問卷」）。

## 自審（`/code-review`，Standards 與 Spec 兩軸）

已修：

- 規範第 9 條：「較差／較好」原本寫在模板裡，改成從 IOI-HA 定義產生。
- 四個結果頁的標題各寫一份，SSQ12 的寫法還跟其他頁不一樣：抽成 `result_header.html`。
- 按鈕列縮排跟其他模板一致。
- 補斷言：摺疊高度、分數條白線與深色、「比較」在結尾列之前。

不修（判斷題）：`color` 和 `shade` 在三處一起組出來、`shade` 用字串表示、深色色碼在 CSS 和 `TrendChart.jsx` 各寫一份（沿用既有做法，程式註解有說明）。

## 超出 R1–R4、R6 字面的改動（請本人確認）

1. SADL 標題也改成「助聽器滿意度／SADL・日期 作答」（R1 只列了 HHIE-S、HHIA-S、THI；改了才六頁一致）。
2. IOI-HA 沒有常模分組時，「接下來」整段拿掉：原本裡面只有兩顆按鈕，現在按鈕都在結尾列。
3. 「看我的紀錄」直接打開這份問卷的分頁（`?questionnaire=代號`）；HHIA-S 的按鈕從「看我的紀錄與趨勢」改成「看我的紀錄」（HHIA-S 沒有趨勢圖）。
4. 白線套用到所有問卷的趨勢圖和分數條，HHIE-S、HHIA-S 也會看到。
5. SADL 結尾的「選擇問卷」按鈕拿掉，改成三顆共用按鈕（下方導覽列仍有「開始篩檢」）。
6. HHIE-S、HHIA-S、THI 結果頁會出現兩顆「看／印聽力報告」：一顆在建議步驟裡、一顆在結尾列。

## 本人實際操作驗收

- [ ] 我的紀錄 → 耳鳴（THI）分頁：圖上五條色帶，圖下五格顏色一一對上
- [ ] THI 結果頁：標題「耳鳴對生活的影響」、分數條五段
- [ ] 六個結果頁的標題、摺疊、結尾三顆按鈕看起來一致
- [ ] IOI-HA 結果頁：每題量表下有「較差」「較好」
- [ ] 上面「超出範圍的改動」六項是否都接受
