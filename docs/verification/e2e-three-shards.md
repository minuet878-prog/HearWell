# e2e 分三台、依每組秒數分配（小改動，無 issue）

日期：2026-11-17。基準：`8fccea71`（main，含 #701）；分支：`ci/e2e-three-shards`。

狀態：本機分組檢查與三組執行通過；CI 上的實際秒數等這個 PR 的 run。只動 CI 與 e2e 的測試載入，
沒碰計分、門檻、資料 migration、權限，不需交叉審查。未操作真實資料；沒有啟動開發伺服器。

## 為什麼做

#701 之後 e2e 兩台各約 6 分 20 秒，是最慢的檢查；#711 讓 backend 降到約 1 分 46 秒。只把台數加大不夠：
輪流分組在 3 台時三台分別 97／229／162 秒（本機量的測試秒數模擬），最慢的幾組容易擠在同一台。

## 改了什麼

- `.github/workflows/ci.yml`：e2e matrix 改成 `1/3`、`2/3`、`3/3`。
- `e2e/main_flow.py` 的 `load_tests`：照 `e2e/durations.json` 的秒數，最慢的組先分、每組交給目前秒數最少的機器；
  每台照秒數由多到少跑，最慢的組最先開始。秒數表沒有的組別當成中位數。本機不設 `E2E_SHARD` 照舊跑全部。
- `e2e/durations.json`：本機 `--durations 0` 量的每組秒數（89 組，共 1620 秒）。
- `e2e/update_durations.py`：讀 `--durations 0` 的輸出重寫秒數表；用法在檔頭。分組只看組與組之間的相對時間，
  本機量的就能用在 CI。

## 驗收對照

| 需求 | 驗證 | 證據 |
|---|---|---|
| 三組合起來就是全部、不重複 | ✅ 本機執行 | 不分組 495 項；三組 182＋151＋162 項，合併後與全部相同，重複 0 |
| 三組時間平均 | ✅ 估算 | 三組測試量 541／540／539 秒，4 程序下各約 136／137／137 秒（同樣算法下輪流分組是 97／229／162） |
| 最慢的組先跑 | ✅ 本機執行 | 三組的第一組依序是 WhiteCardRuleTest、StyleInBrowserTest、HearingAidGuideTest |
| 三組都通過 | ⚠️ 本機有干擾，以 CI 為準 | 2/3：151 項 220 秒 OK；3/3：162 項 240 秒 OK；1/3 見下方「本機第 1 組」 |
| 秒數表能重新產生 | ✅ 本機執行 | `update_durations.py` 讀完整 e2e（495 項 OK）的輸出：89 classes, 1620 seconds |
| CI 上 e2e 變快 | ⏳ 等 PR 的 CI | 兩台時各約 6 分 20 秒 |

這些都是測試基礎設施，沒有寫自動斷言；分組用上表的實際載入結果驗證。

## 本機第 1 組

- 第一次：182 項 1 個失敗，`WearMotionTest.test_push_in_plays_once_and_stops_on_the_reviewed_drawing`
  （`main_flow.py` 按空白鍵重播後那行 `assertEqual(..., start)`）：起點位置差 0.6 px。原因是測試本身的時間競爭：
  `play()` 按下時先畫起點，之後每個 `requestAnimationFrame` 往前畫；測試按鍵後再讀位置，中間只要過了一格就不相等。
  跟分組無關；單獨重跑 5 次都通過，過去 40 次失敗的 CI 沒有它。要不要修另外決定。
- 第二次：167 個 error，三個類別（WhiteCardRuleTest、ReturningUserRetestTest、ContentAndContact576Test）的瀏覽器同時被關
  （`TargetClosedError`），之後同類的測試全部出錯。當時這台電腦另有兩個 session 在 worktree 跑 e2e、一組在跑後端測試。
  原因沒有確認；三個程序同時發生，不像單一測試的問題。本人決定先開 PR，以乾淨的 CI 機器為準。

## 以後要注意

- 新增或擴充測試組後，秒數表會慢慢不準（新組先當中位數），三台開始不平均時照 `update_durations.py` 檔頭重跑。
- 再加台數效益很小：每台固定約 1 分 10 秒的準備，加上最大一組（WhiteCardRuleTest）不能拆開。

## 測試與審查

- `ruff check .`、`ruff format --check .`：全過。
- 秒數表用的完整 e2e（不分組、`--parallel 4`）：495 項 566 秒 OK。
- 自審：看過 diff，沒有要修的項目。
