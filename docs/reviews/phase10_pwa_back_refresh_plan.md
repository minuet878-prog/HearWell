# 實作計畫：PWA 返回鍵與下拉重整

規格：`docs/specs/phase10_pwa_back_refresh.md`　分支：`feat/pwa-back-refresh`

## 做法總覽

- **上一頁按鈕**：由 Django 樣板直接寫在標題列（首頁不寫），預設帶 `hidden`（隱藏）。
  一支小 JS 判斷「現在是全螢幕模式」才把它顯示出來。JS 沒載入 → 按鈕一直藏著，頁面其他部分不受影響（驗收 10）。
- **下拉重整**：同一支 JS 監聽手指的 `touchstart`／`touchmove`／`touchend`（觸控開始、移動、結束三個事件）。
  只在「全螢幕模式、頁面在最上方、主內容裡沒有表單欄位」時作用。
- **不用 React、不加套件**：這兩個功能是純 DOM（直接操作網頁元素）就做得到的小事，用 React 只會讓每一頁多載入 React。

## 要改的檔案

| 檔案 | 改什麼 |
|---|---|
| `frontend/src/pwa-nav.js`（新） | 約 40 行。① 判斷全螢幕：`matchMedia("(display-mode: standalone)")`（Android）或 `navigator.standalone`（iPhone 專用的屬性）。② 上一頁：有瀏覽紀錄就 `history.back()`，沒有就到首頁。③ 下拉重整：手指從頁頂往下拉超過 80px，提示改成「放開重新整理」，放開就 `location.reload()`；不夠就收回 |
| `frontend/src/pwa-nav.test.js`（新） | Vitest 單元測試（jsdom 模擬瀏覽器），測上面三段邏輯 |
| `frontend/vite.config.js` | 加一個入口 `pwa-nav` |
| `screening/templates/screening/layout.html` | 標題列左側：`HearWell` 前面加 `<button hidden>‹ 上一頁</button>`（首頁不輸出）；`<body>` 最上方加下拉提示的區塊（`aria-hidden`，螢幕閱讀器不唸，因為它只是手勢的視覺回饋）；每頁載入 `pwa-nav.js` |
| `screening/static/screening/styles.css` | 上一頁按鈕：白色外框配藍底、字級 rem、最小 2.75rem（約 44px）見方；左側「上一頁＋HearWell」綁成一組不拆行（驗收 13）；下拉提示的樣式 |
| `screening/tests/test_pages.py` | 加在現有的 `PwaTests`：首頁沒有按鈕、其他頁有按鈕且預設 `hidden`、按鈕是 `<button>` 且文字是「上一頁」、每頁都載入 `pwa-nav.js` |
| `e2e/main_flow.py` | 新增一個測試類別，用 `add_init_script` 把 `navigator.standalone` 設成 true，假裝是 iPhone 全螢幕：按鈕顯示與大小、從問卷列表按上一頁回到首頁、200% 字級 320px 寬的版面 |

## 驗收條件 → 測試

| 驗收 | 測在哪 |
|---|---|
| 1 一般瀏覽器看不到 | Vitest（不是全螢幕 → 按鈕保持隱藏、下拉不作用）＋ e2e（一般模式按鈕不可見） |
| 2 首頁以外看得到、≥44px | e2e |
| 3 首頁沒有 | Django＋e2e |
| 4 問卷列表 → 上一頁 → 首頁 | e2e |
| 5 沒有上一頁 → 首頁 | Vitest |
| 6、7、8 下拉門檻、不夠、不在頁頂 | Vitest |
| 9、9b 有表單不啟用；登出不算 | Vitest（`main` 裡有 form／input／select／textarea 就不啟用；表單只在標題列不算） |
| 10 沒 JS 也正常 | Django（按鈕預設 `hidden`） |
| 11 螢幕閱讀器唸「上一頁，按鈕」 | Django（是 `<button>`、可見文字就是名稱，不另加 aria-label） |
| 12、13 200% 版面 | e2e |
| 14 實機 | 人工，由你來 |

## 判斷「有表單」的規則

看 `<main>` 裡面有沒有 `form`、`input`、`select`、`textarea`。標題列的登出表單在 `<main>` 外面，自然不算。
聽力圖輸入頁是 React 畫的、沒有 `<form>`，但有下拉選單和勾選框，所以也會被擋。
在「手指碰到螢幕」的當下才檢查，React 晚一點才畫出來也抓得到。

## 一個邊角情況（先講）

「有沒有上一頁」用 `history.length > 1` 判斷。如果 iPhone 從背景回來時重新載入了某一頁，然後使用者往下點一頁再按上一頁回來，這時 `history.length` 是 2，但已經沒有更前面的頁了，再按一次會沒反應。
處理方式：按下去 0.5 秒後如果頁面還在原地，就改去首頁。多 3 行左右。

## 不做（照規格）

左右滑動手勢、重新整理按鈕、service worker、改動頁面內容或導覽列。
