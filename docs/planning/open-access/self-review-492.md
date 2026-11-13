# #492 自審（2026-11-13）

範圍：`git diff origin/main...HEAD`（基準點 2a6632a），分支 `feat/492-guest-screening`，36 個 commit、66 個檔案。兩條線分開審：規範（`CODING_STANDARDS.md`、`AGENTS.md`、`test_standards.py`，加 Fowler 壞味道基準）與規格（#492、#493–#500、設計圖選定與實作中補的決定）。

## 規範

**明文規範：沒有硬性違規。** 第 1、2、6（例外內）、9、14、16、18、24 條都符合。

| # | 項目 | 位置 | 判定 |
|---|---|---|---|
| S1 | 第 23 條：清除確認整塊淡紅底，紅色例外原本只寫「按鈕」 | `frontend/src/site.css` `.guest-clear-confirm` | 不改也可（要不要在規範上補寫） |
| S2 | Duplicated Code：`part` 與 `span`、`tile` 與 `askTile` 拼同一種分數磚 | `guest-home.js:9,16`、`guest-results.js:236,245` | 建議 |
| S3 | Duplicated Code：`loadGuestResults` 對每個鍵呼叫 `loadGuestResult`，清過期跑 n 次 | `guest-results.js:62,73` | 建議 |
| S4 | Data Clumps：請求內容與帶 CSRF 的 POST 標頭組了三次 | `guest-results.js:140,198`、`AnswerApp.jsx:277` | 建議 |
| S5 | Refused Bequest：`GuestAnswersSerializer` 拿掉 `norm_token`、`from_guest` | `serializers.py:305-310` | 不改也可 |
| S6 | Repeated Switches：「是不是訪客」都靠 `submission.pk` | `results.py:130,186`、`graded_result.html:27,69` | 建議（給一個 `is_guest` 之類的屬性） |
| S7 | 依賴方向：API 從頁面模組匯入 `TREND_STATUS_TEXT` | `api/views.py:34` | 建議（搬到 `scoring.py` 或 model 層） |
| S8 | Primitive Obsession：`count_guest("completed"/"saved")` | `guest_counts.py:21` | 不改也可 |
| S9 | Mysterious Name：`attrs["scored"]` 裝的是還沒計分的（題目, 分數） | `serializers.py:323` | 不改也可 |
| S10 | Divergent Change：路由判斷 `asks_about_guest_results` 放在顯示用 filter 檔 | `custom_filters.py:22` | 不改也可 |

## 規格

34 條驗收：31 條有真的在驗行為的斷言，3 條只證明一部分（19、22、28）。沒有範圍蔓延（I3、I4、首頁兩份標題、訪客不顯示 SSQ12 選填都有出處）。完整對照表在本人對話紀錄，結論如下。

| # | 項目 | 位置 | 判定 |
|---|---|---|---|
| P1 | 驗收 19：首頁那一半（過期的結果首頁看不到、瀏覽器刪掉）沒有測試 | `guest-home.test.js` | 建議（補測試） |
| P2 | 驗收 28：e2e 只查 localStorage，沒查首頁畫面上那一塊有出現 | `e2e/main_flow.py:14305` | 建議（補斷言） |
| P3 | 瀏覽器完全關掉 JavaScript：訪客看到網頁表單，送出後被帶去登入，答案不見 | `screening.html:57,63`、`answering.py:321-325` | 建議（`<noscript>` 提示，或訪客的表單預設隱藏） |
| P4 | 驗收 22「日期是保存那天」的斷言分不出作答日與保存日（程式本身是對的） | `test_guest_save.py:250` | 不改也可 |
| P5 | 已登入的人也打得到只算分入口，送 `just_finished` 會讓「訪客完成」加一 | `api/views.py:189` | 不改也可（規格接受數字不精確） |
| P6 | 「不用登入的健康資料頁面」名單是手寫的 | `test_standards.py:494` | 不改也可（規格要的就是一份名單） |

## 實作代理回報、審查也點到的

| # | 項目 | 位置 | 判定 |
|---|---|---|---|
| B1 | **bug**：存訪客結果沒看成功與否，存不進去（例如作答途中儲存空間滿了）照樣跳到結果頁，結果頁讀不到就回首頁，答案不見、沒有提示。根本原因：`saveGuestResult` 的回傳值沒被檢查 | `AnswerApp.jsx:296` | 要修（等本人同意）：存失敗時留在作答頁，顯示 I4 那句話 |
| B2 | 詢問頁按「要，存進這個帳號」後，焦點留在已隱藏的按鈕上；保存卡出發的保存頁也沒處理焦點 | 保存頁 | 建議（無障礙：焦點移到「正在保存」那一行） |
| B3 | 已同意的人打開隱私權說明、家人專區、問答小助手、帳號設定時不會被轉去詢問，回首頁或進其他頁才問 | `custom_filters.py` | 不改也可（判斷同意狀態每頁要多一次查詢） |
| B4 | 詢問頁按「不要」後回首頁，不回原本要去的頁；轉址前會先閃一下原本的頁 | `guest-ask.js` | 不改也可 |

## 本人決定（2026-11-13）

交叉審查前修：B1、B2、P3、P1、P2、S3、S6、S7、S9。其餘（S1、S2、S4、S5、S8、S10、P4–P6、B3、B4）這次不改。
