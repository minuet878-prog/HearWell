# 本人驗證 Search Console、提交 sitemap（#591，規格 #583）

日期：2026-11-16。本人照 [Search Console 清單](../deployment/search-console.md)操作，代理在對話中逐步帶著做，並從 Mac 核對正式站。

## 部署後代理先核對正式站

本人把 `main`（含 #585、#586）部署到 VPS 之後，代理從 Mac 打開正式站：

| 檢查 | 結果 |
|---|---|
| `https://tingpal.tw/robots.txt` | 200、`text/plain`；內容是 `User-agent: *`、`Allow: /`、`Sitemap: https://tingpal.tw/sitemap.xml` |
| `https://tingpal.tw/sitemap.xml` | 200、`application/xml`；29 個網址，都是 `https://tingpal.tw/…`；沒有 `lastmod`、`changefreq`、`priority` |
| sitemap 上的 29 個網址 | 逐一打開都回 200，都沒有 `X-Robots-Tag` |
| 登入頁、訪客選年齡頁 | 200，帶 `X-Robots-Tag: noindex` |

## 本人操作

- **第 0 步**：Search Console 的資源清單裡已經有 `tingpal.tw`（地球圖示，「網域」資源）。之前已用 DNS 驗證過（DNS 上原有的 `google-site-verification` 紀錄），第 1–3 步不用做。
- **第 4 步**：提交 `sitemap.xml`。狀態「成功」，上次讀取時間 2026/11/16，系統探索到的網頁 29（本人截圖）。
- **第 5 步**：網址檢查，兩個都按「測試線上網址」：
  - `https://tingpal.tw/family`：允許建立索引「是」。
  - `https://tingpal.tw/login`：允許建立索引「否」。

## 驗收條件

- [x] 規格驗收 28　網站驗證成功（「網域」資源，DNS 紀錄）；sitemap 提交後狀態「成功」，讀到的網頁數 29，跟 sitemap 一樣
- [x] 規格驗收 29　網址檢查：公開頁面（家人專區）允許建立索引；不公開的頁面（登入頁）不允許

## 順手改的

- 清單第 4 步的欄位名稱改成實際畫面上的「系統探索到的網頁」（原本寫「已找到的網頁」）；記下第一次提交時 Google 當場就讀完。

## 之後

- 「家屬用哪些字找到聽伴」看 Search Console 的「成效」→「搜尋結果」→「查詢」，上線幾天後才有資料。這是這個階段結束時要回答的問題之一。
- #589（標題與描述）上線後，Google 下次來讀時會換成新標題；不用重新提交 sitemap。
