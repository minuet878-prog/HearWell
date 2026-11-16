# Google Search Console：驗證網站、提交 sitemap（規格 #583）

[回部署參考](README.md)

「讓家屬找得到」第 2 項（[拷問決定](../planning/found-by-family/search-basics-grill-decisions.md) Q8）裡本人要做的事，票是 #591。做完之後，Search Console 會告訴您：Google 收錄了哪些頁面、家屬是用哪些字搜到聽伴的。

每一步都寫了「做對了會看到什麼」；看到的不一樣就停下來，把畫面截圖給代理。Search Console 的介面可能是中文或英文，按鈕名稱兩種都寫了。

**開始之前**：sitemap 要先上線到正式站（#586 合併、部署完）。用瀏覽器打開下面兩個網址確認：

- `https://tingpal.tw/robots.txt`：看到三行字，最後一行是 `Sitemap: https://tingpal.tw/sitemap.xml`。
- `https://tingpal.tw/sitemap.xml`：看到一串 `https://tingpal.tw/…` 的網址（2026-11-16 是 29 個）。

| 步 | 內容 | 在哪裡做 | 要多久 |
|---|---|---|---|
| 0 | 看是不是已經驗證過 | Search Console | 一分鐘 |
| 1 | 新增「網域」資源，拿到驗證碼 | Search Console | 幾分鐘 |
| 2 | 把驗證碼加進 DNS | Gandi | 幾分鐘，生效最久幾小時 |
| 3 | 驗證 | Search Console | 幾分鐘 |
| 4 | 提交 sitemap | Search Console | 送出幾分鐘；Google 讀完要幾小時到幾天 |
| 5 | 用網址檢查看一個公開、一個不公開的頁面 | Search Console | 幾分鐘 |

---

## 0. 先看是不是已經驗證過

2026-11-16 代理查 DNS，`tingpal.tw` 已經有一筆 `google-site-verification=…` 的 TXT 紀錄：之前（可能是設定 Google 登入時）已經用某個 Google 帳號驗證過這個網域。

1. 打開 <https://search.google.com/search-console>，用設定 Google 登入時的那個 Google 帳號登入。
2. 點左上角的資源選單，看清單裡有沒有 **`tingpal.tw`**（前面是地球圖示，代表「網域」資源）。

- **有**：第 1–3 步已經做過了，直接跳到第 4 步。
- **只有 `https://tingpal.tw/`**（網址前置字元資源）：也可以用，但它不涵蓋 `www` 和 `http://`。照第 1 步另外新增「網域」資源；同一個帳號通常會馬上自動驗證成功，不用再改 DNS。
- **沒有**：可能是另一個 Google 帳號驗證的。換帳號再看一次；都沒有，就照第 1 步做。

**回報**：清單裡看到什麼（截圖），代理再告訴您從哪一步開始。

## 1. 新增「網域」資源

1. 打開 <https://search.google.com/search-console>，用您要管理網站的 Google 帳號登入。
2. 左上角的資源選單 →「新增資源」（Add property）。
3. 選左邊的 **「網域」**（Domain），不要選右邊的「網址前置字元」（URL prefix）。
   - 「網域」一次涵蓋 `tingpal.tw`、`www.tingpal.tw`、`http://` 和 `https://` 所有寫法，而且只能用 DNS 驗證，不用改網站程式（拷問 Q8）。
4. 輸入 `tingpal.tw`（不要加 `https://`、不要加 `www`）→「繼續」（Continue）。

**做對了會看到**：「透過 DNS 記錄驗證網域擁有權」（Verify domain ownership via DNS record）的視窗，裡面有一串 `google-site-verification=` 開頭的文字和一個「複製」（Copy）按鈕。

**這個視窗先不要關**，第 3 步還要回來按「驗證」。按「複製」，把那串文字整串複製起來。

## 2. 在 Gandi 加上驗證碼

Gandi 後台 → **Domain** → `tingpal.tw` → **DNS Records** → **Add record**：

| 欄位 | 填什麼 |
|---|---|
| Type | `TXT` |
| Name | `@`（代表 tingpal.tw 本身） |
| TTL | 不用改 |
| Text value | 第 1 步複製的整串，`google-site-verification=` 開頭；不用自己加引號 |

**注意：不要改到原本的兩筆。** 2026-11-16 `tingpal.tw` 本身已經有兩個 TXT 值：

- `v=spf1 include:_mailcust.gandi.net ~all`：寄信用的（[Resend 設定](resend-setup.md)第三段）。
- `google-site-verification=fG0I…`：之前的 Google 驗證（見第 0 步）。不確定是哪個帳號用的，**不要刪**。

做法：

- 正常情況：新增一筆，跟原本的並存。
- 如果 Gandi 說這個名稱已經有 TXT 紀錄、不讓您新增：改成**編輯**原本那筆，在裡面**多加一個值**（Gandi 叫 add value 或多一行），貼上這次的那串。原本的值都要留著，不要蓋掉。

**做對了會看到**：DNS Records 清單裡，名稱 `@`、類型 TXT 的值比原本多一個，`v=spf1 …` 還在。

加完 → **回報**。代理會用 `dig TXT tingpal.tw` 確認新的值查得到、原本的沒被改掉。

## 3. 驗證

回到第 1 步那個視窗，按 **「驗證」**（Verify）。

**做對了會看到**：「已驗證擁有權」（Ownership verified），接著進到 `tingpal.tw` 這個資源的首頁。

**如果說驗證失敗**：DNS 還沒生效，通常再等幾分鐘到一小時再按一次。超過幾小時還是失敗 → 截圖給代理。

視窗不小心關了：資源選單 → 選 `tingpal.tw` → 會再出現同一個驗證視窗。

## 4. 提交 sitemap

1. 左側選單 →「索引」（Indexing）→ **「Sitemap」**（Sitemaps）。
2. 「新增 Sitemap」（Add a new sitemap）的欄位前面已經寫好 `https://tingpal.tw/`，在後面輸入 `sitemap.xml` →「提交」（Submit）。

**做對了會看到**：「已成功提交 Sitemap」（Sitemap submitted successfully）。下方「已提交的 Sitemap」（Submitted sitemaps）多一列 `/sitemap.xml`。

- **狀態**（Status）一開始可能是「無法擷取」（Couldn't fetch）或空白：Google 還沒來讀，是正常的。隔天再看。
- 隔天應該是 **「成功」**（Success），**「已找到的網頁」**（Discovered pages）跟 sitemap 的網址數一樣（2026-11-16 是 29）。

**回報**：狀態和已找到的網頁數，截圖給代理（規格驗收 28）。

數字不一樣，或隔天還是「無法擷取」→ 截圖給代理。

## 5. 網址檢查

畫面最上方的搜尋列「檢查「tingpal.tw」中的任何網址」（Inspect any URL in "tingpal.tw"），一次檢查一個網址。

### 5-1 公開頁面：家人專區

1. 輸入 `https://tingpal.tw/family` → Enter。
2. 剛提交時多半顯示「網址不在 Google 服務中」（URL is not on Google）：Google 還沒收錄，是正常的。
3. 按右上角 **「測試線上網址」**（Test live URL），等它跑完。

**做對了會看到**：「網址可供 Google 使用」（URL is available to Google）。展開「網頁可用性」（Page availability），**「是否允許建立索引？」**（Indexing allowed?）寫 **「是」**（Yes）。

想讓 Google 早一點來：按「要求建立索引」（Request indexing）。不按也會來，只是慢一點。

### 5-2 不公開的頁面：登入頁

1. 輸入 `https://tingpal.tw/login` → Enter → **「測試線上網址」**（Test live URL）。

**做對了會看到**：「網址無法供 Google 使用」或「無法建立索引」（URL is not available to Google）。展開「網頁可用性」，「是否允許建立索引？」寫 **「否：在 'X-Robots-Tag' HTTP 標頭中偵測到『noindex』」**（No: 'noindex' detected in 'X-Robots-Tag' http header）。

這就是 ADR 0062 的「預設不收錄」：登入頁不會出現在搜尋結果。

**回報**：5-1、5-2 兩張截圖給代理（規格驗收 29）。

---

## 之後怎麼看

- **家屬用哪些字找到聽伴**：左側「成效」（Performance）→「搜尋結果」（Search results）→ 下方「查詢」（Queries）。上線幾天後才開始有資料，前幾週數字會很少。這是這個階段結束時要回答的問題之一。
- **哪些頁面被收錄**：左側「索引」→「網頁」（Pages）。不公開的頁面會列在「未建立索引」（Not indexed）、原因「已遭『noindex』標記排除」（Excluded by 'noindex' tag），這是對的。
- 新增公開頁面（例如第 3 項的「關於聽伴」）不用重新提交：sitemap 會自動多一個網址，Google 下次來讀時就會看到。
