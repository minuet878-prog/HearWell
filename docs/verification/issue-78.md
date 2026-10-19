# #78 HHIA-S 作答與結果：驗證及驗收

日期：2026-10-19。規格：[Add the HHIA-S answering and results flow #78](https://github.com/minuet878-prog/HearWell/issues/78)。分支：`codex/adult-questionnaire-design`。

狀態：程式、自動測試與兩軸審查完成，等待本人實際操作驗收。未 push、未開 PR、未合併 main；#78 不因程式完成而結案。

## 改了什麼

- 新增 `seed_hhia_s`：依 `hhia-s` 代碼僅建立一次問卷與十題，單一交易完成，不更新既有版本。部署在原有 fixture 載入後執行，避免固定資料編號覆寫舊題目；既有 fixture 未修改。
- 原題逐字依使用者提供的《助聽器選配與驗證》書內第 165 頁（PDF 第 166 頁）視覺核對；E/S 各五題。原題「你」保留，網站說明用「您」。使用條件沿用本人對 #77 的審定，不聲稱新增取得提供者授權或完成台灣中譯驗證。
- 沿用既有 React／HTML 備用表單、作答驗證、Submission 計分、session 認證、收據編號防重送及本人資料權限。
- 新增 HHIA-S 門檻（0–8、10–24、26–40）、已審定成人建議與共通說明。原 HHIE-S 門檻與文案不變。
- HHIA-S 選項為會／有時／不會（4／2／0）。API、HTML 表單、結果與匯出一致，結果讀取預先載入問卷，避免逐題追加查詢。
- 顯示適用年齡及可繼續原問卷的提示，不依年齡阻擋作答；不提前實作年齡推薦、IOI-HA 常模擴充、手選比較或報告整合。

## 驗收條件對照

以下為自動驗證對照；本人實際操作仍待確認。

| #78 條件 | 證據 |
|---|---|
| ✅ 獨立十題版本、既有版本不變、提醒不阻擋 | `test_catalog_has_an_independent_ten_question_version`；`test_web_fallback_can_complete_retry_and_find_history_after_65`；審查既有 fixture 零差異 |
| ✅ 配戴狀態、4/2/0、錯誤作答不保存、重送不重複 | `test_web_invalid_answers_are_not_saved_and_keep_accessible_errors`；`test_api_retry_validation_and_private_results`；HTML 重送測試 |
| ✅ 六個門檻邊界、三段建議及共通說明、十題有時 20 分 | `test_results_use_adult_levels_and_advice_at_all_boundaries`；`test_original_answer_labels_match_api_form_and_results` |
| ✅ 結果／歷史／API 一致、日期、狀態、逐題、資料隔離 | HTML 歷史及 API 測試；其他使用者讀取結果／API 回 404，列表不含其紀錄 |
| ✅ 匯出／刪除、鍵盤焦點、錯誤提示、無 JavaScript | `test_export_and_account_deletion_include_new_answers_only_for_owner`；兩項真實瀏覽器測試及 HTML 錯誤提示測試 |

新增 Django 測試位置：`screening/tests/test_hhia_s.py`。瀏覽器測試位置：`e2e/main_flow.py` 的兩項 `test_adult_completes_hhia_s_*`。

## 測試與審查

- HHIA-S 整合測試：7 項通過（PostgreSQL）。
- 前端測試：12 個檔案、180 項通過；Vite build 通過，沒有新增前端套件或功能碼。
- 真實 Chromium：React 鍵盤操作／焦點、完全關閉 JavaScript 作答，2 項通過。
- 完整 Django 測試：571 項通過（PostgreSQL，50.734 秒）。
- 本次 Python 修改 Ruff 檢查通過；`git diff --check` 通過。模型欄位未變，不需新 migration。
- 全專案 Ruff 仍有 6 個先前文件整理造成的註解行寬問題：`audiogram_thumbnail.py` 及 `test_data_display.py`、`test_family_guide.py`、`test_layout.py`、`test_monitoring.py`、`test_pages.py` 各一處。本次不順手修改。
- Standards 審查：0 項；Spec 審查：0 項。兩位審查代理分別檢查 `git diff 1b3a311...8770022`，未執行資料庫測試。
- 舊測試以 HHIA-S 代表未知問卷的案例已改用測試專用 `unconfigured`，保留未知分級的回歸保護。
- 第一輪全套與瀏覽器測試曾因共用同一個 test_ 資料庫互相干擾，該輪結果作廢；後續改為依序執行。

## 本人實際驗收

尚未對本機真實資料庫執行新增問卷指令，也未啟停本機服務。若要本機操作，請先自行在已啟動的開發資料庫執行：

```bash
python manage.py seed_hhia_s
```

此指令會新增 HHIA-S 與十題；已存在 `hhia-s` 時不改資料。它不是修補已有問卷的工具。

1. 登入後從「開始篩檢」選 HHIA-S，確認年齡提示、來源及原題文字。
2. 選配戴狀態，十題都選「有時」，確認總分 20、輕至中度影響、成人建議及共通說明。
3. 從我的紀錄重新開啟，確認日期、配戴狀態、逐題回答；試鍵盤 Tab／方向鍵／空白鍵與上一題。
4. 關閉 JavaScript 再填一次，確認整份 HTML 表單仍能完成；漏答時有錯誤與題目連結。
5. 使用專門的假資料帳號驗證匯出與刪除，勿以真實帳號測試刪除。

自動測試未取代本人對臨床文字與實際使用感受的驗收。報告與家屬版整合依 #84 處理。

## 面試筆記（僅本機、不進版控）

新概念：只建立一次的初始化、測試程序的資源隔離。

- Q146：為何新增問卷不用固定資料編號？
- Q147：為何兩組資料庫測試同時執行會互相干擾？

紀錄：`docs/interview/development/planning/78-hhia-s.md`。
