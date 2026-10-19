# Phase 4 規格：作答時竄改題數會 500

- **狀態**：已完成
- **分支**：`fix/answer-total-forms`
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-15

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

作答送出的資料被竄改時（多送、少送或清空某幾題的表單），網站一律回到作答頁並顯示錯誤，不會 500，也不會存下任何紀錄。

## 2. 範圍

### 要做
- 作答表單的每一份子表單都必須驗證，不允許「整份留空就算通過」。

### 不做
- 改動正常作答（沒有竄改）時的任何畫面或訊息。
- 改動錯誤訊息的文字。
- 新增 API 或改 DRF。
- 處理其他頁面的表單。

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 驗證留在 form 層（formset），不搬到 view（CLAUDE.md：作答驗證放在 form 層，DRF 才能共用）。

## 4. 行為描述

### 4.1 作答送出（`POST /questionnaire/<id>`）

| 情況 | 現在 | 改成 |
|---|---|---|
| 正常作答 | 存檔、轉到結果頁 | 不變 |
| 送出的表單份數比題數多（多出來的是空的） | **500**（`KeyError: 'question_id'`） | 回到作答頁，上方「表單資料有誤，請重新確認每一題的作答」，不存檔 |
| 某幾份表單整份清空（連題目編號都沒有），並把它們標成「新增的」 | **500** | 同上 |
| 送出的表單份數比題數少 | 回到作答頁「有題目沒有作答」 | 不變 |

## 5. 驗收條件

- [x] 1. 假設 10 題的問卷，當送出 10 題都答好、但份數竄改成 12（`TOTAL_FORMS=12`，多的 2 份是空的），則回 200、顯示「表單資料有誤，請重新確認每一題的作答」、沒有新增任何 Submission 或 Answer。
- [x] 2. 假設 10 題的問卷，當把 `INITIAL_FORMS` 竄改成 0、並把其中 1 份表單整份清空，則回 200、顯示同一句錯誤、不存檔。
- [x] 3. 正常作答（`INITIAL_FORMS` 與 `TOTAL_FORMS` 都等於題數）照常存檔並轉到結果頁；漏答時仍顯示「還有 N 題沒有回答」。
- [x] 4. 現有測試全部通過。

## 6. 待決問題

- [x] ~~被竄改時要顯示哪一句？~~ → 沿用現有的「表單資料有誤，請重新確認每一題的作答」

---

## 完成後回報（由 AI 填寫）

- **改了哪些檔案、為什麼**：
  - `screening/forms.py`：`BaseAnswerFormSet.__init__` 以 `form_kwargs` 設 `empty_permitted=False`，每張子表單都必須驗證。根本原因：index ≥ `INITIAL_FORMS` 的子表單 Django 預設可留空，空的就通過、`cleaned_data` 是空的，`clean()` 讀 `question_id` 時 `KeyError` → 500。
  - `screening/views.py`：「還有 N 題沒有回答」只算題目編號正常、分數沒填的題目；題目編號有錯的表單（被竄改）改顯示通用錯誤。
  - `screening/tests.py`：`TamperedAnswerTests`（6 個）。
- **驗收條件對應的測試**：
  1. `test_extra_empty_forms_are_rejected`
  2. `test_cleared_new_form_is_rejected`
  3. `test_normal_answers_still_saved`、`test_unanswered_question_still_pointed_out`
  4. 全部 130 個 Django 測試、27 個前端測試
  - 審查後補（回歸）：`test_fewer_forms_than_questions_still_rejected`、`test_question_from_another_questionnaire_rejected`
- **規格以外的決定**：
  - 實作時發現：修好後「整張清空」的表單會被算進「還有 N 題」，與規格的「表單資料有誤」不符 → 計數排除題目編號有錯的表單（本人同意）。
  - 被清空的那題下方仍顯示「這一題還沒有回答」（本人選 A：只有竄改者看得到、內容不算錯，不為此多寫邏輯）；測試只斷言上方沒有「還有 N 題」。
  - 審查實測 18 種竄改方式皆無 500、無錯誤存檔；份數超過 2000 時顯示 Django 內建訊息，屬修改前既有行為，不改。
- **這次用到的新概念**：formset 管理表單（`TOTAL_FORMS`／`INITIAL_FORMS`）、`empty_permitted`、`form_kwargs`、不信任隱藏欄位。
- **面試可能追問的 2–3 題**：Q40、Q41。要點見 `docs/interview.md`。
- **建議寫進 decisions/ 的內容**：見對話（由本人撰寫）。
