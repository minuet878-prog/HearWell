# 白卡規則測試漏查同意頁之後的頁面（#369）

日期：2026-10-26。基準：`bf4381b`（origin/main）；分支：`fix/369-white-card-pages`。規格：[#369](https://github.com/minuet878-prog/HearWell/issues/369)。

狀態：只改 e2e 測試，網站畫面與程式沒動。沒碰計分、分級、門檻、migration、權限，所以不需要交叉審查。沒有操作真實資料。

## 原因

`WhiteCardRuleTest` 的兩個迴圈測試用同一個使用者依序開每一頁。清單裡「同意頁」那步的 `undecided()` 會刪掉這個使用者的同意紀錄，排在它後面、需要同意的頁面都被 `ConsentRequiredMiddleware` 導去 `/consent`，量到的是同意頁本身，所以一直通過。

試驗（印出每頁實際網址，跑完已還原）確認漏查的頁面：

- 「每張白卡都是連結」：聽力報告、分享設定。
- 「每個白色元素都點得到」：聽力報告、分享設定、HHIA-S／THI／SSQ12／SADL／IOI-HA 五份作答頁。

帳號設定、家人版報告不需要同意，有檢查到。

## 修法

- 兩個迴圈每開一頁都斷言瀏覽器就在那一頁（`assert_landed_on`），之後任何導向都會直接失敗。
- 同意頁從 `WHITE_CARD_PAGES_LEARN` 拿出來，成為 `WHITE_CARD_PAGE_CONSENT`，三個用到它的迴圈都把它放在最後（含 200% 字級的了解頁迴圈，保留原本的檢查範圍）。
- 修好後新抓到一項：SADL 作答頁收起來的「這份問卷在問什麼？」框是白底。它是 React 畫的下拉框，和全站的 `details` 下拉框共用樣式（`.dropdown-box, .answer-about`）；本人 2026-10-26 決定比照下拉框放行：測試先按按鈕打開，框本身不算，展開的內容照樣檢查。畫面沒改。

## 驗收對照

| 驗收條件 | 驗證 | 證據 |
|---|---|---|
| 檢查到「health report」「share settings」「account settings」時，瀏覽器實際停在那一頁、不是 `/consent` | ✅ 自動 | `e2e/main_flow.py` 的 `assert_landed_on`，用在 `test_every_white_card_is_a_link`、`test_every_white_element_can_be_tapped` |
| 修好後全部通過，或把新抓到的違規逐項列給本人決定 | ✅ 自動＋本人決定 | 新違規一項（SADL「這份問卷在問什麼？」），本人選比照下拉框放行；`WhiteCardRuleTest` 46 項全過 |

## 測試

- 先加網址斷言、不改順序：9 個 subtest 失敗（`'/consent?next=/report' != '/report'` 等），重現了問題。
- 同意頁移到最後：只剩 SADL 那一項；放行後 `e2e.main_flow.WhiteCardRuleTest` 46 項全過。
- 整套 `e2e.main_flow --parallel 4`：276 項全過。
- `ruff check`、`ruff format --check` 通過。
