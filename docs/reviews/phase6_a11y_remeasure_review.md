# 審查：無障礙基準線重新量測（`chore/a11y-remeasure`）

- 規格：[`docs/specs/phase6_a11y_remeasure.md`](../specs/phase6_a11y_remeasure.md)
- 審查：`reviewer` subagent（2026-10-16），比對 `main` ＋ 未 commit 的變更
- 查證與分類：主 session

## 審查發現與查證

| # | 發現 | 嚴重 | 查證 | 分類 |
|---|---|---|---|---|
| 1 | `screening.html` 錯誤摘要上方的 `{# … #}` 跨兩行，Django 不當註解，整段英文顯示在頁面上 | 高 | 已重現：`Template('A{# one\n two #}B')` 輸出原文。追加修改（連結改指向整題）時把註解改成兩行造成；修後重量只截了跳轉後的畫面，沒看頁首 | 要修＋補測試 |
| 2 | 通用錯誤（表單被竄改）時 `message` 是 `ErrorList`，輸出 `<ul>`，包在新加的 `<p>` 裡變成不合法的 `<p><ul></ul></p>`，瀏覽器會多出空段落 | 低 | 已重現：渲染結果 `<p class="mb-2"><ul class="errorlist nonform">…</ul></p>` | 要修（一行） |
| 3 | 報告 5.2「320 px」寫「錯誤狀態沒量」但沒寫原因（驗收 1） | 低 | 屬實 | 要修（文件） |
| 4 | `role="alert"` 用在載入時就存在的內容，部分讀屏可能不唸或唸兩次；有 `autofocus` 移焦點，實際會唸 | 參考 | 規格「不做」排除讀屏實機測試，驗收 10 以 axe 為準 | 不改（之後讀屏實機測試時確認） |

## 審查確認沒問題的部分

- 題號連結與 `fieldset id` 走同一份 `question_form`（view `enumerate(start=1)`、模板 `forloop.counter`）。
- IOI-HA 沒有助聽器題、被竄改的表單仍走通用錯誤、登入頁只在失敗時加標記。
- 沒有多寫、沒碰「不做」清單；不可違反規則皆符合。
- 驗收 7 只能用 `<wbr>` 的單元測試加報告 5.5 的手動重量證明（版面量測單元測試做不到）：不改。

## 測試

- Django 387 通過、前端 139 通過（審查時）。

## 修正結果（2026-10-16）

- 1：註解改成 `{% comment %}`；新增 `test_no_template_comment_leaks_onto_the_page`（修前失敗、修後通過）。瀏覽器確認頁首不再出現註解。
- 2：通用錯誤改回直接放在摘要 `<div>` 裡，只有漏答時才用 `<p>`＋連結；新增 `test_generic_error_list_is_not_inside_a_paragraph`（修前失敗、修後通過）。
- 3：報告 5.2 補上原因；作答錯誤頁補量 320 px（5.5）。
- Django 389 通過、`ruff check` 通過。
