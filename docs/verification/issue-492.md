# 免註冊先篩檢（規格 #492，#493–#500）

日期：2026-11-13。分支：`feat/492-guest-screening`（整合分支，PR [#517](https://github.com/minuet878-prog/HearWell/pull/517)，draft）。規格：[#492](https://github.com/minuet878-prog/HearWell/issues/492)；票：#493 設計圖、#494 結果從沒存的作答算出來、#495 訪客做完看得到結果、#496 從保存卡保存、#497 其他入口先問、#498 清除與到期、#499 首頁直接開始、#500 月計數。

狀態：自動測試、自審都已完成。**本人略過交叉審查**（2026-11-13）。等本人實際操作驗收。

## 本人決定

- 拷問：[grill-decisions.md](../planning/open-access/grill-decisions.md) Q1–Q17，ADR 0055。
- 設計圖：[mockup-493-decisions.md](../planning/open-access/mockup-493-decisions.md)（A1、B1、C1、D1、E1、F2、G2；字句全部照草稿，「換手機或換瀏覽器就看不到這次結果」要加，訪客作答頁拿掉「答案會自動存…」與「✓ 已儲存」）。
- 實作中：[implementation-decisions.md](../planning/open-access/implementation-decisions.md) I1–I6（限次每小時 40 次、`NUM_PROXIES = 1`、載不出來與存不了時的說明、`CODING_STANDARDS.md` 第 6 條計分例外、2 個 worker 不處理）。
- 自審：[self-review-492.md](../planning/open-access/self-review-492.md)，本人選 B1、B2、P3、P1、P2、S3、S6、S7、S9 修，都已修。
- 交叉審查：本人略過。

## 實作時的做法（請本人知道）

- 同意書維持 #478 升的第 5 版；訪客那句併在第 5 版的隱私權說明裡，日期 2026/11/13。
- 首頁兩份訪客結果時，「您有 2 份還沒保存的結果」當兩格的共同標題，新的在上。
- 已同意的人打開隱私權說明、家人專區、問答小助手、帳號設定時不會被轉去詢問，回首頁或進其他頁才問（判斷同意狀態每頁要多一次查詢）。按「不要」後回首頁；轉址前會先閃一下原本的頁。
- 無／極輕微影響的建議裡「記錄聽力圖」連結要登入，訪客點了會被帶去登入頁。
- 隱私權說明與詞彙表沒有寫「訪客月計數」（只有月份與兩個數字，不連到任何人）。
- 瀏覽器完全關掉 JavaScript 時，訪客只看到說明與註冊連結（P3）。

### 代理擬的字句（請本人審）

| 位置 | 字句 |
|---|---|
| 保存頁標題 | 保存這次結果 |
| 有一份沒存成 | 「名稱」沒有存成，還留在這支手機上，請再試一次。（附「再試一次」） |
| 全部存好、跳轉前 | 已保存，正在打開我的紀錄。 |
| 載不出來（I3） | 這個瀏覽器載不出免註冊作答，請註冊後再做。（附「註冊新帳號」） |
| 存不了（I4、B1） | 這個瀏覽器不能暫存結果，請改用一般模式或註冊後作答。（附「註冊新帳號」） |

## 自動測試

提交 `0f5e989`，2026-11-13，本機：

| 項目 | 結果 |
|---|---|
| Django 測試 | 2178 項通過 |
| 端對端測試（`--parallel 4`） | 418 項通過 |
| 前端測試 | 540 項通過 |
| 前端建置、`ruff check`、`ruff format --check` | 通過 |

## 自審

`/mattpocock-skills:code-review`，基準 `origin/main`（2a6632a）。Standards：沒有硬性違規，壞味道 10 項；Spec：34 條中 31 條有斷言，19、22、28 只證明一部分（19、28 已補測試，22 的程式本身正確）。完整清單見 [self-review-492.md](../planning/open-access/self-review-492.md)。另外查到並修了 B1：作答途中存不進瀏覽器時照樣跳到結果頁、答案不見；根本原因是沒檢查 `saveGuestResult` 的回傳。

## 驗收條件

測試檔：G＝`screening/tests/test_guest.py`、S＝`test_guest_save.py`、C＝`test_guest_counts.py`、H＝`test_home.py`、R＝`test_result_from_answers.py`、F＝`frontend/src/guest-results.test.js`、GH＝`guest-home.test.js`、A＝`AnswerApp.test.jsx`、E＝`e2e/main_flow.py`。

**首頁與入口**

- [x] 1 沒登入首頁主要按鈕連到年齡那一步、三步驟、登入連結：H `GuestHome…`；E `GuestHomeTest`
- [x] 2 精靈只問年齡、65 以上進 HHIE-S、18–64 進 HHIA-S：G 精靈測試
- [x] 3 其他問卷作答頁照舊要登入：G
- [x] 4 已登入照舊；打開訪客結果頁回首頁：G
- [x] 5 作答頁上方那一行、照問戴不戴：G；A
- [x] 6 沒登入的分頁列不變：G

**只算分、不儲存**

- [x] 7 不新增 `Submission`／`Answer`：G；R
- [x] 8 分數、分項、分級跟登入者結果頁相同：G；R
- [x] 9 驗證錯誤 400、訊息跟登入者相同：G
- [x] 10 第 41 次 429 與那句話、作答還在（I1）：G；A
- [x] 11 其他問卷被拒絕：G

**訪客結果頁**

- [x] 12 結果內容；沒有與上次比較、報告、分享：G；R；F
- [x] 13 禁止快取、`test_standards.py` 的不用登入健康資料頁面名單：`test_standards.py`
- [x] 14 保存卡依分級字句、兩個按鈕：S
- [x] 15 還留幾天：F；S
- [x] 16 清除前確認、「不要」不變、清完返回鍵看不到：F；E `GuestClearTest`
- [x] 17 只清一份：F
- [x] 18 同一份再做只留最新：F
- [x] 19 滿 7 天消失並刪掉（結果頁與首頁）：F；GH（P1 補）
- [x] 20 跟作答草稿互不影響：F；A

**回得去**

- [x] 21 首頁最上面那一塊：GH；H；E `GuestHomeTest`

**保存**

- [x] 22 從保存卡註冊保存、分數相同、日期是保存那天、清掉訪客結果：S；F；E `GuestSaveFromCardTest`
- [x] 23 從保存卡登入保存直接存：S；F
- [x] 24 兩份一起存：S；F
- [x] 25 重送只有一筆：S
- [x] 26 從頂端註冊先問（按鈕依 F2）：S；F
- [x] 27 登入既有帳號先問，「不要，清掉這次結果」帳號沒有新紀錄：S；F；E `GuestDeclineSaveTest`
- [x] 28 不同意後訪客結果還在、首頁看得到：E（P2 補畫面斷言）
- [x] 29 沒同意最新同意書先走同意書：S

**月計數與隱私**

- [x] 30 做完一份加一、回頭再看不加：C
- [x] 31 保存新建立才加、重送與一般作答不加：C
- [x] 32 只有月份與兩個數字、後台只能看：C
- [x] 33 隱私權說明新句子、同意書版本不變：G

**e2e**

- [x] 34 三條路線：E `GuestSaveFromCardTest`、`GuestDeclineSaveTest`、`GuestClearTest`

## 本人實際操作

（待本人驗收後填寫）
