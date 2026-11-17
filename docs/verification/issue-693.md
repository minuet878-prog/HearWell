# #693 助聽器建議依聽力圖顯示

日期：2026-11-17。分支：`feat/693-fitting-advice`（還沒開 PR）。規格 [#693](https://github.com/minuet878-prog/HearWell/issues/693)，票 #694（設計圖）、#695–#698（實作）。決策：ADR 0067（取代 ADR 0017 的 25 dB 選配建議、ADR 0044 的「目前不需要」條件），ADR 0068（自我測試也算聽力圖）。

狀態：2026-11-17 本人在預覽（埠 8001）實際操作後回覆「看過了，沒問題」，**驗收通過**。自動測試全過。

- 拷問與規格：[拷問決定](../planning/audiogram-gated-advice/grill-decisions.md) Q1–Q11；字句在寫規格時由本人逐句選定。
- 設計圖（#694，2026-11-17）：本人看過改動前後對照，訪客結果頁的建議區塊選 A（改連到「去哪裡做聽力檢查」）。
- 實作中本人補充（都寫進 #693 本文底部）：
  1. 輕度＋最新一筆問卷「無法判讀」→ 當成沒做問卷（先做問卷）。
  2. 最新一筆「無法判讀」時，不分聽力，照顧旅程第 1 步不算完成、請他重做；「下次篩檢」照舊從那筆的日期算。
  3. 顯著影響那句的「自我檢測」改成 GLOSSARY 的「自我測試」（ADR 0068）。
  4. 已戴助聽器的人，聽力圖頁與語言香蕉區頁一律有選配按鈕與選配卡。
  5. 驗收 15 改寫成「只用聽力圖主人自己的資料」：家人連結還沒實作（ADR 0046 只有決策），做好時再補家人身分的測試。
- 第 4 步自審（`/mattpocock-skills:code-review`，基準 `origin/main`）：Spec 1 項錯（輕度＋無法判讀時首頁 500，先寫重現測試再修）、1 項待決（上面補充 4）；Standards 判斷題中，選配指引首頁五句建議從模板搬進 `scoring.py`（第 9 條），其餘小修。
- 交叉審查（Codex，2026-11-17）：[審查與處理](https://github.com/minuet878-prog/HearWell/issues/693#issuecomment-6937710997)。要修 5 項（第 16 條小字登記、AirPods 那句共用、驗收 4 斷言限定在儲存卡、驗收 12 已戴者回歸、驗收 16 補斷言）都修了；S1、S2、驗收 14 是本人在實作中的決定，補寫進規格。[複核](https://github.com/minuet878-prog/HearWell/issues/693#issuecomment-6938507428)：五項都已解決。
- 沒有操作真實資料。測試都在臨時測試資料庫上。

## 行為

| 情況 | 現在 |
|---|---|
| HHIE-S、HHIA-S 結果頁（三級） | 沒有「看助聽器選配與補助」；HHIE-S 無／極輕微影響照留「記錄聽力圖」 |
| HHIE-S 顯著影響 | 「……並做聽力檢查；有 AirPods Pro 的話，也可以先用 iPhone 做聽力自我測試。」（建議原文與第一步） |
| HHIE-S 三級 | 建議末尾與底部小字都有「這份問卷反映您感受到的生活影響，不能判定聽損程度，也不能單憑分數決定是否需要助聽器。」 |
| 訪客結果頁 | 建議區塊改連「去哪裡做聽力檢查」；儲存卡兩級是「網站會依聽力圖幫您整理下一步」 |
| 任一耳 > 40 dB | 建議評估選配，路線照常 |
| 最差耳 26–40 dB＋最新問卷輕中度以上 | 建議評估選配，路線照常 |
| 最差耳 26–40 dB＋最新問卷無／極輕微 | 建議每年追蹤；路線沒有「您在這裡」；旅程第 3、4 步「目前不需要」 |
| 最差耳 26–40 dB＋沒有問卷（或無法判讀） | 先請他做問卷；路線沒有「您在這裡」；旅程第 3、4 步「之後」 |
| 兩耳 ≤ 25 dB | 照舊「如果您仍覺得聽不清楚，建議安排聽力評估」；旅程第 3、4 步「目前不需要」 |
| 看過選配指引章節 | 不再算開始走路線；回答路線上的問題才算 |
| 聽力圖頁、語言香蕉區頁 | 沒戴：只有「建議」才有選配按鈕與選配卡；已戴：一律有 |
| 已戴助聽器 | 選配指引、路線、旅程照舊；聽力圖能不能判讀照舊版條件 |

跟規格或設計圖不一樣、或規格沒寫到的地方（請本人驗收時一起看）：

1. **選配指引首頁的五句建議改由 `scoring.py` 提供**（自審，規範第 9 條），字句不變。
2. **刪掉 `test_guide_result_entry.py`**：整檔在測「結果頁連到選配指引」（#229），已被這次規格推翻。
3. **聽力圖頁多兩三個查詢**（最新一筆問卷、助聽器與補助資料），不隨紀錄筆數增加。
4. **沒修、留著的**：為了避開循環匯入而寫在函式內的 import；同一頁會算兩次使用者狀態；「去之前要準備什麼」在選配路線那一站另有一份。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。都在 `screening/tests/`，`e2e/main_flow.py` 另有改寫的斷言。

| # | 驗收條件（簡寫） | 驗證 | 證據 |
|---|---|---|---|
| 1 | 兩份問卷三級都沒有選配連結；HHIE-S 正常留「記錄聽力圖」 | ✅ 自動 | `test_no_aid_advice.py`（`NoAidAdviceResultTests`）、`test_result_next_steps.py` |
| 2 | 顯著影響新字句（兩處） | ✅ 自動 | `test_no_aid_advice.py`（`test_hhie_s_severe_says_to_have_the_hearing_checked`） |
| 3 | HHIE-S 說明句在建議末尾與底部 | ✅ 自動 | `test_no_aid_advice.py`、`test_result_next_steps.py` |
| 4 | 訪客儲存卡新字句、沒有「助聽器選配」 | ✅ 自動 | `test_no_aid_advice.py`（`NoAidAdviceGuestTests`，斷言限定在儲存卡）、`test_guest_save.py` |
| 5 | > 40 dB 的句子與「去之前要準備什麼」 | ✅ 自動 | `test_guide_summary.py`、`test_fitting_advice.py`（41 dB 邊界） |
| 6 | 輕度＋有影響：句子、準備連結、「您在這裡」 | ✅ 自動 | `test_guide_summary.py`（`FittingAdviceGuideTests`）、`test_fitting_route.py` |
| 7 | 輕度＋無影響：追蹤句、第 3、4 步目前不需要 | ✅ 自動 | `test_guide_summary.py`、`test_care_journey.py` |
| 8 | 輕度＋沒問卷：先做問卷句與連結、沒有「您在這裡」、第 3、4 步之後 | ✅ 自動 | `test_guide_summary.py`、`test_care_journey.py`、`test_fitting_route.py` |
| 9 | 依最新一筆問卷 | ✅ 自動 | `test_fitting_advice.py`（`FittingAdviceLatestRecordTests`）、`test_audiogram_fitting_advice.py` |
| 10 | 正常＋只看章節：第 3、4 步目前不需要 | ✅ 自動 | `test_care_journey.py`、`test_fitting_route.py`（`ViewingDoesNotStartRoute…`） |
| 11 | 正常＋回答一題：路線照常 | ✅ 自動 | 同上 |
| 12 | 已戴照舊 | ✅ 自動 | `test_guide_summary.py`、`test_fitting_route.py`、`test_care_journey.py`（含 `CrossReview693Wearing…`） |
| 13 | 缺頻率：45 dB 建議、30 dB 無法判斷 | ✅ 自動 | `test_fitting_advice.py` |
| 14 | 聽力圖頁、語言香蕉區頁的按鈕與選配卡（含已戴一律有） | ✅ 自動 | `test_audiogram_fitting_advice.py`（`FittingAdviceAudiogramPage…`、`SelfReview693Wearing…`） |
| 15 | 只用聽力圖主人自己的資料（本人改寫） | ✅ 自動 | `test_fitting_advice.py`、`test_audiogram_fitting_advice.py`、`test_guide_summary.py` |
| 16 | 沒登入時衛教入口照留 | ✅ 自動 | `test_no_aid_advice.py`（`NoAidAdviceEducationTests`） |
| 17 | 整套測試與 e2e 通過；交叉審查沒有要修 | ✅ 自動 | 見下方測試結果；複核五項已解決 |
| — | 輕度＋無法判讀不會 500、第 1 步請重做（自審） | ✅ 自動 | `test_care_journey.py`（`SelfReview693UnreadableLifeImpactTests`） |

## 測試結果

- 單元測試：`manage.py test --settings=config.test_settings screening --parallel 4`，2913 項通過。
- e2e：先 `npm run build --prefix frontend`，`manage.py test --settings=config.test_settings e2e.main_flow --parallel 4`，495 項通過（2026-11-17，交叉審查修正之後）。
- `ruff check .`、`ruff format --check .` 通過。

## 本人操作驗收（請在預覽依序看）

用自己的測試帳號，在預覽（埠 8001）記錄聽力圖與填問卷：

1. 做一份 HHIE-S，三級各看一次結果頁：沒有「看助聽器選配與補助」；顯著影響是 AirPods 那句；建議末尾和底部有說明句。
2. 登出做一份訪客 HHIE-S 顯著影響：建議區塊連到「去哪裡做聽力檢查」，儲存卡是新字句。
3. 記一張一耳 45 dB 的聽力圖：選配指引首頁是 > 40 dB 那句；聽力圖頁主要按鈕是「看助聽器選配與補助」。
4. 改成一耳 30 dB：
   - 沒有問卷時：選配指引是「先做問卷」那句和「去做問卷」；首頁旅程現在這一步是第 1 步。
   - 做一份無／極輕微：變成追蹤那句；旅程第 3、4 步「目前不需要」；聽力圖頁主要按鈕是「看語言香蕉區」。
   - 再做一份輕度到中度影響：變成「輕度＋有影響」那句；路線有「您在這裡」。
5. 兩耳都 20 dB、點開一章選配指引：旅程第 3、4 步仍是「目前不需要」。

本人回覆（2026-11-17）：「看過了，沒問題」。
