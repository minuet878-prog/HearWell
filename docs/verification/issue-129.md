# #129 我的紀錄與聽力圖頁改用 Tailwind 排版驗證

日期：2026-10-21；分支 `feat/129-history-pages`（從 `feat/128-answering-pages` 開出，共用擴充後的搜尋測試）；母分支 `feat/tailwind-migration`。
狀態：自動驗證完成，等本人實際操作驗收。子分支合回 `feat/tailwind-migration`；沒有 push、開 PR 或合併回 `main`。

## 範圍與參考

- [#129](https://github.com/minuet878-prog/HearWell/issues/129)、母規格 #119、ADR 0008、ADR 0009；對照表見 [`issue-127.md`](issue-127.md)、[`issue-128.md`](issue-128.md)。
- 模板：我的紀錄 `my_hearing.html`、比較框 `comparisons/*_history.html`、IOI-HA 常模圖 `ioi_ha_chart.html`／`ioi_ha_lines.html`、聽力圖清單／新增與編輯／檢視／比較／刪除，以及 `audiogram_point_value.html`、`audiogram_thumbnail.html`。
- React：`TrendChart.jsx`、`AudiogramApp.jsx`、`AudiogramChart.jsx`、`audiogram-main.jsx`、`audiogram-view-main.jsx`、`main.jsx`。
- 這張票新出現的換法：`flex-fill`→`flex-auto`（都是 `flex: 1 1 auto`）、`align-items-center`→`items-center`；聽力圖三顆按鈕 `w-100`→`w-full`（#125 記錄的 450px 問題，見 issue 留言）。

## 刻意的改動（本人 2026-10-21 決定在這張票修）

1. **`site.css` 基礎層補回 Bootstrap Reboot 的日期欄位規則**：日期欄位內「月／日／年」各段內距歸零。#124 補基礎樣式時漏了這條，新增／編輯聽力圖頁的日期欄位文字位置因此和 `main` 差了幾個像素（4 張截圖，約 1500 個像素）。
   - 不是這張票造成的：沒改 class 前就是這樣；試驗只補這一條、其他不動，history 群組 20 張就和 `main` 全部相同（試驗後已還原，再正式補上）。
   - 同一個原因的其他地方：Reboot 還有幾條表單相關規則沒補（數字欄位的上下鍵、搜尋欄位、顏色與檔案欄位、`progress`、`iframe`），全站沒有用到這些元素；email 欄位的 `direction: ltr` 在由左到右的頁面沒有作用。所以只補這一條。

## 驗收條件對照

| 條件 | 證明 |
|---|---|
| 1. 截圖只比這群頁面（手機與桌機），和 `main` 沒有超過反鋸齒的差異 | 截圖工具 history 群組：基準在 `origin/main`（`ef638a7`）拍，本分支再拍；**20 張全部逐像素相同**（補日期欄位規則之前 16 張相同、4 張不同，見上方）。涵蓋我的紀錄四份問卷分頁、聽力圖清單、新增、檢視、編輯、比較、刪除 × 390／1024 寬。因為改到全站共用的 `site.css`，同一個分支也重拍 public（26 張）和 answering（38 張），和 `main` 全部相同 |
| 2. 這些模板與 React 元件搜尋不到 Bootstrap 專屬 class | `screening/tests/test_tailwind.py:102`。加入本票檔案後列出 24 處，改之後通過 |
| 3. 既有聽力圖與趨勢圖 e2e（拖曳讀數、遮蔽開關、圖表日期、窄螢幕）全部通過 | e2e 全套通過，其中圖表日期 `e2e/main_flow.py:689` `test_trend_dates_stay_inside_and_apart`、窄螢幕 `:761` `test_audiogram_cards_fit_a_phone`。**「拖曳讀數」「遮蔽開關」本來就沒有 e2e**，是前端單元測試（`AudiogramApp.test.jsx`），已通過；e2e 的按鈕樣式檢查（`test_buttons_keep_their_colours_size_and_focus_ring`）會按遮蔽開關看顏色。自審後新增 `:777` `test_audiogram_entry_buttons_fill_their_column`：`:795` 遮蔽開關、清除、存檔三顆按鈕在 390、1024 寬都和欄寬相同；改回 `w-100` 時 6 項失敗（450px，欄寬 363／693px），改之後通過 |
| 4. 前端測試通過 | 13 檔、190 個通過 |

截圖沒拍到、靠數值對照確認的：1200px 以上的字級、趨勢圖的錯誤文字、沒有 JS 時的 `<noscript>` 提示、少於兩張聽力圖時的比較頁、數值輸入表收起來時裡面的標題。

## 自動驗證

| 檢查 | 結果 |
|---|---|
| Django 全套 | 646 個通過 |
| 前端 | 13 檔、190 個通過 |
| e2e `e2e.main_flow` 全套 | 43 個通過（含本票新增 1 個；在本分支跑，已包含 #128 的改動） |
| `npm run build --prefix frontend`、`ruff check` | 通過 |

截圖工具的 8765 埠被本機另一個專案佔用，沒有停它；兩邊都暫時改成 8766 拍，拍完已還原。

## 自審

和 #128 一起審，見 [`issue-128.md`](issue-128.md)。和本票有關的：

| 發現 | 處理 |
|---|---|
| 按鈕改成 `w-full` 只有截圖證明，沒有斷言（Spec） | 已補 e2e，先紅後綠（上方條件 3） |
| 「拖曳讀數」「遮蔽開關」沒有 e2e（Spec） | 照實記在條件 3；這張票不新增拖曳的 e2e |
| `site.css` 新規則的註解寫成只影響聽力圖，其實套用到全站日期欄位（Standards） | 已改註解 |

不需交叉審查：只改樣式，沒有修改計分、分級、門檻、資料 migration 或權限。

## 本人實際操作

- [ ] 我的紀錄：趨勢圖標題、摘要框、IOI-HA 常模圖、配戴比較框的間距。
- [ ] 新增聽力圖：遮蔽開關、清除、存檔三顆按鈕撐滿寬度（#125 驗收時發現遮蔽開關沒有置中）。
- [ ] 新增聽力圖：日期欄位的文字位置正常。
- [ ] 比較聽力圖：「右耳／左耳」兩顆按鈕平分寬度。
- [ ] 接受上方「刻意的改動」第 1 項。
