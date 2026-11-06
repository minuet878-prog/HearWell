# 家人專區第二批（#426，票 #430–#432）

日期：2026-11-06。分支：`feat/426-family-zone-batch-2`。規格：[#426](https://github.com/minuet878-prog/HearWell/issues/426)；拷問決定：[family-zone](../planning/family-zone/grill-decisions.md)；審字清單：[第二批文字](../planning/family-zone/batch-2-wording.md)。

狀態：自動測試、自審、交叉審查都完成。**本人審字與操作驗收還沒做**，所以驗收條件「文字由本人審過」還不算通過。第三批（#433–#435）還沒開始，母規格 #426 繼續開著。

## 本人決定

1. 頁面用 B 案：清單在 `/family/visits`，補助檢核和期限試算各一頁（Q15）。
2. 補助檢核的題目與規則照草稿（Q16）。清單的問題改用「他」（Q17）。期限試算的未來日期顯示錯誤（Q18）。
3. 清單與兩個結果都放「列印或存成 PDF」；`/family/visits` 加不留存標記。
4. 結果不自相矛盾（Q19）：有還缺時不列去申請和購買請款；已滿年限改成「如果」的句子；九號表已過期時拿掉「請在這天以前到公所申請。」。
5. 隱私權修訂日期跟著小修改成 2026/11/06，和票上「其餘文字不變」字面上不同，本人同意（ADR 0014）；同意書版本不變。
6. 做交叉審查（`OPEN_PAGES` 多三個頁面，屬於 `AGENTS.md` 的權限改動）。

本人同意草稿後，代理發現「已買、沒有核定通知、有九號表」會同時出現「可以去申請」和「沒核定就先買的不補助」，改成不列第 3 題的還缺和下一步。這條列在審字清單請本人確認。

## 做了什麼

- `/family/visits`：12 項可勾選的清單，不送出、不儲存，可列印；專區首頁加入口卡。
- `/family/visits/subsidy`：五題 POST 表單，列出還缺、要先確認、提醒和下一步。規則在 `screening/subsidy_check.py`，不碰 request 和資料庫。
- `/family/visits/deadlines`：輸入日期算期限，二十五號表起訖與選配路線共用 `form_25_window`。
- 九號表章、二十五號表章各加一行連結；隱私權 cookie 句改成「只用登入和送出表單需要的 cookie」。

## 驗收條件

| 條 | 驗收 | 結果 | 證據 |
|---|---|---|---|
| 11 | 清單勾選列印、重新整理不留下、不存 | 通過 | e2e `FamilyVisitsTest`、`test_viewing_it_writes_nothing_and_sets_no_cookie` |
| 12 | 列出還缺，不出現「符合」「可領」「一定拿得到」 | 通過 | `test_family_subsidy_check.py` 720 組窮舉 |
| 13–19 | 補助檢核各類結果 | 通過 | `test_family_subsidy_check.py` 各條案例 |
| 20 | 漏題留同頁、已選還在、焦點到摘要 | 通過 | `test_family_subsidy_check.py`、e2e `FamilySubsidyCheckTest` |
| 21 | 答案不在網址、資料庫不變、不可快取、不讀 `request.user` | 通過 | 兩個測試檔與 e2e；不讀 `request.user` 只檢查 view 原始碼，因為版面本身會讀登入狀態 |
| 22–27 | 期限試算（月底、只填一個、已過、不合法） | 通過 | `test_family_deadlines.py`、e2e `FamilyDeadlinesTest` |
| 28 | 兩章原文不變、多一個連結、寫「申請的人」 | 通過 | `ReviewedPagesTests`（基準來自這批之前的 `main`）、兩個測試檔 |
| 29 | 結果列印完整，不含導覽和頁尾 | 通過 | e2e `FamilySubsidyCheckTest`、`FamilyDeadlinesTest` |
| 36 | 手機 200% 不左右捲，44px，1rem | 通過 | 三個 e2e 類別 |
| 37 | 唯一主標題、回專區、分頁標在了解、不用登入 | 通過 | 三個測試檔 |
| 38 | 文字與出處由本人審過 | **未完成** | 等本人審字 |

逐條對到 `檔案:行號` 的版本在[交叉審查留言](https://github.com/minuet878-prog/HearWell/issues/426#issuecomment-6678702579)。

## 自動測試

併入 `main` 後，在 `afcda00` 上跑，每個都用結束碼確認：

- Django：1783 項通過。
- e2e：321 項通過。
- 前端：371 項通過。
- Ruff：`ruff check .`、`ruff format --check .` 都通過。

## 自審

Standards 與 Spec 兩軸在合併後各跑一次。修掉：過時註解、重複的出處區塊與期限數字、三個行內連結的觸控高度、寫死的同意書版本、文件表格斷開；自相矛盾的結果由本人決定後修（Q19）。

刻意不修：試算錯誤摘要的「欄位名稱：錯誤訊息」（`hhi_comparison.html` 有同樣寫法）；`nav_learn.html` 和 `OPEN_PAGES` 每加一頁都要改（現有做法）。

## 交叉審查

Codex 審，基準 `origin/main`，結果[留言在 #426](https://github.com/minuet878-prog/HearWell/issues/426#issuecomment-6678702579)。一項要修：三頁原文不變沒有真正驗證的斷言。修在 `97069dd`，Codex 複核後不再算要修（逐行模擬刪改 884 次都讓測試失敗）。

## 已知限制

- `ReviewedPagesTests` 讓這三頁以後改字時測試會失敗，要本人審過再更新基準；第二批上線後可以再決定要不要留。
- Playwright 的 Chromium 關掉往返快取，所以「按上一頁看不到勾選」只驗得到 `no-store` 標頭和 `autocomplete="off"`，不保證每種瀏覽器都擋得掉。
- 實際朗讀沒有自動測試。
- 查核日期沿用指引，這次沒有重查法規。
- 沒有操作真實資料，也沒有新增 migration。
