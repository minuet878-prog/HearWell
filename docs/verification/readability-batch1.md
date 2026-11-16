# 可讀性第 1 批：頁尾、作答頁頁首、離下次篩檢（小改動，無 issue）

日期：2026-11-16。基準：`28ee68e`（origin/main）；分支：`feat/readability-batch1`。依據：[可讀性檢查](../planning/readability-review-2026-11-16.md)、[第 1 批設計圖](../planning/redesign/mockup-readability-batch1.html)。

狀態：等本人實際操作驗收。

- 本人在設計圖選定：頁尾 A、作答頁 A、下次篩檢 B（2026-11-16）。
- 走小改動流程（跳過拷問、規格、拆票）：本人 2026-11-16 決定。作答頁頁首加了一點 React 程式，是邊緣情況，本人同意照小改動做完。
- 不需要交叉審查：沒改計分、分級、門檻，沒有 migration，沒碰權限。
- 沒有操作真實資料。測試和截圖都在臨時測試資料庫上。

## 行為

| 項目 | 現在 |
|---|---|
| 頁尾 | 手機上三個連結排成一列、圖示在字上面；「家人專區：溝通與陪伴」縮成「家人專區」。電腦維持圖示在字左邊。字放大到一列放不下時自動折行，名稱不會被拆開 |
| 作答頁頁首 | 標題、題數、訪客的隱私那一行只在第一個畫面（問有沒有戴助聽器；IOI-HA 是第 1 題）顯示。之後每題只剩進度條和「第幾題／共幾題」。按上一題回到第一個畫面時三行再出現。標題和題數仍然給螢幕閱讀器讀；隱私那一行連同連結拿掉。沒有 JavaScript 的整張表單不變 |
| 離下次篩檢 | 首頁右邊那一格：小標「離下次篩檢」、大字「134 天」（跟左邊「6 分」同一種寫法）、小字日期。「還沒排」「已到期」時小標照舊寫「下次篩檢」 |

跟設計圖不一樣的地方：

- 頁尾：設計圖的頁尾左右只留 8px、連結左右留白 0.1rem；網站頁尾照原本留 16px，連結左右留白用 0.25rem，320px 寬時剛好擠得下一列（第一版用 0.5rem 時會折成兩列）。看起來跟設計圖一樣，可以按的範圍仍然超過 44px。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。

| 需求 | 驗證 | 證據 |
|---|---|---|
| 頁尾連結名稱：訪客兩個、登入後三個，家人專區用短名 | ✅ 自動 | `screening/tests/test_layout.py:256` `FooterOneRowTests` |
| 頁尾聲明和信箱還在 | ✅ 自動 | `screening/tests/test_layout.py:118`（原有，每一頁都檢查） |
| 手機 320、390 寬三個連結同一列、圖示在字上面、每個至少 44px 高 | ✅ 自動 | `e2e/main_flow.py:10245` `FooterOneRowTest.test_a_phone_puts_the_links_in_one_row_icons_over_words` |
| 訪客只有兩個連結時也在同一列 | ✅ 自動 | `e2e/main_flow.py:10292` `test_a_visitor_has_two_links_in_one_row` |
| 電腦上圖示仍在字左邊 | ✅ 自動 | 同上 `test_a_computer_keeps_the_icon_beside_the_words` |
| 320px、200% 字級不超出畫面，連結仍至少 44px | ✅ 自動 | 同上 `test_double_text_size_on_a_small_phone_spills_nothing` |
| 短頁面的頁尾仍貼底、不被分頁列擋住 | ✅ 自動 | `FooterPinButtonRowsT359Test`（原有，照跑） |
| 作答頁：第一個畫面有頁首，之後收起、題目往上移，回到第一個畫面再出現 | ✅ 自動 | `e2e/main_flow.py:10322` `AnswerHeadFirstScreenTest.test_a_guest_sees_the_head_on_the_first_screen_only`；`frontend/src/AnswerApp.test.jsx`「the page head on the first screen only」 |
| 六份問卷的作答頁都一樣（SADL、IOI-HA 從第 1 題開始） | ✅ 自動 | `e2e/main_flow.py:10380` `test_every_questionnaire_folds_its_head_after_the_first_screen` |
| IOI-HA 沒有戴助聽器題，第 1 題算第一個畫面 | ✅ 自動 | `frontend/src/AnswerApp.test.jsx` `counts question 1 as the first screen…` |
| 「要接著答嗎？」時頁首還在，接著答到第 2 題後收起 | ✅ 自動 | 同檔 `keeps the head while asking whether to carry on…` |
| 收起時標題和題數只給螢幕閱讀器、訪客那一行連同連結拿掉 | ✅ 自動 | `frontend/src/answer-main.test.jsx` `folds the page head away past the first screen` |
| 沒有 JavaScript 時表單的標題照常顯示 | ✅ 自動 | `AnswerHeadFirstScreenTest.test_without_javascript_the_form_keeps_its_head` |
| 離下次篩檢：小標、大字天數、小字日期 | ✅ 自動 | `screening/tests/test_home_journey.py:239` |
| 已到期時小標照舊「下次篩檢」 | ✅ 自動 | `screening/tests/test_home_journey.py:249` |
| 還沒排時小標照舊「下次篩檢」 | ✅ 自動 | `screening/tests/test_home_journey.py:206`（原有，整段文字比對「下次篩檢 還沒排」） |
| 天數在 320、390 寬只佔一行；200% 字級不超出 | ✅ 自動 | `e2e/main_flow.py:10407` `NextScreeningTileTest` |
| 實際走起來 | ⬜ 本人 | 見下方「人工驗收」 |

## 測試與審查

- 單元測試 `manage.py test --settings=config.test_settings --parallel 4`：2608 項全過。
- 前端 `npm test --prefix frontend`：564 項全過。
- 端對端（先 `npm run build --prefix frontend`）`e2e.main_flow --parallel 4`：436 項全過。
- `ruff check .`、`ruff format --check .`：全過。

自審（`/mattpocock-skills:code-review`，基準 `origin/main`，兩個代理分別看規範與規格，只看 diff、設計圖和這份紀錄）：

- Standards：沒有硬性違規。6 項判斷題，改了 5 項：作答頁改用網站現成的 `visually-hidden`（原本重寫了一份）、e2e 改用共用的 `submission_with_answers`、刪掉重複的頁尾聲明測試、首頁那一格的標籤合回一處、兩段過時的樣式註解改寫。沒改：e2e 輔助函式回傳三個一組（只在測試裡用）。
- Spec：三項都有做到、沒有漏做。改了：這份紀錄裡跟設計圖對不上的留白數字；補上「還沒排」的證據、「已到期」的斷言、訪客頁尾和六份問卷的 e2e。範圍外：第一個 commit 一起帶進第 2、3 批設計圖、回饋感設計圖和互動盤點，都是文件，PR 說明會寫清楚。
- 第一次完整跑時有兩個舊測試還在找舊的字（頁尾「家人專區：溝通與陪伴」、首頁那一格的「還有」），已改；全部測試檔都搜過，沒有別的地方用到這兩組舊字。

改了的既有測試（刻意改變外觀，不是行為壞掉）：

- `screening/tests/test_family_zone.py`：頁尾連結的字改成「家人專區」。
- `screening/tests/test_home_journey.py`、`screening/tests/test_thi.py`：下次篩檢那一格，日期從大字改到小字。
- `frontend/src/answer-main.test.jsx`：測試頁面多一個頁首元素。

## 量測

`e2e/screenshots.py` 在臨時測試資料庫拍的整頁截圖（390px 寬），隱私權頁的內容這次沒動，高度差就是頁尾：

| 頁面 | 改前（d6151cc） | 改後 | 少了 |
|---|---|---|---|
| 隱私權，登入後（頁尾三個連結） | 2578px | 2454px | 124px |
| 隱私權，訪客（頁尾兩個連結） | 2474px | 2418px | 56px |
| 首頁，登入後 | 1787px | 1637px | 150px（頁尾，加上那一格日期不再佔兩行） |

## 人工驗收

8001 開在這個分支的 worktree（前端已建置）：

```bash
cd /Users/huangweizhe/HearWell/.claude/worktrees/readability-batch1 && /Users/huangweizhe/HearWell/py313/bin/python manage.py runserver 8001
```

用手機寬度（瀏覽器縮窄，或開發者工具選手機）操作：

1. 任一頁捲到最底：頁尾三個連結（沒登入是兩個）排成一列，圖示在字上面，按得到。
2. 登出 → 首頁「開始篩檢」→ 選「65 歲以上」→ 第一個畫面有標題、題數、隱私那一行 → 選「沒戴」按下一題：上面只剩進度條，題目往上移 → 按兩次上一題回到第一個畫面：三行回來。
3. 登入有紀錄的帳號 → 首頁右邊那一格：「離下次篩檢」、大字「N 天」、小字日期。
4. 字放大（手機設定或瀏覽器放大到 200%）再看 1、3：不會左右捲動，天數不斷行。

結果：（待本人回覆）
