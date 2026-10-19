# Phase 2 規格：B1 助聽器配戴標記

- **狀態**：已完成
- **分支**：`feat/hearing-aid-flag`
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-14

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

使用者每次作答時，標記這次有沒有戴助聽器；結果頁和歷史紀錄都看得到這個標記。之後才能比較配戴前後的分數（B2 趨勢圖會用到）。

## 2. 範圍

### 要做
- 作答頁在第一題之前加一題：「這次填答時，您有沒有戴助聽器？」，選項是「有戴」和「沒戴」，不預選，必填。
- 送出時，標記跟作答一起存下來。
- 結果頁和歷史紀錄的每一筆都顯示「助聽器：有戴」「助聽器：沒戴」或「助聽器：未記錄」。

### 不做
- 讓標記影響計分或分級。
- 送出之後修改標記。
- 歷史紀錄依標記篩選或分組。
- 趨勢圖（B2）。
- API。
- 回填舊資料（舊紀錄維持「未記錄」）。
- 修正作答頁說明文字的錯字（屬於 Phase 2 補回四項中的「錯字」那項）。
- 改動 admin 的唯讀規則。

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本 phase 特別注意：
  - 結果頁只能看自己的紀錄（IDOR，第 8 條）。
  - 「沒戴」和「未記錄」是兩種不同的狀態，不能用同一個值表示（同第 11 條的精神）。
  - 新文字的字級用 `rem`；對比要達 WCAG AA，不用 `text-muted`。

## 4. 行為描述

### 4.1 作答頁

| 項目 | 內容 |
|---|---|
| 網址與方法 | 既有作答頁，GET 顯示、POST 送出 |
| 誰可以使用 | 未登入：導向登入　　已登入：可以　　能否存取他人資料：不適用 |
| 回傳／顯示的欄位 | 第一題之前顯示「這次填答時，您有沒有戴助聽器？」，兩個選項「有戴」「沒戴」，不預選 |
| **不能**回傳／顯示的欄位 | 無 |
| 需要計算的資料 | 無（標記不計分） |
| 空資料時的行為 | 沒選助聽器題 → 不存，顯示錯誤訊息，已選的答案仍保留 |

### 4.2 結果頁

| 項目 | 內容 |
|---|---|
| 網址與方法 | 既有結果頁，GET |
| 誰可以使用 | 未登入：導向登入　　已登入：只能看自己的　　能否存取他人資料：不行，回 404 |
| 回傳／顯示的欄位 | 原有內容 ＋「助聽器：有戴／沒戴／未記錄」 |
| **不能**回傳／顯示的欄位 | 無 |
| 需要計算的資料 | 由誰計算：後端　　計算路徑：分數與分級不變，沿用 `Submission` 的計分方法 |
| 空資料時的行為 | 舊紀錄沒有標記 → 顯示「助聽器：未記錄」 |

### 4.3 歷史紀錄

| 項目 | 內容 |
|---|---|
| 網址與方法 | 既有歷史頁，GET |
| 誰可以使用 | 未登入：導向登入　　已登入：只列自己的　　能否存取他人資料：不行 |
| 回傳／顯示的欄位 | 每一筆原有內容 ＋「助聽器：有戴／沒戴／未記錄」 |
| **不能**回傳／顯示的欄位 | 無 |
| 需要計算的資料 | 同結果頁 |
| 空資料時的行為 | 沒有任何紀錄 → 維持原本的「你還沒有做過篩檢紀錄」；舊紀錄 → 「助聽器：未記錄」 |

## 5. 驗收條件

- [x] 1. 假設已登入，當開啟作答頁，則第一題之前出現助聽器題目，有「有戴」「沒戴」兩個選項，而且都沒有預選。
- [x] 2. 假設所有題目都答了，並選「有戴」，當送出，則存下一筆紀錄，結果頁顯示「助聽器：有戴」。
- [x] 3. 假設所有題目都答了，並選「沒戴」，當送出，則存下一筆紀錄，結果頁顯示「助聽器：沒戴」。
- [x] 4. 假設所有題目都答了，但助聽器題沒答，當送出，則不存任何紀錄，頁面顯示錯誤訊息，已選的答案仍保留。
- [x] 5. 假設助聽器的值被竄改成非法值，當送出，則不存任何紀錄，頁面顯示錯誤訊息。
- [x] 6. 假設有一筆沒有標記的舊紀錄，當開啟結果頁和歷史紀錄，則都顯示「助聽器：未記錄」。
- [x] 7. 假設有三筆紀錄（有戴、沒戴、未記錄），當開啟歷史紀錄，則每一筆各自顯示正確的標記。
- [x] 8. 假設兩次作答的答案完全相同，只差在有戴和沒戴，則總分和分級都一樣。
- [x] 9. 假設使用者 A，當開啟使用者 B 的結果頁，則回 404（沿用既有測試，確認仍然通過）。

## 6. 待決問題

- [x] ~~選項有幾個？~~ → 兩個：有戴／沒戴
- [x] ~~必填嗎？~~ → 必填
- [x] ~~放在作答頁哪裡？~~ → 第一題之前
- [x] ~~顯示在哪些頁面？~~ → 結果頁＋歷史紀錄
- [x] ~~題目文字？~~ → 「這次填答時，您有沒有戴助聽器？」
- [x] ~~舊資料怎麼顯示？~~ → 「助聽器：未記錄」

---

## 完成後回報（由 AI 填寫）

- **改了哪些檔案、為什麼**：
  - `screening/models.py`、`migrations/0014_submission_wearing_hearing_aid.py`：`Submission.wearing_hearing_aid = BooleanField(null=True, choices=…)`，`None` 代表舊紀錄「未記錄」，跟「沒戴」分開。
  - `screening/forms.py`：新增 `HearingAidForm`（必填、`TypedChoiceField` 轉布林、統一錯誤訊息），驗證放在 form 層。
  - `screening/views.py`：作答頁傳入助聽器表單；兩個表單都通過才建立 Submission。
  - `screening.html`、`result.html`、`my_hearing.html`：作答頁第一題前加題目；結果頁、歷史頁顯示「助聽器：…」（`fs-4 text-body-emphasis`）。
  - `screening/tests.py`：新增 `HearingAidTests`；既有兩個 POST 測試補上助聽器欄位。
  - `docs/roadmap.md`：B1 打勾；無障礙基準線補上審查發現的兩點。
- **驗收條件對應的測試**（都在 `HearingAidTests`，條件 9 除外）：
  1. `test_question_shown_before_first_question_without_default`
  2. `test_wearing_saved_and_shown_on_result`
  3. `test_not_wearing_saved_and_shown_on_result`
  4. `test_missing_answer_rejected_and_answers_kept`（另有反向情境 `test_hearing_aid_choice_kept_when_answer_missing`）
  5. `test_tampered_value_rejected`
  6. `test_unrecorded_submission_shows_unrecorded`
  7. `test_history_shows_each_status`
  8. `test_status_does_not_change_score`
  9. `SubmissionResultAccessTests.test_user_cannot_view_others_submission`（既有）
  - 另有 `test_new_text_uses_readable_style` 守字級與對比的 class。
- **規格以外的決定**：
  - `pyproject.toml` 的 `allowed-confusables` 加上全形「：」，否則 Ruff RUF001 會把「助聽器：有戴」當成可疑字元。
  - 一度用 `all([...])` 強迫兩個表單都驗證，實測發現 Django 表單的 `errors` 會 lazy 觸發驗證，`and` 就夠，改回 `and`。
- **這次用到的新概念**：三態布林（`BooleanField(null=True)`）、`get_FOO_display()`、`TypedChoiceField` ＋ `coerce`、Django 表單的 lazy 驗證、「故意弄壞」驗證測試、斷言 context vs 斷言 HTML。
- **面試可能追問的 2–3 題**：Q14（為什麼 `null=True` 不用 `default=False`）、Q15（`and` 短路為什麼錯誤訊息還在）、Q16（斷言 context 為什麼太鬆）。要點見 `docs/interview.md`。
- **建議寫進 decisions/ 的內容**：見對話（由本人撰寫）。
