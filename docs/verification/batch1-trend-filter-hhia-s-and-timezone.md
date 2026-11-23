# 趨勢圖篩選、HHIA-S 趨勢圖與台灣時區一致化

日期：2026-11-23；分支 `feat/trend-filter-hhia-s-and-fixes`（從 `main` 的 `e5a90336` 開出）。
狀態：待本人驗收；**不需交叉審查**（不碰計分規則、分級、門檻、migration，API 權限沿用原有 `request.user` 限定並補上跨帳號隔離測試）。

## 起因

整體檢視後整理的第 1 批（資料與 API 正確性）：

1. 趨勢圖（`TrendChart.jsx`）原本只拉 `/api/submissions/` 第 1 頁（全問卷合計最新 20 筆）再由前端篩選，填過超過 20 筆其他問卷時，HHIE-S 或 THI 趨勢圖會掉點或空白；同時列表 API 為了 SADL 一律預載所有題目答案。
2. HHIA-S（65 歲以下生活影響問卷）尚未開啟趨勢圖，65 歲以下使用者在「我的紀錄」看不到分數變化圖。
3. `User.age` 與 `this_roc_year()` 使用 `date.today()`（系統時區），與全站其餘地方使用的 `timezone.localdate()`（台灣時間）不一致。
4. 訪客限流（`GuestScoreThrottle`、`GuestCountThrottle`）依規格 #492 維持不寫資料庫的 `LocMemCache`，補上正式站 `--workers 2` 各自計數的註解說明。

## 改了什麼

| 項目 | 原本 | 現在 |
|---|---|---|
| `/api/submissions/`（[views.py](../../screening/api/views.py)） | 不支援依問卷篩選，且每筆一律預載全部 `Answer` | 支援 `?questionnaire=<code>` 篩選（已更新 [schema.yaml](../../docs/api/schema.yaml)）；非 `SubscaleResult`（SADL）的篩選查詢跳過預載答案，仍嚴格限定 `request.user` |
| `TrendChart.jsx`（[TrendChart.jsx](../../frontend/src/TrendChart.jsx)） | 呼叫 `/api/submissions/` | 呼叫 `/api/submissions/?questionnaire=<code>` |
| HHIA-S 定義（[hhia_s.py](../../screening/questionnaires/hhia_s.py)） | 未設 `trend_chart`（預設 `False`） | 設 `trend_chart=True`，與 HHIE-S 共用同一套趨勢圖、「開始戴」虛線與結果頁「看紀錄與趨勢」 |
| 年齡與民國年（[accounts.py](../../screening/models/accounts.py)、[forms.py](../../screening/forms.py)） | `date.today().year` | `timezone.localdate().year`（全站統一台灣時區） |
| 訪客限流註解（[settings.py](../../config/settings.py)、[views.py](../../screening/api/views.py)） | 未註明多 worker 各自計數 | 補註 2 個 Gunicorn worker 實際每 IP 上限約為設定值 2 倍，維持 #492 不寫資料庫 |

## 驗證

- 先寫測試看它失敗、再改（TDD）：
  - API 篩選與 IDOR／不預載答案：`test_api.ApiSubmissionTests.test_list_filters_by_questionnaire_and_stays_scoped_to_user`、`test_filtered_graded_list_skips_answer_prefetch_and_does_not_grow`，以及 `test_sadl.SadlScoringTests.test_the_submission_list_reads_answers_the_same_number_of_times_for_two_or_five`（確認 `?questionnaire=sadl` 仍維持常數查詢次數與回傳 `satisfaction`）。
  - 前端趨勢圖：`TrendChart.test.jsx` 驗證呼叫 `/api/submissions/?questionnaire=<code>`；47 個檔案、799 項前端測試全過，`npm run build --prefix frontend` 成功。
  - HHIA-S 趨勢圖：`test_history.py`（`test_hhia_s_tab_shows_its_name_and_trend_chart`、`test_hhia_s_tab_compares_and_shows_trend_chart`、`FittingDayT650Tests`）、`test_result_pages.py`、`test_result_types.py`、`test_hhi_comparisons.py`（`my_hearing` 查詢數比照 HHIE-S 為 13 次）。
  - 台灣時區：`test_accounts.RegisterFormTests.test_age_and_this_roc_year_use_taipei_date` 模擬 UTC 12/31 16:30（台灣已跨年 1/1 00:30），驗證 `User.age` 與 `this_roc_year()` 皆依台灣年份計算。
- 端對端測試（Playwright）：更新 `e2e/main_flow.py` 中攔截 `/api/submissions/` 的路由為 `**/api/submissions/?*`，跑 `test_trend_chart_does_not_push_the_records_down`、`test_every_score_on_the_trend_chart_stays_inside_it`、`test_hhia_s_since_last_is_a_summary_box` 3 項全過。
- 全部測試：Django 3,290 項全過（1 skipped）；前端 Vitest 799 項全過；`ruff check .`、`ruff format --check .` 全過；OpenAPI schema 一致性測試通過。
- 自審（對照 `CODING_STANDARDS.md`）：無違規；無寫死問卷代碼（由 `definition.result is SubscaleResult` 判斷）；查詢次數不隨筆數成長；權限維持 `request.user` 隔離。

## 本人驗收

- [ ] 本機打開「我的紀錄」的 HHIA-S 分頁（需有 HHIA-S 紀錄），確認顯示分數趨勢圖；若有填開始戴助聽器日期，圖上會畫「開始戴」虛線。
- [ ] 在「我的紀錄」的 HHIE-S 或 THI 分頁打開瀏覽器 DevTools Network，確認趨勢圖呼叫的是 `/api/submissions/?questionnaire=<code>`（不再抓全問卷）。
- [ ] HHIA-S 結果頁下方列表顯示「看紀錄與趨勢」。
