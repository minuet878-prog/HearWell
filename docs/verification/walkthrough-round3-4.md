# 2026-11-27～28 走查第三、四輪驗證：報告、比較、紀錄、了解、首頁、結果頁

2026/11/28。接續 PR #791，本人用 dev-prompt 在預覽逐頁標註。第三輪收 35 筆，第四輪收 12 筆，另外有本人看設計圖後選定的四項。分支 `style/walkthrough-round3`，從 #791 的最後一個 commit 分出，共 5 個 commit。沒有規格 issue：本人逐筆標註，動版面的都先給設計圖選。

**不需交叉審查**：沒有碰計分、門檻、資料或權限。說明如下：

- HHIE-S 三級建議改寫成一句，只是文字：分級和門檻都沒動，題目和 fixture 也沒動。
- 結果頁「戴上助聽器，差多少？」用的是比較頁本來就有的兩筆比較，只是幫使用者先挑好一組。
- SSQ12／SADL 的橫尺只用來顯示位置，分數本身沒有重算。

**實機驗收**：本人 2026/11/28 在預覽看過了解頁、報告頁、首頁、SADL 結果頁，其餘頁面待本人確認。

## 自動驗證

- Django 全套 3,353 項，3,352 項通過、1 項跳過。
- 前端 806 項通過，前端建置與 Ruff 通過。
- 端對端：第三輪改動跑過 524 項全過；第四輪改動另跑一輪，結果寫在 PR。

## 本人點選的決定

| 項目 | 選擇 | 設計圖 |
|---|---|---|
| 首頁入口 | 跟訪客首頁同字（「擔心家人的聽力」「想了解助聽器」）；已登入首頁放在「上次結果／離下次篩檢」正下方，四格成一塊 | 首頁入口 C |
| 結果頁比較按鈕 | 有沒戴、有戴紀錄時，淺藍方塊放在藍卡上方；用這一筆配另一種最新一筆 | 比較按鈕 B |
| 首頁顏色 | 照顧旅程首頁頂部淡藍光暈、其他地方極淡灰白，區塊改成白卡片（本人先選暖米色底，再拿一張柔和光暈的截圖改成這個） | 首頁光暈 B |
| 結果頁 | 分數區塊、順序維持；「分項僅供參考」改淡灰 | 結果頁 1A、2（本人補充）、3A |
| 其他問卷結果頁 | 淡藍底；SSQ12、SADL 加橫尺；IOI-HA 沒有單一總分，所以不畫尺 | 結果頁 4A |
| HHIE-S 建議 | 三級各一句（本人選定字句） | — |
| 結果頁提醒說明 | 全刪，ADR 0065 補記 | — |

## 改動與驗證對照

| 頁面 | 改動 | 驗證 |
|---|---|---|
| 首頁照顧旅程 | 動畫每步與間隔減半 | 本人看過前後對照；沒有測試在斷言秒數 |
| 首頁（已登入） | 兩塊入口；沒做問卷的首頁拿掉兩個小連結 | `test_home_doors.py` `test_signed_in_*`、`test_home_journey.py` |
| 首頁藍卡 | 只留大標、進度和要按的卡片；第 7 步沒有倒數卡 | `test_home_journey.py`（第 7 步三種情況）、`test_answer_cards.py` |
| 首頁顏色 | 頂部淡藍光暈、白卡片 | 預覽截圖（375 寬、沒有橫向捲動） |
| SSQ12 作答 | 刪「有戴、沒戴怎麼選」；來源只留計分句；刪自動儲存那行 | `test_ssq12.py`、`AnswerApp.test.jsx` |
| 健康報告 | 小鳥只留大標；刪左右耳兩行（摺疊列上已有）；刪 IOI-HA 常模依據行；HHIE-S 建議一句 | `test_report.py`、`test_pages.py` `test_advice_text`、`test_no_aid_advice.py` |
| 比較頁 | 大標「戴上助聽器，差多少？」；刪說明和兩句提醒；「分數變化」；差值句置中 | `test_hhi_comparisons.py`、`test_ssq12_comparisons.py`、`test_records_redesign.py` |
| 結果頁比較方塊 | 藍卡上方淡藍方塊，配對規則，下方列表那列不重複 | `test_result_compare_door.py` 四項、`test_result_pages.py` |
| 結果頁分數區塊 | 刪日期與助聽器那行、「比上次」、「分級從」；螢幕閱讀器句與長條保留 | `test_result_since_last.py`、`test_result_pages_redesign.py`、`test_result_gauge_page.py` |
| 結果頁說明 | 「分項僅供參考」淡灰 | `test_score_explain.py`、`test_scoring.py` |
| 結果頁提醒 | 只剩標題和按鈕 | `test_result_reminder.py` `test_off_with_an_email_*` |
| SSQ12／SADL／IOI-HA 結果 | 淡藍底；SSQ12、SADL 橫尺 | `test_result_scale.py` 三項、`test_result_pages_redesign.py` |
| 我的紀錄 | 沒紀錄：刪說明、按鈕「去做問卷」；報告列刪小字；實心報告按鈕移到最下面 | `test_empty_states.py`、`test_records_redesign.py`、`test_history.py` |
| 了解頁 | 小鳥只留大標「了解聽伴」；卡片刪標題下那行 | `test_learn.py`、`test_learn_stack.py`、`test_search_titles.py` |

## 不在這個 PR

- 骨導只做一耳時兩耳判型、刪除紀錄：要規格和交叉審查，各自的 session 處理中（刪除紀錄見 #794）。
- 我的紀錄 SADL／SSQ12「最近一次」：分支 `feat/records-latest-ungraded`。
- SSQ12 滑桿、語言香蕉區：各自的 session。
