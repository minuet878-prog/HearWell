# 0009 Tailwind 基礎層：留著 Preflight，再補回 Bootstrap 的預設

日期：2026-10-21（本人審定，#124；接續 ADR 0008）

## 情境

Tailwind 預設會先把所有元素歸零（Preflight）：標題沒有字級、清單沒有圓點、按鈕和輸入框沒有外框。網站原本靠 Bootstrap 的預設長相，遷移要畫面不變。另一種做法是拿掉 Preflight、直接搬 Bootstrap 的 Reboot，最接近原樣，但和一般 Tailwind 專案的習慣不同。

## 決定

- 留著 Preflight，在基礎層把網站用得到的 Bootstrap 預設一條條補回來（標題與 `.h1`–`.h6`、段落、清單、連結、表格、表單元件、`legend` 等）。
- 設計數值放在 `@theme`。token 名稱不能和模板裡還在用的 Bootstrap class 撞名：Tailwind 會照 token 名自動產生 class（例如 `--color-muted` 會生出 `.text-muted`），會悄悄改掉別頁的樣子。
- CSS 建置不壓縮（Tailwind optimize 與 Vite CSS minify 都關掉）：壓縮器會把 `rgba(…, 0.5)` 改成十六進位 alpha（128/255），數值就不是原本的了。下載大小靠 brotli 壓縮，還在上限內。

## 理由

用 Tailwind 的標準做法，以後的人照一般 Tailwind 的認知寫，不會踩到「這個專案沒有 Preflight」。補回的規則集中在一個地方，第 2a 階段要改預設外觀時，只改基礎層。

## 代價

補漏一條就是畫面差異，要靠截圖比對和瀏覽器量測一條條抓（#124 審查就抓到漏了 `.h1`–`.h6`）。每加一個 token 都要先查模板有沒有同名的 Bootstrap class，直到 #131 把 Bootstrap class 清乾淨。CSS 檔比壓縮版大一些。
