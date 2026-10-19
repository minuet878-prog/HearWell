# Phase 6-4 網頁版作答連按兩次：審查報告

- 規格：[phase6_web_double_submit.md](../../specs/phase-06/phase6_web_double_submit.md)
- 比對：`git diff main...fix/web-answer-double-submit`（＋規格打勾）
- 審查：`reviewer` subagent（2026-10-16）；結論：符合規格，沒有中高嚴重度問題；驗收 1–12 都有有效測試；本機 Django 350、前端 139 通過

| # | reviewer 意見 | 嚴重程度 | 主 session 查證 | 分類 |
|---|---|---|---|---|
| 1-1 | `except IntegrityError` 之後直接找「同一編號」那筆，沒確認真的找得到：編號是 None 時會變成 `IS NULL`，撈到這個人一筆不相干的舊紀錄（還帶「剛才已經送出」說明）；找不到時 `None.id` → 500，蓋掉真正的錯誤 | 低 | 屬實（讀 `views.py` 第 170–173 行）。目前 Submission／Answer 的其他限制（例如同一份作答同一題只能一筆）已在表單驗證擋掉，所以現在觸發不到；但以後加限制就會誤導 | 要修：找不到先存的那筆（含編號是 None）就把原本的錯誤丟出去；補測試 |
| 1-2 | 驗證沒過、編號是 None 時，隱藏欄位輸出字面 `"None"` | 很低 | 屬實；下次送出解析失敗又變 None，行為仍符合規格（照舊存、不防重複） | 不改 |
| 2 | `layout.html` 全站顯示 messages；從 `api.views` 匯入 `_find_by_key` | — | 唯一呼叫 messages 的是這次的 `_already_sent`；重用既有函式 | 不改 |
| 3 | `test_submit_feedback_markup` 沒測 hhia-s；vitest 的 pageshow 監聽器累積 | 很低 | 同一份模板；舊監聽器只碰已移除的節點 | 不改 |
| 5 | 把 A 問卷頁的編號竄改後 POST 到 B 問卷網址，會轉到 A 那筆 | 很低 | 只查本人紀錄，不越權；只有竄改才會發生 | 不改 |
