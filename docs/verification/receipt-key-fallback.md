# 沒有 crypto.randomUUID 時作答頁變成整張表單

分支 `fix/random-uuid-fallback`（從 `main` 開出），2026-11-12。不碰計分、門檻、資料或權限，不需要交叉審查。

## 問題與根本原因

- 本人在全站改版驗收時，用 iPhone 連 `http://172.20.10.2:8001`，作答頁一打開就是所有題目的整張表單，不是一題一頁；同一支 iPhone 開正式站（https）正常。
- 作答程式在第一次畫題目時呼叫 `crypto.randomUUID()` 產生防重複送出的代碼（Idempotency-Key）。這個功能只在安全連線（https、localhost）下有，iPhone 要 iOS 15.4 以後才支援；沒有時呼叫就出錯，作答程式放棄，留下 Django 表單。
- 重現：用 Playwright 的 WebKit 模擬 iPhone 13 打開作答頁，正常；把 `crypto.randomUUID` 拿掉後，第 1 秒就是整張表單，錯誤是 `Cannot destructure property 'step' from null or undefined value`。（試驗用的測試檔查完已刪除。）
- 同一個原因也在聽力圖輸入頁（`AudiogramApp.jsx`）。正式站使用者只有 iOS 15.0–15.3 的舊 iPhone 會遇到。

## 修正

- 新增 `frontend/src/receipt-key.js`：有 `randomUUID` 就用它，沒有時用每個瀏覽器都有的 `crypto.getRandomValues` 做出第 4 版 UUID。作答頁與聽力圖輸入頁改用它。

## 測試

- 先寫測試看它失敗，再修：
  - `receipt-key.test.js`：有 `randomUUID` 時用它；沒有時 50 次都是不重複的第 4 版 UUID。
  - `AnswerApp.test.jsx`「without crypto.randomUUID」：照樣一題一頁、送出時帶代碼（修前：作答程式沒準備好）。
  - `AudiogramApp.test.jsx`「opens and saves without crypto.randomUUID」：照樣存檔（修前：`crypto.randomUUID is not a function`）。
- 前端 400 個通過、建置成功、e2e 374 個通過（`--parallel 4`）。

## 本人驗收

- 2026-11-12 本人用 iPhone 連預覽（http 區網位址），作答頁回到一題一頁。✅
