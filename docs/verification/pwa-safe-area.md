# 主畫面 App 的分頁膠囊太低、頁首頂端模糊

分支 `fix/pwa-safe-area`（從 `main` 開出），2026-11-12。只改畫面：不碰計分、門檻、資料或權限，不需要交叉審查。

## 問題與根本原因

本人用 iPhone 從主畫面打開聽伴（PWA），發現兩件事：

1. **分頁膠囊太低**：膠囊壓在螢幕底部的橫條（home indicator）上。
   - 原因：`layout.html` 的 viewport 沒有 `viewport-fit=cover`。少了它，iPhone 回報的安全距離（`env(safe-area-inset-*)`）全部是 0。分頁列的下緣寫的是 `6px + env(safe-area-inset-bottom)`，實際只剩 6px。
   - 本人的截圖量到膠囊離螢幕底約 6pt。
2. **頁首頂端模糊**：Logo、「聽伴」和「登出」按鈕的上半部糊掉，往下漸漸變清楚，「目前登入」那行已經清楚。
   - 原因：網站的 CSS 沒有任何模糊效果。這是 iOS 26 以後的系統行為：主畫面 App 會在狀態列下方再往下約 1.25rem 加一層柔邊模糊，網頁關不掉。
   - 頁首內容離狀態列太近，所以被蓋到。在 Safari 裡一般瀏覽不會這樣。

兩個問題都在 iOS 模擬器（iPhone 18 Pro Max，iOS 27.1）把網站加到主畫面後重現。

## 修正

- `layout.html`：viewport 加上 `viewport-fit=cover`。
- `site.css`：
  - 頁首補上狀態列的高度：`padding-top: env(safe-area-inset-top)`。加了 cover 之後，頁面會延伸到狀態列底下，頁首的白底會填滿狀態列，Logo 從狀態列下方開始。
  - 只有 iPhone 主畫面 App（`display-mode: standalone`，加上只有 iOS 認得的 `-webkit-touch-callout`）時，頁首再往下讓 1.5rem，讓 Logo 和登出落在系統模糊範圍外。Android 主畫面 App 和一般瀏覽器都不受影響。
  - 手機橫放：以下都加上左右安全距離，內容不會被相機凹口（動態島）擋到。
    - 內容區（`container`）左右留白取「0.75rem」和安全距離中較大的一邊。
    - 分頁列左右兩側。
    - 「回到頂端」按鈕的右邊與下緣。

## 測試

- 自動測試：`test_pages.py` 的「每頁都有 App 資訊」加一條斷言，要求每頁的 viewport 有 `viewport-fit=cover`。拿掉這個設定時，這條斷言會失敗。
- iOS 模擬器（主畫面 App）：
  - 修前：膠囊貼在螢幕最底，Logo 上半部糊掉。
  - 修後：膠囊停在橫條上方；Logo 和「聽伴」清楚；橫放時文字避開動態島。
- iOS 模擬器（Safari 一般瀏覽）：版面跟修前一樣，Logo 清楚，膠囊在 Safari 工具列上方。
- `env()` 在桌機瀏覽器和 Playwright 都是 0，所以 e2e 只能確認其他畫面沒有被改壞，測不到 iPhone 上的位置。

## 本人驗收

- [ ] 部署後，用自己的 iPhone 從主畫面打開：
  - 膠囊在底部橫條上方。
  - 頁首的 Logo、登出清楚。
