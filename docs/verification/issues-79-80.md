# #79／#80：SSQ12-TW 與年齡、用途推薦

日期：2026-10-19。規格：[#79](https://github.com/minuet878-prog/HearWell/issues/79)、[#80](https://github.com/minuet878-prog/HearWell/issues/80)。基準：已合併 #85 的 `4a4c358`。

狀態：功能、審查修正及完整測試完成；等待本人人工驗收。未 push、未開 PR、未合併 main，未對真實資料庫執行 migration 或初始化。

## 交付範圍

- SSQ12-TW 獨立十二題版本，延續只建立一次、不覆寫現有題目的初始化方式。
- React 分數尺、增減按鈕與明確不適用；預設刻度不當作回答，0 與不適用可從草稿恢復。
- 不適用以 `Answer.score = NULL` 保存；漏答不保存。資料庫擴充為 0–10 或 NULL，各問卷精確答案仍由共用表單限制，既有 HHI／IOI-HA 不接受新問卷的值。
- SSQ12 的平均只走 `Submission` 計分路徑，十二題皆有數值才相加除以十二，Decimal 四捨五入到小數一位。任何不適用均不算平均；全部不適用另說明沒有可用數值回答。
- 結果、歷史、API、匯出與帳號刪除包含新資料；不顯示分項、風險分級、效益及格線或長期趨勢。
- 已知出生年直接推薦 HHIA-S／HHIE-S；缺少出生年或差值恰為 65 時確認實際區間。已配戴者依目的直接選 IOI-HA／SSQ12／適齡 HHI。
- 保留自行選擇；非推薦年齡的 HHI 顯示提醒但不擋作答。未配戴 HHI 結果可選填 SSQ12，也能直接看紀錄。
- 中文用途在前、代碼在後；窄螢幕卡片文字獨占一行。修正字級放大時導覽最小寬度、頁尾 email 的水平溢出。

報告整合及配戴狀態比較仍留至 #82–#84；本次不把 SSQ12 當成傳統加總分級塞入既有本人／家屬報告。

## 原表核對

採[婦聯聽覺健康基金會 SSQ12-TW PDF](https://hh1314.org.tw/wp-content/uploads/2025/08/SSQ12-TW-基金會浮水印.pdf)，2026-10-19 下載，核對第 2、3 頁題目與尺規。SHA-256：`f2da563a0416b64b7872b52e3c12d0c65f388ad4947d45780b61844cb72200fd`。

- 第 9 題：混亂 → 分開；第 11 題：不清晰 → 清晰；第 12 題：非常專心 → 輕鬆做到。第 9、12 題不反向計分。
- HTML 與 API 共用 `Question.scale`，React 由 API 取得尺規文字。
- 網站 0 分說明依既有審定調整，保留原題與原始 PDF；不宣稱網站整數輸入、不適用規則已取得電子等效或高齡驗證。
- 使用條件沿用本人對 #77 的審定，未聲稱新增取得提供者回覆或授權。

## 驗收對照

以下勾選代表自動驗證有證據；本人操作確認仍待完成。

| 票 | 自動驗證完成 | 主要證據 |
|---|---|---|
| #79-1 | ✅ 未操作不算回答；0–10 整數或明確不適用，步距 1 | `AnswerApp.test.jsx` 的 SSQ12 兩項測試；輸入驗證整合測試；鍵盤分數尺 e2e |
| #79-2 | ✅ 保存實際配戴狀態、經驗不足可先不填、不強制兩種狀態 | HTML 提示、API／HTML 狀態測試 |
| #79-3 | ✅ 十二數值才平均；任一／全部不適用不算 0、不補分 | `test_twelve_numeric_answers_have_only_a_rounded_average`、`test_not_applicable_is_not_zero_in_api_history_and_export` |
| #79-4 | ✅ 正確特殊錨點及 0 分說明，無反向／分項／分級／趨勢 | 原表視覺核對、API 錨點測試、平均／結果／歷史測試、e2e |
| #79-5 | ✅ 75／76 → 6.3；0／不適用／漏答不混淆 | 平均、輸入、HTML、草稿與公開 API schema 測試；e2e 零分及不適用恢復 |
| #79-6 | ✅ 舊限制不變，匯出／刪除／權限與無障礙 | SSQ12 隔離／刪除測試；既有 HHI／IOI 作答回歸；無 JS 與鍵盤 e2e |
| #80-1 | ✅ 一般直接推薦；未知與 65 歲邊界確認 | 18／30／64／66／80 歲與未知／65 歲整合測試；已知出生年不受網址參數覆寫 |
| #80-2 | ✅ 三種已配戴目的可直接進入，其他目的不需先確認年齡 | `test_all_purposes_are_direct_links_even_without_confirmed_age`、推薦 e2e |
| #80-3 | ✅ 未配戴 HHI 結果可選填 SSQ 或直接看紀錄 | `test_nonrecommended_hhi_stays_available_and_unaided_result_offers_ssq` |
| #80-4 | ✅ 非推薦問卷仍可填、適用提醒、中文用途優先 | 自由選擇整合測試及既有卡片測試更新 |
| #80-5 | ✅ 鍵盤、上一頁、無 JS、320px 放大字級不撐寬 | `test_age_confirmation_and_purpose_links_without_javascript`；SSQ12 分數尺／焦點 e2e；手機截圖檢視 |

## 驗證與審查

- #79 與既有作答回歸：102 項通過。
- 審查補修後 SSQ12／推薦／API：61 項通過。
- 完整瀏覽器回歸：21 項通過；其中新增 3 項涵蓋 SSQ12、無 JS、推薦與手機放大，審查補修後三項再次通過（10.943 秒）。
- 最後完整 Django：584 項通過（PostgreSQL，52.947 秒）；前端：12 檔、182 項通過。
- OpenAPI `--validate --fail-on-warn` 通過；Vite build 通過；完整 `ruff check .` 與 `git diff --check` 通過。沒有 TypeScript 或獨立 typecheck 指令；沒有額外引入型別檢查套件。
- Standards 軸：無強制規範違反；尺規 mapping 重複的建議已改善。Spec 軸：無發現。
- 審查另指出 Answer.score schema 仍為舊 enum、scale 被列為必要欄位；補公開 schema 測試先看失敗，再修正宣告，重新產生 OpenAPI。審查者已複核問題解決。
- 既有固定 HHIE-S 提示、代碼優先文案的測試，依 #80 新規格更新，保留原有卡片內容、連結與提示位置測試目的。

## 本機人工驗收

資料庫與開發伺服器由本人操作。以下會新增 schema 與問卷資料，尚未由代理在真實資料庫執行：

```bash
python manage.py migrate
python manage.py seed_hhia_s
python manage.py seed_ssq12
npm run build --prefix frontend
```

1. 使用有出生年的假帳號：18–64 歲推薦 HHIA-S，66 歲以上推薦 HHIE-S；65 歲差值及未填出生年才詢問區間。仍可自行進入另一份 HHI。
2. 未確認年齡時，直接選「了解目前聆聽能力」或「了解助聽器的幫助」，確認不用先回答年齡；選生活影響時推薦適齡 HHI。
3. 填 SSQ12：未操作不能前進；可選 0、10、不適用，增減每次 1 分；返回、重新整理可恢復。確認第 9、11、12 題尺規。
4. 十二題皆選 6，結果平均 6.0；十一題 6、最後一題 9 或 10，兩種平均皆 6.3。任一不適用只顯示逐題結果與原因。
5. 我的紀錄可找回 SSQ12，無分級及趨勢；下載資料可分辨 0 與 null。不在真實帳號上試刪除。
6. 未配戴狀態完成 HHI，結果可選填 SSQ12 或看紀錄；手機、字級放大及關閉 JavaScript 都能使用。

回退限制：新答案若已有 6–10 或 null，不可直接反向 migration 恢復舊的 0–5／不可空約束；須先規劃保留資料的處理方式，不可刪除使用者作答來讓回退通過。

## 面試筆記（不進版控）

新增概念：三態作答、十進位四捨五入、OpenAPI 契約。題號 Q148（三態作答）、Q149（四捨五入）、Q150（API 契約），開發紀錄為 `docs/interview/development/planning/79-80-ssq12-guidance.md`。
