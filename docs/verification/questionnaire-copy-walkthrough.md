# 2026-11-27 走查第二輪驗證：問卷卡片與作答頁（PR #791）

2026/11/27。接續 PR #790，本人用 dev-prompt 標註 16 筆，這個 PR 收其中 13 筆（另一筆「先選一個答案…」已在 #790 刪掉）。分支 `style/questionnaire-copy`，功能 commit `916be2da`。沒有規格 issue：本人逐筆標註，改動前先看過設計圖並點頭。

**不需交叉審查**：只動文字、版面和一個顯示位置（IOI-HA 常模依據，ADR 0085），沒有碰計分、門檻、資料或權限。

**實機驗收**：本人 2026/11/27 在預覽實際操作，通過。

## 自動驗證

- Django 全套 3,346 項，3,345 項通過、1 項跳過。
- 前端 806 項通過，前端建置與 Ruff 通過。
- 端對端 524 項通過（全跑一輪有 5 項仍檢查被刪的字，改成檢查不再出現後，那 3 組重跑全過）。
- GitHub CI 7 項全過。

## 改動與驗證對照

| 頁面 | 改動 | 驗證 |
|---|---|---|
| 問卷頁 | 小鳥小字刪 | `test_card_stack.py:140`、`test_bird_hero.py`（`ONE_LINE`） |
| 問卷頁卡堆 | 藍卡只留圖標、標題、問卷名、按鈕；題數時間、上次結果、適合誰、為什麼推薦刪 | `test_screening_redesign.py:143`、`:164`、`test_questionnaire_cards.py:212`、e2e `test_the_recommended_card_keeps_its_sides` |
| 精靈推薦結果 | 同上 | `test_screening_redesign.py:188`、`test_recommendations.py:151` |
| 推薦規則 | 規則沒動；測試改從頁面資料確認是哪條規則選的 | `test_recommendations.py:151`（`reason`）、`:705`（卡堆原因），41 項全過 |
| 作答頁 | 「答到一半離開…」刪，頁尾「答案會自動存在這支手機…」保留 | `test_answering.py:933`、`answer-main.test.jsx:201`、e2e `AnswerReassuranceTest` |
| IOI-HA 作答 | 第 1 題上方常模依據框刪，摺疊裡每題都看得到（ADR 0085） | `test_screening_redesign.py:250`、`AnswerApp.test.jsx:1220`、`answer-main.test.jsx:170`、e2e `test_nothing_covers_next_on_ioi_ha_items_1_and_2` |

## 不在這個 PR

- SSQ12 滑桿手感、語言香蕉區放哪：各自的 session 處理中。
- SSQ12「不適用」：本人決定保留，不改。
