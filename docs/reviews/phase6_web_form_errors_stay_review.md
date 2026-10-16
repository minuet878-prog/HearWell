# 審查報告：phase6_web_form_errors_stay

- 審查者：`reviewer` subagent（唯讀），2026-10-16
- 基準：`main`（變更尚未 commit）

## 結論

沒有「要修」的項目。規格五條驗收條件都有對應測試，而且斷言真的在驗那一條。Django 356、前端 139 全過。

## 各項檢查

1. **bug**：未發現。表單只會被 CSS `.answer-loading #answer-form` 藏起來，而加上 `answer-loading` 的行內腳本現在包在 `{% if use_react %}` 裡，驗證失敗頁的 HTML 沒有這段腳本。POST 的其他出口（成功、重複送出、`IntegrityError`）都是轉頁，不受影響。收據編號沿用同一個 `key`。IOI-HA 的 GET 與 POST 都是 `use_react=False`。
2. **多寫**：未發現。「只漏答助聽器題」的測試不屬於任何驗收條件，但測的是同一行為的另一種觸發方式，算合理補充。
3. **漏掉驗收條件**：五條都有測試（1、5 → `test_missing_answer_shows_errors_keeps_answers_and_no_react`；2 → `test_fixed_answers_save_once_under_the_same_key`；3 → `test_opening_the_page_still_loads_react`；4 → `test_ioi_ha_failed_submit_unchanged`）。
4. **做了「不做」的事**：未發現。frontend、styles.css 沒動；焦點移動只記進 roadmap。
5. **不可違反的規則**：未發現。沒有新查詢、沒碰計分、沒有新字級。

## 建議

- **[補測試（可選）]** 驗收 1 說「其他題已選的答案都還選著」，測試只檢查分數題，沒檢查「有沒有戴助聽器」（送出 `False`）重新顯示後還勾著。
- **[不改]** `WebFormErrorsStayTests` 用指定屬性的方式借用 `WebDoubleSubmitTests` 的輔助函式（避免繼承後重跑它的測試）。只是可維護性考量；檔內已有同樣寫法（`AnswerFlashTests`），抽 mixin 反而多一層。

## 主 session 查證與分類

| 項目 | 分類 | 理由 |
|---|---|---|
| 助聽器題答案保留沒有測試 | 補測試 | 屬於驗收 1 字面範圍；加一行斷言即可，成本極低 |
| 借用輔助函式的寫法 | 不改 | `AnswerFlashTests` 已用同一寫法，維持一致；不為一處加抽象層 |
