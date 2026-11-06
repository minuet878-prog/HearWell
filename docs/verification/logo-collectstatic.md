# 正式站 logo 消失

日期：2026-11-06；分支 `fix/logo-collectstatic`（從 `main` 的 `6606284` 開出）。
狀態：程式與自動驗證完成；**不需交叉審查**（不碰計分、門檻、資料或權限）。**iPhone 實機還沒確認**，只有部署後才看得到。

## 起因

本人回報正式站的 SVG logo 有問題。實際查看：頁首 logo 是一塊白色，在白底上像不見了。

## 根本原因

小鳥 logo 寫在 `site.css` 的 data URI（把圖形直接寫進 CSS 的寫法）裡，裡面有 `mask='url(%23bird)'`。部署時的 `collectstatic` 會掃描 CSS 裡所有的 `url(...)`，換成加了雜湊的檔名，流程是：

1. Django 的規則從最外層的 `url("data:...` 比對到第一個 `)`，也就是裡面的 `translate(28 33.5)`。開頭是 `data:`，所以略過。
2. 接著從那裡繼續掃，掃到裡面的 `url(%23bird)`，把它當成檔案路徑，改成 `url("#bird#bird")`。
3. 多出來的雙引號讓外層的字串提早結束，整段 CSS 失效，遮罩變成 `none`。

同一個圖形用在 3 個地方，都受影響：

| 位置 | 遮罩失效後 |
|---|---|
| 頁首 logo | 白色圖層蓋滿小圓塊 |
| 頁尾小拱門 | 藍色方塊 |
| 開始按鈕 | 跟文字同色的方塊 |

分頁圖示和主畫面圖示是獨立檔案，沒有受影響。

**為什麼沒抓到：** 測試設定（`config/test_settings.py`）刻意用不改檔名的儲存方式，本機預覽也不跑 `collectstatic`，只有正式部署才會。這是 #422 換 logo 時帶進來的。

## 修法

- `mask='url(%23bird)'` 改成 `mask='url%28%23bird%29'`。瀏覽器解碼後一樣是 `url(#bird)`，Django 找不到 `url(` 就不會動它。
- `test_standards.py` 新增 `CssDataUriTests`：`site.css` 的 data URI 裡不能有 `url(`，大小寫都算（Django 的規則不分大小寫）。

## 驗證

### 重現與修正

用暫時的設定在暫存資料夾跑真實的 `collectstatic`，不動正式環境。

| 條件 | 修之前 | 修之後 |
|---|---|---|
| 新的自動檢查 | 失敗，指向第 98 行 | 通過 |
| Vite 建置後 | `url(%23bird)` | `url%28%23bird%29` |
| `collectstatic` 後 | `url("#bird#bird")`，檔名雜湊 `edd2d7438fbc` 和正式站相同 | `url%28%23bird%29` |
| 3 處的遮罩（Chromium） | 都是 `none` | 都有圖形 |
| 畫面（Chromium） | logo 看不到、方塊 | 小鳥和耳朵都正常 |

### 全套

Ruff（`check`、`format --check`）通過；前端測試 363 個通過；Django 測試 1624 個通過；e2e 277 個通過。

### 待確認

- [ ] 部署後，本人用 iPhone 看頁首、頁尾與開始按鈕。

## 自審

標準軸、規格軸都沒有「要修」的項目。採用兩個小調整：把新測試移到不會隔開輔助函式的位置；讓檢查不分大小寫、不限 `data:image/`。

## 還留著的風險

- 新檢查只看原始碼，不看建置後的 CSS。目前沒有開壓縮（`cssMinify: false`），`url%28` 會原樣保留；日後開壓縮要再確認。
- 外層用單引號的 data URI 檢查不到。目前全部都是雙引號。
- CI 沒有跑 `collectstatic`，其他只在正式環境才出現的問題還是抓不到。
