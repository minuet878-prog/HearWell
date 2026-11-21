# #741 照顧旅程七步與全站頁面改版

日期：2026-11-21～22。整合分支：`feat/741-page-redesign`。規格 [#741](https://github.com/minuet878-prog/HearWell/issues/741)，子票 #742–#758，另含 #759、#760（本人另開、併入同一整合分支）。

狀態：本人 2026-11-21～22 在本機預覽（worktree 開 runserver 8001）逐頁實際操作，2026-11-22 回覆「看完了，可以寫驗收紀錄」，**驗收通過**。交叉審查（Codex）要修 5 項已修完並複核通過。

## 自動測試（整合分支 `93793f5a`，之後只改隱私權更新日期 `0795feb2`）

| 項目 | 結果 |
|---|---|
| 單元測試 | 3284 個通過（skipped 1） |
| 前端（Vitest） | 799 個通過 |
| 前端建置 | 成功 |
| e2e（`--parallel 4`） | 514 個通過 |
| Ruff check／format | 通過 |

`0795feb2` 只改 `PRIVACY_UPDATED_ON` 和它的測試，`test_consent`、`test_family_zone`、`test_pages` 共 161 個重跑通過。

## 子票

| 票 | 內容 | 交叉審查 |
|---|---|---|
| #742 | 拿掉待辦和「第幾台」（migration 0045） | 要（migration） |
| #743 | 選配路線新順序與各站完成條件（migration 0046 只改證明選項文字） | 要（migration、完成條件） |
| #744 | 照顧旅程七步、第 1–4 步卡片 | — |
| #745 | 第 5 步路線站問答卡 | 要（權限） |
| #746 | IOI-HA 兩次、第 6、7 步倒數 | — |
| #747 | 只播一次的進場動畫 | — |
| #748 | 頁首、返回鍵、分頁列 | — |
| #749 | 小鳥對話、藍色大卡 | — |
| #750 | 結果頁、分級短名 | 要（分級） |
| #751 | 登入首頁 | — |
| #752 | 訪客首頁三扇門（migration 0047 只新增預設 0 的欄位） | — |
| #753、#754 | 問卷頁、了解頁堆疊卡 | — |
| #755 | 作答頁 | — |
| #756 | 紀錄頁 | — |
| #757 | 帳號設定、登入頁 | — |
| #758 | 無障礙、無 JavaScript、e2e 收尾 | — |
| #759、#760 | 全站選中樣子、章節順序跟路線（驗收紀錄見 `issue-759.md`、`issue-760.md`） | — |

## 第 4 步自審（`/mattpocock-skills:code-review`，基準 `main`）

- Standards 違規 3 項已修：返回鍵／頭像／離開的滑過效果包進 `@media (hover: hover)`、刪沒人用的 `Definition.short_name()`、`CODING_STANDARDS.md` 第 22、23 條同步 ADR 0075、0077。
- 判斷題修了：`_keep_view` 改公開 `fitting_route.keep_view`、合併重複查詢、`HOME_SKIPPED_STOP` 改名、不再拆顯示文字取站名、兩處過時註解。
- 未做：`care_journey._step`／`_card` 參數過多（Data Clumps）的重構，跟這次需求無關。
- Spec 軸要本人決定的 3 項都決定了（第 2 步「點過」從哪點都算、訪客「開始」記在門：了解自己、規範檔同步）。

## 第 4b 步交叉審查（Codex）

審查者只看 diff、規格 #741（含「實作中本人補充」）和 `CODING_STANDARDS.md`。結果留言在 #741：

- 第一輪（[留言](https://github.com/minuet878-prog/HearWell/issues/741#issuecomment-7064937378)）：要修 5 項、建議 0 項。migration、權限、門檻與計分、路線與七步四個高風險區塊沒有問題。
- 修正（`5d7372aa`、`ecf133d4`、`2cf6cae8`、`a9331a2a`、`93793f5a`）：第 6 步要第二份 IOI-HA；訪客結果的儀表進入「捲到才播一次」；補驗收 21 兩卡同尺寸、來源標籤無外框、登出紅字三個斷言。
- 複核（[留言](https://github.com/minuet878-prog/HearWell/issues/741#issuecomment-7065476769)）：5 項都已解決，仍要修 0 項。

## 驗收對照

逐條「驗收 → 測試斷言（檔案:行號）」的完整對照在交叉審查報告裡（Spec 軸兩張表：驗收 1–32、驗收 33–58 與本人補充），審查者每一條都找到對應斷言，缺的 3 條已補。下表是摘要。

| 驗收 | 內容 | 證明的測試 |
|---|---|---|
| 1–6 | 七步、第 2、3 步與聽力圖 | `test_home_journey.py`（只做 HHIE-S、查詢醫療院所後到第 3 步、缺頻率、第 3 步完成的結果小卡）；`test_care_journey.py`（第一張聽力圖讓第 2、3 步一起完成） |
| 7–10 | 第 4 步三種情況 | `test_care_journey.py` `GuideStepTests`、`test_home_journey.py`（正常／追蹤目前不需要、輕到中度看種類與價格） |
| 11–16 | 身障證明、九號表、核定公文問答卡 | `test_answer_cards.py` `CertificateCardTests`、`Form9AndNoticeCardTests`；`test_route_answers.py` |
| 17–20 | 首頁跳過種類與價格、去找聽力師之前 | `test_route_order.py` `HomeSkipsTypesAndPricesTests`；`test_answer_cards.py` |
| 21–23 | 配戴之後兩張小卡（同尺寸）、二十五號表日期卡 | `test_answer_cards.py`；e2e 兩卡同尺寸（`2cf6cae8`） |
| 24–26 | 第 6、7 步倒數（半圓）、IOI-HA 逐題比較、第二份 | `test_care_journey.py` `EffectStepTests`（含晚填第一份的回歸，`5d7372aa`）；`test_ioi_ha_since_last.py`；`test_home_journey.py` |
| 27–28 | 朱紅印章、戴助聽器從第 5 步算 | `test_home_journey.py`；e2e `test_the_done_stamp_presses_down_once` |
| 29–32 | 沒有待辦、migration 0045、路線順序、證明三選項 | `test_no_todos.py`（0044→0045 真跑遷移、九欄不變）；`test_route_order.py` |
| 33–34 | 每頁小鳥對話、最多一張藍色大卡（首頁一行） | `test_bird_hero.py` `EveryPageTests` |
| 35–39 | 頁首、頭像選單、返回鍵、分頁列 | `test_site_header.py`；`frontend/src/site-header.test.js`；e2e `SiteHeaderTest`、頭像選單（含登出紅字 `93793f5a`） |
| 40–43 | 登入首頁問候、大卡、兩格；訪客首頁三扇門 | `test_home_journey.py`；`test_home_doors.py`；e2e 門計數 |
| 44–46 | 問卷頁堆疊卡 | `test_card_stack.py`；`frontend/src/card-stack.test.js`；e2e 拖曳換卡 |
| 47 | 作答頁 | `test_answer_page_layout.py`；`frontend/src/AnswerApp.test.jsx` |
| 48–49 | 結果頁、分級短名 | `test_result_gauge_page.py`、`test_short_level_names.py`、`test_score_explain.py`、`test_just_saved.py`、`test_thi_support.py` |
| 50 | 紀錄頁、趨勢圖 | `test_records_page.py`；`frontend/src/TrendChart.test.jsx`；e2e 線和點從左畫到右（含半途斷言） |
| 51 | 了解頁 | `test_learn_stack.py` |
| 52–53 | 帳號設定、登入頁 | `test_account_login_pages.py`、`test_reminder_switch.py`、`test_accounts.py`（密碼「顯示」在框後） |
| 54–58 | 減少動態效果、只播一次、讀螢幕、200%／320px、無 JavaScript | e2e `test_reduced_motion_nothing_moves_on_the_redesigned_pages`、`CountUpTest`、`BirdAndHeroCardTest`、`GuestResultGaugeTest`（`ecf133d4`）、無 JS 問答卡與問卷頁；`frontend/src/in-view.test.js` |

## 驗收時本人的決定（都寫回規格 #741「實作中本人補充」）

2026-11-21～22 在預覽逐頁看過後決定，共約 40 條，主要有：

- 第 2 步：點過「查詢醫療院所」（從哪裡打開都算）或有任何聽力圖就完成；第 3 步才顯示聽力圖來源兩張小卡。
- 兩個首頁的小鳥只一行；拿掉清單旁「N / 7」；離下次篩檢、第 6、7 步倒數改成半圓。
- 結果頁：綠條和「做完了」只在剛交出時（訪客也一樣）；拿掉作答資訊兩行；黃色分數卡置中；「這個分數怎麼算」移到分數卡和建議下一步中間（固定分數尺＋情緒／社交兩列），刪「看完整建議」；THI 重度、極重度一律顯示 1925。主按鈕可以在第二個畫面（放寬 2026-11-16 的決定）。
- 分數不從 0 往上跑，天數可以（ADR 0077 已修正）。
- 標籤（分級、比上次、來源）不要外框；印出的報告分級保留外框。
- 頁首：左上只寫「聽伴」；首頁以外一打開就有「‹」；點頭像跳出帳號設定／登出選單。
- 了解頁卡片置中、副標 22px；帳號設定提醒只留鈴鐺、狀態、按鈕；分享報告頁精簡、只在沒有 JavaScript 時顯示網址。
- 隱私權說明用字改成「看過哪些選配指引頁面、是否查過醫療院所」，同意書維持第 9 版，更新日期 2026-11-22。

## 部署注意

- migration：0045（刪待辦打勾表和 `pair_number`）、0046（只改選項文字）、0047（新增預設 0 的欄位）。
- **部署前**照 ADR 0073 先查正式環境會刪多少打勾紀錄（唯讀）：

```sql
SELECT (SELECT COUNT(*) FROM screening_todotick) AS ticks, (SELECT COUNT(DISTINCT user_id) FROM screening_todotick) AS users, (SELECT COUNT(*) FROM screening_aidandsubsidy WHERE pair_number > 1) AS later_pairs;
```

- 本機開發資料庫已在驗收時套用 0045–0047（本人同意）；切回 `main` 前要等 #741 合併，否則首頁會因缺欄位報錯。

## 待辦（不在這次範圍）

- 動畫與視覺細節 Brief 剩下的部分（按下縮小、錯誤抖一次、OKLCH 漸層、紀錄卡片長大轉場、同心圓角、圖示粗細、骨架畫面、數字對齊）：#741 合併後當下一份規格。
- `test_share.py` 的「封面不能有 dB」偶爾失敗：頁面上隨機產生的 CSP nonce 偶爾含「dB」。
- `main` 原本就有 9 處滑過效果沒包在 `@media (hover: hover)`。
- 合併後更新 `docs/roadmap.md` 和面試筆記，並跑 `/mattpocock-skills:retro`。
