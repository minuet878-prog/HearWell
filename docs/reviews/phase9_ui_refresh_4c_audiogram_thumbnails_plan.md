# 4c 聽力圖縮圖：實作計畫

規格：`docs/specs/phase9_ui_refresh_4c_audiogram_thumbnails.md`（已確認）。第 4 步的計畫，等本人點頭才動手。

## 1. 座標計算放 Python（新檔 `screening/audiogram_thumbnail.py`）

- 一個函式 `thumbnail(points)`：輸入一張聽力圖的點，回傳畫圖需要的東西：
  - 每耳的線段：照大圖的規則分段，也就是照 `AIR_FREQUENCIES` 的順序，缺的頻率跳過，無反應的點斷開，只有一個點的段不畫線。
  - 每個氣導點的座標與耳別。
  - 格線的 y 座標、正常範圍的方框。
- 座標系：`viewBox` 是 120 × 90。橫軸用對數，250–8000 Hz；縱軸 −10 到 120 dB，往下是聽力越差。四邊各留 4 的邊距。
- 用到的頻率、dB 範圍、正常上限都從 `screening/audiogram.py` 匯入（`AIR_FREQUENCIES`、`DB_MIN`、`NORMAL_LIMIT`），不另外寫一份數字。
- 放在獨立的檔案，不放進 `audiogram.py`：`audiogram.py` 是判讀規則（規則 9），縮圖是畫面用的座標，兩者分開。

## 2. View 與模板

- `views.audiogram_list`：每張聽力圖算好縮圖、掛在物件上（`audiogram.thumbnail`）。
  - 點已經用 `prefetch_related("points")` 一次讀進來，這裡不會多查資料庫。
  - 為了讓判讀和縮圖共用同一批點，順便把判讀也改成在 view 裡算一次（現在模板呼叫 `audiogram.interpretation`，它也讀同一批預先載入的點，查詢數不變）。
- 新模板 `audiogram_thumbnail.html`：把上面的資料畫成 SVG，加上 `aria-hidden`。
- `audiogram_list.html`：
  - 卡片最前面放縮圖。
  - 日期、右耳、左耳各一行（右耳和左耳各包一個區塊）。
- `styles.css`：縮圖 6rem × 4.5rem、白底、灰框。

## 3. 測試（先寫、先確認失敗）

- 新檔 `screening/tests/test_audiogram_thumbnail.py`：
  - 直接測 `thumbnail()`：
    - 右耳 20／40／60 dB 是三個點，y 座標越來越大（驗收 2）。
    - 左耳的點有標成左耳；骨導不出現（驗收 3）。
    - 缺頻率時跳過、照樣連；遇到無反應就斷開（驗收 4）。
    - 沒有任何點時，回傳空的線段和點（驗收 5）。
  - 頁面測試：
    - 每張卡片有一個 `aria-hidden` 的 SVG，卡片仍是單一個連結（驗收 1）。
    - 1 張和 10 張聽力圖的查詢次數相同（驗收 6）。
    - 看不到別人的聽力圖（驗收 7）。
    - 右耳、左耳各一行（驗收 8）。
- `e2e/main_flow.py`：320px 寬時，聽力圖列表上每個程度標籤的高度都不超過一行（驗收 9）。
- 既有測試：聽力圖列表的斷言（`test_audiogram.py`、`test_layout.py` 用 regex 找「右耳：〔標籤〕」）預期仍然通過，如果卡片結構改動讓它們失敗，就照新結構更新，並在完成回報說明。

## 4. 不做

改大圖、比較頁、輸入頁、報告；縮圖互動；新增前端程式。

## 5. 驗證

Django、前端、build 後 e2e、`ruff check .`。突變試驗：把「無反應就斷開」拿掉、把縱軸方向反過來，確認測試會失敗。
