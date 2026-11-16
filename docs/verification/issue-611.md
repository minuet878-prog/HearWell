# #611 填寫時的七個小幫手

日期：2026-11-16。分支：`feat/611-filling`（從 `590dec54` 開）。規格 [#611](https://github.com/minuet878-prog/HearWell/issues/611)，票 #613（設計圖）、#614（J2 信箱打錯提醒）、#615（J4 出生年顯示幾歲）、#616（N3 鍵盤「下一個」）、#617（K1 大字讀數）、#618（K2 看示範）、#619（R1 漏標提醒）、#620（Q2 安心話）。依據：[拷問決定與選定表](../planning/redesign/interaction-grill-decisions.md)、[設計圖](../planning/redesign/mockup-613-filling.html)。

狀態：自動測試全過，**等本人實際操作驗收**。

- 本人在設計圖選定（2026-11-16）：J2 A、J4 A、N3 照表、K1 B（兩排）、K2 符號跟著耳朵、R1 A、Q2 A＋甲。
- 不需要交叉審查：沒改計分、分級、門檻，沒有 migration，沒碰權限（N3 在登入頁加了鍵盤行為，沒動登入的驗證）。
- 第 4 步自審用 `/mattpocock-skills:code-review`（基準 `origin/main`）：Standards 沒有硬性違規；Spec 找到 1 項要修（J2「不問」清單太寬），已修。本人另選了 4 項判斷題一起修（示範圖小字列為例外、共用格線、改四個名稱、表單兩個設定合一）。
- 沒有操作真實資料。測試都在臨時測試資料庫上。

## 行為

| 項目 | 現在 |
|---|---|
| J2 信箱打錯（#614） | 註冊、用 LINE 取名稱、忘記密碼三頁：離開信箱欄時，@ 後面跟 7 個常見網域只差一兩個字，下面問「您是不是要打 ○○？」＋外框按鈕「按這裡改」。不擋送出，只在瀏覽器比對。用 Google 取名稱沒有 |
| J4 幾歲（#615） | 註冊、用 LINE／Google 取名稱三頁：出生年綠勾出現時，正下方綠色「今年滿 76 歲」。「今年」由伺服器給，算法跟帳號年齡一樣 |
| N3 下一個（#616） | 註冊、登入、用 LINE／Google 取名稱、設新密碼：最後一欄以外，手機鍵盤那顆鍵寫「下一個」，按了跳下一欄、不送出。聽力圖日期年 → 月 → 日，「日」照舊不做事。單欄表單、日期選擇器不動 |
| K1 大字讀數（#617） | 標右耳、標左耳兩步，圖的正上方一塊：還沒標寫「點一下圖來標記」；標了寫兩排，上面符號名稱、下面「1000 Hz　45 dB」，拖動時跟著變，放開才念給讀螢幕軟體。圖不會跳 |
| K2 看示範（#618） | 「怎麼標記」裡一張小示範圖＋外框按鈕「▶ 看示範」：按了約 2 秒，手指點 1000 Hz、45 dB，符號出現，停在最後一格，按鈕變「↺ 再看一次」。標右耳示範 ○、標左耳示範 ✕ |
| R1 漏標提醒（#619） | 確認存檔那一步，兩耳氣導標的頻率不同時，淡灰提示框寫「左耳沒有標 2000、4000、8000 Hz。報告上本來就沒有的話，直接存檔就好。」不擋存檔 |
| Q2 安心話（#620） | 作答頁第一個畫面題數下面，灰字：登入的人兩句「這不是考試，沒有對錯。答到一半離開，答案會留在這支手機，7 天內回來可以接著答。」；訪客和退回整頁表單的人只有第一句。過了第一個畫面收起來 |

跟規格或設計圖不一樣、或規格沒寫到的地方（請本人驗收時一起看）：

1. **K1 這一塊一直預留最長讀數的高度**，所以圖永遠不跳。一般字級看起來跟設計圖一樣；320px 寬、字放大 200% 時，還沒標點的提示那一塊也約四行高（設計圖畫的是讀數長了才變高）。
2. **K2「減少動態效果」時整塊示範和按鈕都不出現**（規格只寫沒有按鈕）。本人 2026-11-16 選定。ADR 0060 補一句、`CODING_STANDARDS.md` 第 22 條補上（本人選定不另開 ADR）。
3. **K2 示範圖刻度字約 0.7rem**，列進小字例外（`OWNER_KEPT`、`CODING_STANDARDS.md` 第 16 條）。本人 2026-11-16 選定：示範圖讀螢幕軟體跳過，重點是手指和符號。
4. **J2「不問」的 Yahoo 地區**只認 hk、sg、au、my、ph、vn、br、mx、ar 九個（設計圖原本寫「等其他地區」）。本人 2026-11-16 選定（自審發現原本的寫法讓 yahoo.com.wt 這種打錯也不問）。
5. **J2 的按鈕在 390px 寬排在問句下一行**，不是同一行旁邊：放不下，設計圖 A 也是這樣排。
6. **J4 讓 LINE、Google 取名稱兩頁也有綠勾**，連帶有「綠勾出現就收掉伺服器的出生年錯誤」，跟註冊頁一樣。
7. **驗收 67**：SADL、IOI-HA 一開頭就是第 1 題、選項多，「下一題」在加安心話之前就不在 390px 的第一個畫面裡（約 949px、937px），安心話再往下推約 72px。本人 2026-11-16 決定接受：六份都檢查題目在第一個畫面，「下一題」只檢查 HHIE-S、HHIA-S、THI、SSQ12 和訪客。
8. **R1 的「8000 Hz。」**在 320px 寬、200% 字級時「Hz。」可能被換到下一行。規格只要求不左右捲。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。「頁面」＝`screening/tests/`，「單元」＝`frontend/src/`，「端對端」＝`e2e/main_flow.py`。

| # | 驗收條件（簡寫） | 驗證 | 證據 |
|---|---|---|---|
| 1–2 | 三頁打錯信箱出現問句與按鈕；按了改好、提醒消失 | ✅ 自動 | 單元 `email-hint.test.js`；頁面 `test_email_hint.py`；端對端 `EmailTypoHintTest` |
| 3–4 | 差一兩個字才問、一樣或差太多不問；「不問」清單不問 | ✅ 自動 | 單元 `email-hint.test.js`（含 yahoo.com.wt 要問、九個地區不問） |
| 5–8 | 不擋送出；改成不像就消失；退回時已在；選填留空不問 | ✅ 自動 | 單元 `email-hint.test.js`；頁面 `test_email_hint.py`；端對端 `EmailTypoHintTest` |
| 9 | 比對不送任何請求 | ✅ 自動 | 單元 `email-hint.test.js`；端對端 `EmailTypoHintTest` |
| 10–11 | 讀螢幕軟體念問句與「已改成」；320／390px、200% 不左右捲、按鈕 44×44px | ✅ 自動 | 單元 `email-hint.test.js`；端對端 `EmailTypoHintTest` |
| 12 | 關掉 JavaScript 沒有提醒 | ✅ 自動 | 端對端 `EmailTypoHintTest`（忘記密碼）；頁面 `test_email_hint.py`（三頁送出空的位置） |
| 13–14 | 三頁打 39 出現綠勾與「今年滿 76 歲」 | ✅ 自動 | 單元 `register-checks.test.js`；頁面 `test_birth_age.py`；端對端 `BirthAgeTest` |
| 15–19 | 錯的不顯示；全形與空白；改年份跟著變；退回時已在；讀螢幕軟體念一次 | ✅ 自動 | 單元 `register-checks.test.js`；頁面 `test_birth_age.py`；端對端 `BirthAgeTest` |
| 20 | 畫面歲數＝註冊後帳號年齡 | ✅ 自動 | 頁面 `test_birth_age.py`；端對端 `BirthAgeTest` |
| 21 | 390px、200% 不左右捲，那一列不被擠壞 | ✅ 自動 | 端對端 `BirthAgeTest` |
| 22–24 | 中間欄有「下一個」、Enter 跳下一欄不送出、最後一欄送出 | ✅ 自動 | 單元 `enter-next.test.js`；頁面 `test_enter_next.py`；端對端 `EnterNextFieldTest`（逐欄只測註冊頁，其他四頁證明有載入） |
| 25–27 | 選字中不跳；密碼跳過「顯示」；單欄表單照舊 | ✅ 自動 | 單元 `enter-next.test.js`、`AudiogramApp.test.jsx`；頁面 `test_enter_next.py`；端對端 `EnterNextFieldTest` |
| 28 | 聽力圖日期年 → 月 → 日，「日」不變 | ✅ 自動 | 單元 `AudiogramApp.test.jsx`；端對端 `EnterNextFieldTest` |
| 29–30 | 單選勾選下拉日期選擇器不變；關掉 JavaScript 照舊 | ✅ 自動 | 單元 `enter-next.test.js`；頁面 `test_enter_next.py`；端對端 `EnterNextFieldTest` |
| 31–37 | 提示句、讀數（遮蔽、無反應）、拖動跟著變放開才念、刪點與換耳回提示、數值表也更新 | ✅ 自動 | 單元 `AudiogramApp.test.jsx`、`AudiogramReading.test.jsx`；端對端 `AudiogramReadingTest` |
| 38 | 那一塊變字時圖完全不動 | ✅ 自動 | 端對端 `AudiogramReadingTest`（拿掉預留高度時會失敗，實作時驗過） |
| 39–41 | 最長讀數不左右捲；確認存檔沒有；原本的小讀數、清除按鈕照舊 | ✅ 自動 | 單元 `AudiogramApp.test.jsx`；端對端 `AudiogramReadingTest` |
| 42–46 | 有「看示範」；播約 2 秒停住；「再看一次」；不自動播；不動使用者的點 | ✅ 自動 | 單元 `AudiogramDemo.test.jsx`、`AudiogramApp.test.jsx`；端對端 `AudiogramDemoTest` |
| 47–49 | 減少動態效果時沒有；讀螢幕軟體跳過；390px、200% 不左右捲、按鈕 44×44px | ✅ 自動 | 單元 `AudiogramDemo.test.jsx`；端對端 `AudiogramDemoTest` |
| 50–56 | 漏標規則（只比氣導、一耳沒標不列、無反應遮蔽算有標…） | ✅ 自動 | 單元 `audiogram.test.js`（`missedAir`）、`AudiogramApp.test.jsx`；端對端 `AudiogramMissedMarksTest` |
| 57–60 | 不擋存檔；補標後更新；提示框樣子；不左右捲 | ✅ 自動 | 單元 `AudiogramApp.test.jsx`；端對端 `AudiogramMissedMarksTest` |
| 61–63 | 登入兩句、訪客一句、退回表單一句 | ✅ 自動 | 頁面 `test_answering.py`、`test_guest.py`；單元 `answer-main.test.jsx`；端對端 `AnswerReassuranceTest` |
| 64–66 | 過了第一個畫面收起；接著答畫面有；沒有教怎麼回答的字 | ✅ 自動 | 單元 `answer-main.test.jsx`；頁面 `test_answering.py` |
| 67 | 不左右捲；第一題和「下一題」在第一個畫面 | ✅ 自動（範圍見上面第 7 點） | 端對端 `AnswerReassuranceTest` |
| 68 | 七項都先有設計圖、本人選定 | ✅ 文件 | [設計圖](../planning/redesign/mockup-613-filling.html)、[選定表](../planning/redesign/interaction-grill-decisions.md) |

## 測試結果

2026-11-16 在 `6c382944`（自審修正後）跑：

| 項目 | 結果 |
|---|---|
| `ruff check .`、`ruff format --check .` | 通過 |
| `npm test --prefix frontend` | 43 個檔、744 個通過 |
| `manage.py test --settings=config.test_settings --parallel 4` | 2697 個通過 |
| `npm run build --prefix frontend` 後 `e2e.main_flow --parallel 4` | 478 個通過 |

新加的端對端類別：`AudiogramReadingTest`、`AudiogramDemoTest`、`AudiogramMissedMarksTest`、`EmailTypoHintTest`、`BirthAgeTest`、`EnterNextFieldTest`、`AnswerReassuranceTest`。

## 本人實機要看的

自動測試測不到，請在手機上操作：

1. 註冊頁：手機鍵盤那顆鍵在中間欄寫什麼字、按了是不是跳下一欄；用注音打使用者名稱、選字時按 Enter 不會跳欄。
2. 註冊頁：信箱打 `wang@gmial.com` 再點別處，問句和「按這裡改」；出生年打 39 出現「今年滿 76 歲」。
3. 記錄聽力圖：標點時圖上方那一塊、拖動時數字跟著變、圖不會跳；按「看示範」看動畫順不順；左耳少標幾個頻率到確認存檔看提示。
4. 作答頁第一個畫面的安心話（登入與沒登入各看一次）。

## 本人驗收

（待本人操作後填寫）
