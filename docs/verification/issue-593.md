# #593 補助站預設收起

日期：2026-11-16。分支：`feat/593-subsidy-stops-folded`。規格：[#593](https://github.com/minuet878-prog/HearWell/issues/593)，票 #596、#597、#598（設計圖 #595 已合併）。依據：[拷問決定](../planning/hearing-aid-guide/subsidy-route-grill-decisions.md)、[設計圖](../planning/hearing-aid-guide/mockup-595-subsidy-stops.html)、[ADR 0063](../adr/0063-subsidy-stops-folded-until-answered.md)。

狀態：本人實際操作驗收通過（2026-11-16）。

- 本人在拷問時決定（2026-11-16）：補助站先問再顯示、證明題改成三個選項、收起的那一行是一句話加一個連結、沒登入跟還沒回答一樣、「下一章」不動、其他資源用連結不搬段落、名稱「助聽器選配與補助」不改、三句邀請句不提補助。
- 本人在設計圖選定（2026-11-16）：收起那一行放在五站之後（A）、五站編 1 到 5（X）、細線加兩行字（甲）、收起時不顯示「收到核定通知後 6 個月內要買。」（子）；九句新字照草稿定稿。
- 照現有規則延伸、記在 #593 留言的：收起時「配戴之後」往下的線上沒有「至少 1 個月」；回答「打算申請或正在申請鑑定」的人題目繼續開著。
- 不需要交叉審查：沒碰計分、分級、門檻、權限；migration 只改選項文字、不動資料（有測試確認每一筆值不變）。
- 沒有操作真實資料。測試在臨時測試資料庫上。

## 行為

| 項目 | 現在 |
|---|---|
| 選配路線（還沒回答、沒登入、回答「沒有」） | 五站：記錄聽力圖、去找聽力師之前、身障鑑定與鑑定醫院、助聽器的種類與價格、配戴助聽器之後，編 1 到 5。下面一條細線，接一句「有身障證明的人另外有四站：九號表、等待核定公文、二十五號表、等待補助發放」和連結「看申請補助的流程 ›」（到九號表章）。沒有任何一站標「不適用」 |
| 選配路線（回答「有」或「打算申請或正在申請鑑定」） | 原本的九站，沒有收起的那一行 |
| 沒答證明題、但答過補助站的題目 | 回答過九號表、核定公文、二十五號表其中一題，或在「配戴之後」答「用身障補助」，就展開成九站 |
| 收起時的兩句提醒 | 「助聽器的種類與價格」下面不寫「收到核定通知後 6 個月內要買。」；「配戴之後」往下沒有「至少 1 個月」。展開後照舊 |
| 證明題 | 選項改成「有」「還沒有，打算申請或正在申請鑑定」「沒有」；路線上的答案寫「有身障證明」「打算申請或正在申請鑑定」「沒有身障證明」 |
| 回答「沒有」 | 第 3 站答案下面固定有「看沒有身障證明時」，連到九號表章最後一段；不管聽力圖估算結果、有沒有聽力圖 |
| 章節最下面的題目 | 回答「沒有」的人，九號表章和二十五號表章不問；還沒回答的人照舊問 |
| 首頁照顧旅程 | 「現在這一步」跟路線的「您在這裡」同一站，補助站收起時不會是補助站；第 3 步點開寫「照選配路線一站一站走，從找聽力師到開始戴助聽器。」 |
| 訪客問卷結果 | 輕中度、重度的註冊保存卡片改寫成「……網站會一步步帶您走助聽器選配。」 |
| 下載我的資料 | 身障證明那一項顯示新的選項文字 |

跟設計圖不一樣的地方：沒有。設計圖的截圖比對：五種狀態都照選定的 A、X、甲、子；字放大 200% 時收起那一行跟站名一樣不縮排（設計圖沒畫這種寬度，自審時發現原本會被擠成很窄的一欄，已修）。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。行號以合併 `main` 之後為準。

| #593 驗收 | 驗證 | 證據 |
|---|---|---|
| 1–3 還沒回答、沒登入：五站＋收起那一行＋連結；沒登入不標進度 | ✅ 自動 | `screening/tests/test_route_steps.py:312`；`screening/tests/test_guide_route.py:451`、`:129` |
| 4 收起那一行不是一站、只有一個連結 | ✅ 自動 | `screening/tests/test_guide_route.py:464`；`e2e/main_flow.py:7887` |
| 5–7 「有」九站到九號表；「打算或正在申請」九站停第 3 站、題目開著 | ✅ 自動 | `screening/tests/test_route_steps.py:317`；`screening/tests/test_route_answers.py:182`；`e2e/main_flow.py:3291` |
| 8–10 「沒有」五站、沒有不適用、「您在這裡」到種類與價格 | ✅ 自動 | `screening/tests/test_route_steps.py:326`；`screening/tests/test_route_answers.py:189`；`e2e/main_flow.py:3291` |
| 11–13 沒答證明題但答過補助站題目就展開；已戴自費仍收起 | ✅ 自動 | `screening/tests/test_route_steps.py:338`、`:352` |
| 14 有→沒有→有，九號表的回答還在 | ✅ 自動 | `screening/tests/test_route_steps.py:360`；`screening/tests/test_route_answers.py:384` |
| 15、16 展開後自費、簡易型的不適用照舊 | ✅ 自動 | `screening/tests/test_route_steps.py:378` |
| 17 三個選項、題目與說明不變（路線與鑑定章） | ✅ 自動 | `screening/tests/test_route_answers.py:161`、`:276` |
| 18 修改可以改成另外兩個 | ✅ 自動 | `screening/tests/test_route_answers.py:202`；`e2e/main_flow.py:3291` |
| 19、20 「沒有」兩章不問；還沒回答照舊問 | ✅ 自動 | `screening/tests/test_route_answers.py:384`、`:394` |
| 21 「沒有」固定有「看沒有身障證明時」，在答案下面 | ✅ 自動 | `screening/tests/test_route_answers.py:249`；`e2e/main_flow.py:3291` |
| 22、23 估算未達門檻的標記與連結：還沒回答、正在申請照舊有；「有」沒有 | ✅ 自動 | `screening/tests/test_route_answers.py:235` |
| 24、25 舊答案等同「沒有」；資料庫的值不變 | ✅ 自動 | `screening/tests/test_guide_route.py:479`；`screening/tests/test_route_answers.py:458`（migration 前後每一筆相同） |
| 26 下載我的資料顯示新字 | ✅ 自動 | `screening/tests/test_export.py:326` |
| 27–29 三句邀請句 | ✅ 自動 | `screening/tests/test_guest_save.py:91`；`screening/tests/test_care_journey.py:405` |
| 30 名稱「助聽器選配與補助」和首頁卡片那句不變 | ✅ 自動 | 原本的測試照舊通過：`screening/tests/test_guide_result_entry.py`、`test_records_redesign.py`、`test_home_next_step.py` |
| 31、32 首頁「現在這一步」跟路線同一站、不落在補助站 | ✅ 自動 | `screening/tests/test_care_journey.py:145`、`:220` |
| 33–36 320／390px、200% 字級不左右捲；連結至少 44px 高；讀到的站只有五項；鍵盤焦點框；線畫到「您在這裡」 | ✅ 自動 | `e2e/main_flow.py:7865`、`:7887`；`screening/tests/test_guide_route.py:99` |
| 37、38 設計圖與審字 | ✅ 本人 | #595（已合併），結果在拷問決定的「設計圖選定」 |
| 39–41 章節內文、「下一章」、補助檢核、問答不變；不用重新同意 | ✅ 自動 | diff 沒有動章節範本、補助檢核、問答；`screening/tests/test_consent.py:175`（同意書仍是第 8 版） |
| 42 收起時不寫「6 個月內要買」，展開後照舊 | ✅ 自動 | `screening/tests/test_guide_route.py:485`、`:493` |
| 43 收起時沒有「至少 1 個月」，展開後照舊 | ✅ 自動 | `screening/tests/test_guide_route.py:498`、`:510` |
| 實際走起來 | ✅ 本人 | 見下方「人工驗收」 |

## 測試與審查

以下都是合併 `main`（`590dec54`）之後跑的：

- 單元測試 `manage.py test --settings=config.test_settings --parallel 4`：2688 項全過。
- 前端 `npm test --prefix frontend`：599 項全過。
- 端對端（先 `npm run build --prefix frontend`）`e2e.main_flow --parallel 4`：455 項全過。
- `ruff check .`、`ruff format --check .`、`makemigrations --check`：全過。

自審（`/mattpocock-skills:code-review`，兩個代理分別看規範與規格）：

- #596：規範軸沒有硬性違規；判斷題修了命名、二十五號表的重複條件、樣式不再寫死號碼寬度、用語表補「答過其中一站也會展開」。規格軸規則逐條正確；修了收起時路線狀態仍算著不適用的站，補了四個測試缺口（「沒有」時的 6 個月提醒、還沒回答時的「至少 1 個月」、按「有」後確認九站、390px 版面）。
- #597：規範軸沒有硬性違規；答案下面的連結改成單一欄位並跟估算那段共用字和網址、migration 測試寫法改得好讀、兩處註解修正。`NO_SUBSIDY` 這個名稱跟新字「沒有」對不上，但它對應資料庫存的值，不改。規格軸沒有做錯；補了三個斷言（正在申請且未達門檻照舊有連結、鑑定章說明不變、連結在答案下面）。
- #598：改動只有三個字串，自己逐條對驗收 27–30，沒有另外派代理。

## 人工驗收

本人在 worktree 開預覽（8001），先套用 0036（只改選項文字，SQL 是 no-op）：

```bash
cd /Users/huangweizhe/HearWell/.claude/worktrees/subsidy-route-grill && /Users/huangweizhe/HearWell/py313/bin/python manage.py runserver 8001
```

試過的：

- [x] 沒登入打開「助聽器選配與補助」：五站，下面一行「有身障證明的人另外有四站……」，連結到九號表章。
- [x] 登入、還沒回答證明題：同樣五站；第 3 站的題目是新的三個選項。
- [x] 按「沒有」：補助站收起、沒有淡色的「不適用」；第 3 站答案「沒有身障證明」下面有「看沒有身障證明時」；「您在這裡」到種類與價格，那一站下面沒有「6 個月內要買」。
- [x] 按「修改」改成「有」：展開成九站，「您在這裡」到九號表。
- [x] 改成「還沒有，打算申請或正在申請鑑定」：九站，「您在這裡」停在第 3 站，題目還開著。
- [x] 首頁照顧旅程第 3 步點開的說明、訪客做完問卷（輕中度、重度）的註冊保存卡片，都不再提補助。
- [x] 手機上字放大時，收起那一行好讀、連結好按。

結果：本人 2026-11-16 照上面七項實際操作，沒有問題。
