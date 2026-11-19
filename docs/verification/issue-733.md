# #733 整體統計與同意書第 9 版

日期：2026-11-19。分支：`docs/aggregate-statistics`。規格 [#733](https://github.com/minuet878-prog/HearWell/issues/733)，沒有拆票。

狀態：2026-11-19 本人在本機實際操作後回覆「看過了，通過」，**驗收通過**。自動測試全過（單元 3166、前端 769、端對端 478），Ruff 兩項檢查都過。

- 拷問決定：本人 2026-11-19 在對話裡逐題點選（Q1–Q13），寫進 ADR 0069 和 GLOSSARY「整體統計」。研究的勾選等有具體題目、合作機構和 IRB 再另開規格。
- 本人的字：隱私權說明選 A 完整版（Q9），「先看重點」選 A 改原句（Q10）；統計資料範圍照 Q11 寫成「問卷作答與結果、聽力圖、助聽器與補助資料和出生年」，並加「不會用到您的 email、使用者名稱和登入方式」。
- 實作中本人補充（已寫回規格）：「會交給誰」的「我們不會把您的資料交給其他人或公司」維持原句。
- 第 4 步自審（`/mattpocock-skills:code-review`，基準 `origin/main`）：Standards 沒有硬性違規；Spec 沒有要修。照建議把「整體統計」段落的測試改成逐字比對（多一句會失敗）。
- 交叉審查（Codex，2026-11-19）：[審查結果與修正](https://github.com/minuet878-prog/HearWell/issues/733#issuecomment-6996466769)。要修 1 項：驗收 3 的「關於聽伴」頁沒有檢查重點第一項，已修（`1237ec61`，三頁各取第一項比對，第一、二項對調時三頁都失敗）。複核沒有要修（本人 2026-11-19 回覆）。
- 沒有操作真實資料，沒有 migration。測試都在臨時測試資料庫上。

## 行為

| 項目 | 現在 |
|---|---|
| 隱私權說明「為什麼蒐集」 | 最後多一條「把大家的篩檢結果和聽力紀錄合起來統計……整體數字。」，下面「我們不會……做上面以外的用途。」不變 |
| 隱私權說明「整體統計」 | 新的折疊段落，在「意見回饋」和「存放在哪裡、保存多久」之間：統計哪些資料、例子、用途，再列 6 點（不用 email 等、只公布整體數字、少於 10 人不公布、只算同意這一版的人、刪帳號後不再算但已公布的收不回、研究會另外勾選） |
| 「先看重點」第一句 | 「只用來算分數、給建議、保存您的紀錄，以及做認不出是誰的整體統計；不拿去賣或做廣告。」同意頁、隱私權說明、關於聽伴三頁共用 |
| 同意書 | 第 9 版，日期 2026/11/19。同意過第 8 版以前的人，下次打開健康資料頁先到同意頁，同意後回到原頁 |

跟規格不一樣、或規格沒寫到的地方（請本人驗收時一起看）：

1. **更新日期先填 2026/11/19**：規格要的是「上線那天」。如果晚於今天部署，部署前要把 `PRIVACY_UPDATED_ON` 改成上線日（測試只要求不早於 11/19）。
2. **舊測試的「第 8 版」改成「至少第 8 版」**：LINE 登入、重測提醒、意見回饋、iPhone 匯入四處原本寫死 8，照以前升版的做法改成 `>=`，第 9 版由 `test_aggregate_statistics.py` 寫死保護。`test_consent.py`「分組不升版」那條照它自己的註解改成寫死 9。
3. **截圖基準**：隱私權說明多一段、重點句變長，`e2e/screenshots.py` 的隱私權說明與同意頁截圖要重拍（不在 CI 裡）。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。測試檔都在 `screening/tests/`。

| # | 驗收條件（簡寫） | 驗證 | 證據 |
|---|---|---|---|
| 1 | 「為什麼蒐集」有統計那一條 | ✅ 自動 | `test_aggregate_statistics.py`（`test_why_it_is_collected_includes_the_statistics`） |
| 2 | 「整體統計」折疊段落、在意見回饋後、一字不差 | ✅ 自動 | `test_aggregate_statistics.py`（`test_a_part_of_its_own_after_the_feedback_part`、`test_the_part_says_what_is_counted_and_what_is_published` 逐字比對）；`test_account_redesign.py`（段落順序） |
| 3 | 三頁「先看重點」第一句是新句、沒有舊句 | ✅ 自動 | `test_aggregate_statistics.py`（`StatisticsHighlightTests`，三頁各取第一項）；`test_consent.py`（`test_highlights_on_top_match_the_consent_page`） |
| 4 | 顯示「第 9 版，<日期> 更新」 | ✅ 自動 | `test_aggregate_statistics.py`（`test_version_9_with_its_date`） |
| 5 | 只同意第 8 版的人先到同意頁，同意後回原頁 | ✅ 自動 | `test_aggregate_statistics.py`（`test_who_agreed_to_version_8_agrees_again_and_goes_on`） |
| 6 | 新同意存成第 9 版 | ✅ 自動 | `test_aggregate_statistics.py`（`test_agreeing_now_keeps_version_9`） |
| 7 | 「我們不會……以外的用途。」仍是最後一句 | ✅ 自動 | `test_aggregate_statistics.py`（`test_why_it_is_collected_includes_the_statistics`，`endswith`） |
| 8 | 沒有新增資料表、欄位或統計功能 | ✅ 人工 | 規格指定看 diff 驗收，不寫鏡像 diff 的測試。自審與 Codex 都看過：沒有 migration，`models` 只改 `CONSENT_VERSION` 和 `PRIVACY_UPDATED_ON` 兩個常數，其餘是兩個模板、測試、GLOSSARY 和 ADR 0069 |
| — | 本人在畫面上看過文字和再同意的流程 | ✅ 本人 | 2026-11-19 本機操作，下面的清單 |

## 本人實際操作驗收（本機）

這次沒有 migration。在終端機開 worktree 的網站：

```bash
cd /Users/huangweizhe/HearWell/.claude/worktrees/aggregate-statistics && /Users/huangweizhe/HearWell/py313/bin/python manage.py runserver 8001
```

打開 http://localhost:8001 ，手機寬度或字放大 200% 也看一次：

- [x] 隱私權說明：「先看重點」第一句是新句；「為什麼蒐集」最後一條是統計；「意見回饋」下面有「整體統計」，打開看 6 點；頂端寫「第 9 版，2026/11/19 更新」
- [x] 關於聽伴：「先看重點」第一句是新句
- [x] 用一個以前同意過的測試帳號登入，打開「我的聽力」：先到同意頁、看得到新句，按同意後回到「我的聽力」（本機資料庫會多一筆這個帳號的第 9 版同意紀錄）
- [x] 註冊一個新帳號：同意頁的重點第一句是新句
