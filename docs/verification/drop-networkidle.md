# e2e 不再等 networkidle

日期：2026-10-23；分支 `test/drop-networkidle`（從 `main` 的 `c381287` 開出）。
狀態：自動驗證完成；**不需交叉審查**（只改測試，不碰計分、門檻、資料或權限）；本人 2026-10-23 看 CI 結果後合併 PR #267。

## 起因

`main` 合併 PR #264 後（`e00c222`），CI 的 e2e 在 `MoreYouCanDoTest.test_browser_tab_and_no_javascript_show_every_card` 等 `networkidle` 逾時 30 秒。CI 留下的 trace 顯示頁面 2.2 秒就載完，30 個請求（頁面、CSS／JS、25 個字型切片）全部完成，跟本機列出的清單一樣；同一份程式在 PR、`docs/257-roadmap` 分支和本機都通過，重跑也通過。是什麼讓網路一直「沒靜下來」，現有證據看不出來。

Playwright 官方文件把 `networkidle` 標為 DISCOURAGED：「Don't use this method for testing, rely on web assertions to assess readiness instead.」

## 改了什麼

7 處 `wait_for_load_state("networkidle")` 全部換掉：

| 位置 | 改成 |
|---|---|
| `SharedLayoutTest.test_phone_width_needs_no_sideways_scrolling` | 等趨勢圖的「載入中」消失、`/report` 的聽力圖畫出來，再等字型 |
| `PwaNavTest` #1、#2 | 拿掉：`goto` 等到 load 事件，`pwa-nav.js`（module script，同步執行）已經跑完 |
| `PwaNavTest.header_boxes` | 等字型（量的是頁首） |
| `MoreYouCanDoTest.open_home`、帳號設定頁 | 拿掉：同上，後面的 `expect` 本來就會自動等待 |
| `e2e/screenshots.py` 的 `open` | 等趨勢圖「載入中」消失、作答頁題目載完、聽力圖畫出來 |

## 驗證

- [x] 整套 e2e：`manage.py test e2e.main_flow --parallel 4`，110 項通過（審查修正後重跑一次，也是 110 項通過）。
- [x] 截圖不變：`e2e/screenshots.py` 改前、改後各截 434 張，`e2e/compare_shots.py` 比對 434 張畫面全部相同，字型與基礎字級也相同。
- [x] `test_standards` 8 項通過；Ruff 通過。
- [x] 自審（`/mattpocock-skills:code-review`）：Standards 軸沒有要修的；Spec 軸一項要修（量寬度前沒等 `/report` 的聽力圖，而且應該先等圖再等字型），已修在 `596c001`。
- [x] 推上 GitHub 後 CI 通過（PR #267：backend、frontend、e2e 三項 SUCCESS）。
