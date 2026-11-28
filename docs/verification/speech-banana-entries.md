# 語言香蕉區多兩個入口驗證

2026/11/28。分支 `feat/speech-banana-entries`。沒有規格 issue：2026-11-27 走查時，本人在 `/audiograms/12` 標註（`#044d2ecb`），說喜歡語言香蕉區，但只有單張聽力圖頁進得去。代理做了四案比較頁（首頁照顧旅程、我的紀錄、了解頁、健康報告），本人選首頁和我的紀錄兩案，了解頁先不做。比較頁就是設計圖。

**不需交叉審查**：只加連結，不碰計分、分級、門檻、資料或權限。語言香蕉區頁本來就只開本人的聽力圖（`_own_audiogram`）。

**實機驗收**：待本人操作。

## 改了什麼

| 位置 | 使用者看到 | 什麼時候出現 |
|---|---|---|
| 首頁照顧旅程第 3 步「記錄聽力圖」 | 展開已完成的第 3 步，「聽力圖結果」卡下面多一張入口卡「看語言香蕉區／看哪些說話聲可能不容易聽到」，開最新一張聽力圖的語言香蕉區 | 第 3 步完成時。完成代表最新一張能判讀，一定有氣導標記 |
| 我的紀錄・聽力圖分頁 | 「比較聽力圖」下面多一顆外框按鈕「看語言香蕉區」，開最新一張 | 最新一張有氣導標記時；只有骨導或沒有聽力圖就不出現（跟聽力圖頁一樣） |

字句沿用聽力圖頁已審過的那張卡，沒有新句子。

## 自動驗證

- Django 全套 3,350 項，3,349 項通過、1 項跳過。
- 前端 807 項通過，前端建置與 Ruff 通過。
- 端對端 524 項全部通過（rebase 到最新 `main` 前後各跑一次）。
- 自審（`/mattpocock-skills:code-review`）：兩軸都沒有「要修」。Standards 建議兩項：view 傳給模板的鍵改名為 `banana_audiogram`（已改）；「有沒有氣導標記」的判斷在兩處重複，只有兩行、沒有抽出。Spec 建議三項：補斷言證明首頁卡在聽力圖結果卡下面、第 3 步未完成時沒有這張卡、按鈕在「比較聽力圖」之後（都已補）。

## 驗收條件與測試對照

| 條件 | 測試 |
|---|---|
| 第 3 步完成時，聽力圖結果卡下面有入口卡，字句正確，開最新一張 | `test_home_journey.py` `test_step_3_done_also_opens_the_newest_audiogram_s_speech_banana` |
| 第 3 步未完成時沒有這張卡 | `test_home_journey.py` `test_a_missing_frequency_s_card_is_its_sentence_and_editing_it` |
| 照顧旅程帶出最新一張的語言香蕉區網址 | `test_care_journey.py` `test_step_3_done_opens_to_the_audiogram_s_result` |
| 聽力圖分頁有外框按鈕、在「比較聽力圖」之後、開最新一張 | `test_records_redesign.py` `test_the_speech_banana_button_opens_the_newest_audiogram` |
| 最新一張只有骨導時沒有按鈕 | `test_records_redesign.py` `test_no_speech_banana_button_without_the_newest_s_air_marks` |
| 沒有聽力圖時沒有按鈕 | `test_records_redesign.py` `test_no_speech_banana_button_without_an_audiogram` |

## 不在這個 PR

- 了解頁的語言香蕉區卡（含沒有聽力圖的人看範例版）：本人決定先不做；要做的話，範例版會推翻原拷問第 6 條，要重新拷問。
- 健康報告、分享報告不放（原拷問第 6 條）。
