# 實作計畫：聽力圖輸入 第 1 批

規格：`docs/specs/phase5_audiogram.md`（已確認，33 條劇本）。分支 `feat/audiogram`。

## 整體分工

| 頁面 | 做法 | 原因 |
|---|---|---|
| 新增聽力圖（拖曳輸入） | React | 互動重；架構方向寫明「React 只做互動重的頁面」 |
| 單張檢視 | Django 頁面算好判讀卡＋數值表；圖用同一個 React 圖元件、唯讀模式 | 判讀由後端算（規則 9、10）；畫圖的程式只有一份，不用 Python 再畫一次 |
| 清單、刪除確認 | Django 頁面 | 沒有互動，跟「我的紀錄」一樣用 template |
| 存檔 | 新的寫入 API，帶收據編號（Idempotency-Key） | 沿用作答 API 的防連按做法（劇本 15） |

## 後端（Django）

1. **新增 `screening/audiogram.py`**：判讀規則，從 `~/audiogram_tool/audiogram/classify.py` 搬過來，不碰 Django。
   - 常數：氣導／骨導頻率清單、dB 範圍（氣導 -10–120、骨導 -10–80）、無反應的值（120／80）、程度門檻
   - `pta()`、`degree()`、`hearing_type()` 照搬
   - 新增 `interpret(points)`：回傳左右耳各自的四頻平均、程度、類型、是否含無反應、資料不足
2. **`screening/models.py`** 新增兩個 model（跟 `Submission`／`Answer` 同樣的形狀）：
   - `Audiogram`：`user`（PROTECT）、`tested_on`（檢查日期）、`created_at`、`idempotency_key`
   - `AudiogramPoint`：`audiogram`（**CASCADE**，見決定 A）、`ear`（R／L）、`conduction`（氣導／骨導）、`frequency`、`db`、`no_response`
   - 資料庫限制：同一張圖、同耳、同導程、同頻率只能一個點；`(user, idempotency_key)` 不重複
   - `Audiogram.interpretation()`：唯一的判讀入口，頁面跟 API 都走這裡（規則 10）
   - migration `0019`
3. **API**（`screening/api/`）：
   - `POST /api/audiograms/`：建立；驗證所有點（劇本 16），全有或全無；收據編號重送回 200、內容不同回 409
   - `GET /api/audiograms/{id}/`：單筆（POST 成功回同樣內容）；別人的回 404
   - 更新 `docs/api/schema.yaml`（有測試比對）
4. **頁面**（`screening/views.py`、`urls.py`、templates）：
   - `/audiograms`：清單（劇本 28、29、33）
   - `/audiograms/new`：掛 React 的空殼頁；沒有 JS 時顯示「需要開啟 JavaScript」
   - `/audiograms/<id>`：檢視（判讀卡、數值表、說明文字、刪除按鈕）
   - `/audiograms/<id>/delete`：GET 顯示「確定刪除？」，POST 才刪（見決定 B）
   - 全部 `login_required`、查詢都限定 `request.user`
5. **「我的紀錄」分頁籤**：把分頁籤拆成共用的小 template，多一個「聽力圖」分頁（見決定 C）
6. `styles.css`：聽力圖頁的樣式（rem）

## 前端（React）

1. **`frontend/src/audiogram.js`**（純函式，好測試）：座標換算、對齊 5 dB、找最近的頻率、拖過下緣變無反應、「放開位置＝原本的點就刪除」的判斷
2. **`AudiogramChart.jsx`**：SVG 聽力圖。符號、箭頭、連線（無反應不連）、放大鏡；可以是唯讀或可拖曳。拖曳用 pointer events（滑鼠、手指通用的事件）＋ `touch-action: none`（劇本 11：拖曳時頁面不捲動）
3. **`AudiogramApp.jsx`**：符號按鈕、提示文字、清除按鈕、可收合的數值表（每格一個下拉選單，含「無反應」）、檢查日期、存檔與錯誤訊息
4. 兩個新進入點：`audiogram-input`（新增頁）、`audiogram-view`（檢視頁的唯讀圖）；`vite.config.js` 加這兩個
5. `bundle.test.js` 加一條：新增頁不載入圖表套件（Recharts）、大小有上限

## 測試對應

- Django（`screening/tests.py` 新增測試類別）：劇本 12–33 的後端部分（判讀規則、API 驗證、IDOR 404、清單、刪除、查詢次數）
- 前端（vitest）：劇本 1–11 的互動部分、12–15 的前端行為
- 人工：劇本 11 的 320px＋200% 與「拖曳時頁面不捲動」，要你在手機上驗收
- 先寫測試、確認失敗，再寫實作

## 需要你決定

**A. 刪除時，點要跟著刪**
專案慣例是所有外鍵都用 PROTECT（有東西指著它就不准刪）。但點沒有聽力圖就沒有意義，而且刪除是這次要做的功能。
- 建議：點用 CASCADE（刪聽力圖時，它的點一起刪）；`user` 維持 PROTECT。
- 代價：跟「全部 PROTECT」的慣例不一致，要在 decisions/ 記一筆原因。

**B. 刪除怎麼確認**
- 建議：另一頁「確定要刪除 2026/10/16 的聽力圖嗎？」＋大按鈕。不靠 JavaScript，螢幕閱讀器讀得到，也是 Django 的標準做法。
- 另一種：瀏覽器內建的確認視窗（`confirm()`）。比較快，但字很小，長者容易看不清楚。

**C. 「我的紀錄」的分頁籤會一直顯示**
現在只答過一份問卷時不顯示分頁籤，沒有紀錄時也不顯示。加了「聽力圖」之後，不顯示就找不到入口。
- 建議：一律顯示（答過的問卷＋「聽力圖」）。沒有任何紀錄的人，也會看到「聽力圖」分頁籤。
- 代價：要改兩個既有測試（`test_single_questionnaire_has_no_tabs`、`test_no_records`），改成斷言「只有一個問卷分頁＋聽力圖」。
