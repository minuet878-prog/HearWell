# WearMotionTest 偶發失敗：用頁面時鐘停住時間再讀位置（小改動，無 issue）

日期：2026-11-17。基準：`origin/main`（含 #715）；分支：`test/wear-motion-clock`。

狀態：本機重現、修正、連跑通過。只改 e2e 測試，沒碰產品程式、計分、門檻、資料 migration、權限，不需交叉審查。
未操作真實資料；沒有啟動開發伺服器。

## 問題

`WearMotionTest.test_push_in_plays_once_and_stops_on_the_reviewed_drawing` 在本機跑 e2e 三台第 1 組時失敗一次：
按空白鍵重播後，`assertEqual(dome.evaluate(self.WHERE), start)` 的耳塞位置差 0.6 px（x 變小、y 變大，已往耳朵移動）。
過去 40 次失敗的 CI 沒有它；當時這台電腦另有兩個 session 在跑 e2e。

## 根本原因

- `play()`（`frontend/src/wear-motion.js`）按下時先畫第一格，之後每個 `requestAnimationFrame` 依 `performance.now()` 往前畫。
- 推進耳塞的耳塞 `keys` 是 `[[15, 80, -55, 0], [75, 0, 0, 0]]`：前 15%（2400 毫秒的 15% = 360 毫秒）停在起點，之後才移動。
- 測試按鍵後才讀位置，中間要來回一趟；電腦很忙時這段超過 360 毫秒，讀到的就是移動後的位置。差 0.6 px 約等於按鍵後 530 毫秒才讀。
- 按 Enter 後記下的 `start` 也有同樣的問題：兩次讀取只要有一次晚了，就不相等。

## 重現（試驗，已還原）

在讀位置前暫時加 `self.page.wait_for_timeout(...)`，模擬慢機器：

| 延遲 | 修正前 | 修正後 |
|---|---|---|
| 空白鍵後 50 毫秒 | OK（還在 360 毫秒的停留內，所以不會出錯） | |
| 空白鍵後 600 毫秒 | FAILED：`[147.50, 3043.64] != [147.90, 3043.36]`，和原本的失敗同方向 | |
| Enter 後與空白鍵後各 600 毫秒 | | OK |

試驗的兩行等待已刪掉（`grep TRIAL` 為 0）。

## 修正

- 開頁後 `page.clock.install(time=CLOCK)` 再重新整理，Playwright 的時鐘接管 `requestAnimationFrame` 與 `performance`
  （依 context7 查的 Playwright Python 文件；專案用 1.64.0）。
- 按 Enter 前 `pause_at(CLOCK + 1 小時)`：時間停住，讀到的 `start` 一定是第一格；檢查完 `resume()`，動畫照常播完，
  其餘斷言不變。
- 按空白鍵前 `pause_at(CLOCK + 2 小時)`：重播的第一格和 `start` 完全相同，維持原本的 `assertEqual`，沒有放寬。

## 驗收對照

| 需求 | 驗證 | 證據 |
|---|---|---|
| 找出偶發失敗的原因 | ✅ 試驗 | 上表：延遲超過 360 毫秒就重現同方向的失敗 |
| 慢機器也不會失敗 | ✅ 試驗 | 兩次讀取前各延遲 600 毫秒仍 OK |
| 斷言沒有放寬 | ✅ 看 diff | 仍是 `assertEqual(..., start)` |
| 平常照樣通過 | ✅ 本機執行 | `WearMotionTest` 連跑 5 次，每次 2 項 OK（約 4 秒） |

## 測試與審查

- `ruff check e2e`、`ruff format --check e2e`：全過。
- 自審：看過 diff，沒有要修的項目。
