# 前端設計重整 第 3 輪：實作計畫

規格：`docs/specs/phase-09/phase9_ui_refresh_3_structure.md`（已確認）。第 4 步的計畫，等本人點頭才動手。

## 1. 帳號設定頁（4.1）

- `screening/urls.py`：新增 `account` 網址（名稱 `account_settings`），跟既有的 `account/delete` 放在一起。
- `screening/views.py`：新增 `account_settings`，`@login_required`，只讀 `request.user`。
  - 同意日期：從 `request.user.consents` 取目前版本（`version >= CONSENT_VERSION`）中最新的一筆；沒有就顯示「還沒有同意」並連到同意頁。判斷有沒有同意，沿用既有的 `has_consented()` 那條規則，不另寫一套。
- `screening/middleware.py`：`account_settings` 加進 `OPEN_PAGES`（同意閘門放行），註解寫明理由：它是下載資料、刪除帳號的入口。
- 新模板 `templates/screening/account.html`：照 4.1 由上到下排。
  - 帳號資料用 `<dl>`（名稱—值的清單）。
  - 「刪除帳號」放在最下方，用 `mt-5 pt-4 border-top` 和上面隔開，紅色文字連結。
  - 出生年的顯示方式和聽力報告一致（西元年）。

## 2. 入口（4.2）

- `layout.html`：
  - 頁首「目前登入：<strong>名稱</strong>」整段包成連到帳號設定的 `<a>`，加 `aria-label="目前登入：名稱，帳號設定"`。這段文字開頭就是畫面上的字，符合「念出的名稱包含畫面上的字」。
  - 頁尾：已登入時多一個「帳號設定」。
- `my_hearing.html`：拿掉底部「下載我的資料／刪除帳號」那一行。
- `delete_account.html`：「回我的紀錄」「取消」改成連到帳號設定，文字改「回帳號設定」「取消」。
- `privacy.html`：兩處「到『我的紀錄』頁按……」改成「到『帳號設定』頁按……」。`PRIVACY_UPDATED_ON` 原本就是今天，不動；`CONSENT_VERSION` 不動。

## 3. 切換問卷（4.3）— 只改 CSS

- `styles.css` 的 `.history-tabs`：
  - 拿掉下方的整條底線。
  - 加 `flex-wrap: wrap`，放不下時自動換行。
  - 每顆改成圓角膠囊，寬度依文字。
  - 選中的那顆深藍實心，其他白底深藍外框，至少 2.75rem 高。
- 模板不動：每顆仍是連結、`aria-current` 照舊。

## 4. 首頁（4.4）

- `index.html`：
  - 副標換成新句子。
  - 拿掉「可達 10 年」那張卡片的大字，卡片內容換成 4.4 的兩句。
  - 原本卡片外面那句「本網站由執業聽力師開發……結果僅供參考……」，前半句搬進卡片，後半句拿掉。
  - 順序本來就是「標題 → 副標 → 按鈕 → 步驟 → 卡片」，只是把卡片後面那段併進卡片。

## 5. 趨勢圖分級文字（4.5）

- `frontend/src/TrendChart.jsx`：`ReferenceArea` 的 label 從 `insideTopRight` 改成 `insideTopLeft`。改一個字。

## 6. 測試（先寫、先確認失敗）

- 新檔 `screening/tests/test_account_settings.py`：驗收 1–9。
  - 帳號頁內容、順序（刪除在最後）；未登入；未同意可進入；未填；別人的資料不出現。
  - 頁首連結與 `aria-label`、頁尾登入前後差別；我的紀錄沒有下載與刪除；刪除頁的返回連結（一般、管理員）；隱私權頁的文字。
- 同一個檔案或 `test_layout.py`：驗收 10（膠囊、`aria-current`、一份時不顯示）、12（首頁順序與文字）。
- `frontend/src/TrendChart.test.jsx`：驗收 13（分級文字在繪圖區的左半邊，`text-anchor` 是 start）。
- `e2e/main_flow.py`：驗收 11。建五份問卷各一筆紀錄，在 320px 量每顆膠囊都在畫面內、不用左右捲動。
- 既有測試要跟著規格改的：
  - `test_pages.py` 的首頁順序 `HOME_ORDER`（phase4_ui_flow 的驗收，被本規格 4.4 取代）。
  - 頁首「目前登入：<strong>名稱</strong>」的兩個斷言（現在外面多包了一層連結）。

  理由會寫在完成回報裡。
- 驗收 14 人工：這輪改了 React（一個字），看畫面前要先 `npm run build --prefix frontend`。

## 7. 不做（照規格）

修改帳號資料、登出按鈕、改刪除或下載本身的流程、第 4 輪的東西、主導覽列、IOI-HA 標題區。

## 8. 驗證

Django、前端、build 後 e2e、`ruff check .`。突變試驗：把 `account_settings` 從同意閘門的放行名單拿掉、把膠囊的 `flex-wrap` 拿掉，確認測試會失敗。
