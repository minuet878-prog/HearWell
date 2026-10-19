# 實作計畫：作答頁不要先閃過全部題目

規格：`docs/specs/phase-05/phase5_answer_flash.md`　分支：`fix/answer-page-flash`

## 做法

關鍵是「藏表單」這件事要在**表單畫出來之前**就發生。React 的程式是 module script，要等整頁讀完才執行，來不及；所以改用一小段直接寫在頁面裡的 script（inline script），放在表單**前面**。瀏覽器讀到它就立刻執行，接著讀到表單時，表單已經是藏起來的狀態。

狀態只用一個記號：`<html>` 上的 class `answer-loading`。
- 有這個 class：CSS 藏起網頁表單，顯示「題目載入中…」
- 拿掉這個 class：網頁表單回來

## 改哪些檔案

1. **`screening/templates/screening/screening.html`**（只在 HHIE-S／HHIA-S，IOI-HA 不加）
   - 說明文字下方加 `<p id="answer-loading" role="status">`（`role="status"` 讓螢幕閱讀器唸出內容變化；沒開 JS 時是空的、不顯示）。
   - 緊接著一段 inline script（約 6 行）：
     - 給 `<html>` 加 `answer-loading`，把 `<p>` 的文字設成「題目載入中…」
     - 設 5 秒計時：時間到還在載入中 → 拿掉 class、清掉文字（網頁表單回來）
   - 沒開 JS：script 不執行，class 不存在，表單照常顯示（驗收 6）。

2. **`frontend/src/answer-main.jsx`**（React 的進入點）
   - 拿到題目時（`onReady`）：
     - 還在載入中 → 跟現在一樣藏表單，拿掉 class、清掉文字。
     - 已經不在載入中（5 秒已過、表單已顯示）→ 把 React 拆掉、不接手，網頁表單和已選的答案不動（驗收 5）。
   - 拿題目失敗（新的 `onFail`）：拿掉 class、清掉文字，表單立刻回來（驗收 3）。

3. **`frontend/src/AnswerApp.jsx`**：現在拿題目失敗時什麼都不做（`.catch(() => {})`），改成呼叫 `onFail`。只加這一行和一個 prop。

4. **`screening/static/screening/styles.css`**：兩條規則：`.answer-loading #answer-form` 不顯示；`#answer-loading` 空的時候不顯示、有字時字級用 `rem`。

## 測試（先寫、先確認失敗）

| 驗收 | 測試 |
|---|---|
| 1、4 | 前端：從 `screening.html` 取出那段 inline script，在 jsdom 裡執行，用假時鐘確認「加 class、出現文字」，以及「5 秒後拿掉、清空」 |
| 2、3、5 | 前端：準備好頁面元素、假的 `fetch`，載入 `answer-main.jsx`：拿到題目 → 表單藏、文字清；失敗 → 表單回來；先過 5 秒再拿到題目 → React 不接手、表單上已選的答案還在 |
| 1、7、8 | Django：HHIE-S 頁有 `role="status"` 的元素和 inline script，而且在表單前面；IOI-HA 頁沒有 |
| 6 | Django：表單本身沒有 `hidden`；CSS 只在 `.answer-loading` 底下藏表單 |

（jsdom 是在測試裡模擬瀏覽器畫面的工具。）

## 不會動的

一題一頁的作答流程、中途儲存、送出；IOI-HA；聽力圖。

## 取捨

- inline script 等於把一點邏輯放在 template 裡，不在 React 裡。這是必要的：只有它能在表單畫出來之前執行。內容只有加減 class 和計時，不含業務邏輯。
- 「5 秒」只寫在 inline script 一個地方。
