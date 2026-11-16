# sitemap、robots.txt 與 Search Console 清單（#586，規格 #583）

日期：2026-11-16。分支：`feat/586-sitemap`。

不需交叉審查：不碰計分、分級、門檻、migration、權限（規格 #583「審查」）。做了自審，見下方。

## 做了什麼

- **`/sitemap.xml`**：用 Django 內建的 sitemap 功能，列出公開頁面清單（#585）上的每個網址，現在 29 個。只有完整網址（`https://` 加主機），沒有更新日期、更新頻率、優先度。新增一題問答，sitemap 就自動多一個網址。
- **`/robots.txt`**：純文字三行：所有爬蟲、所有網址都可以讀，加上 sitemap 的完整網址。不擋任何頁面（ADR 0062：擋住的頁面讀不到禁止收錄標記，反而可能出現在搜尋結果）。
- **本人清單**：`docs/deployment/search-console.md`，部署文件索引加了「搜尋引擎」一段。
- 為了用 sitemap 功能，設定多裝一個 Django 內建的 `django.contrib.sitemaps`。它不建資料表，只是讓 Django 找得到 sitemap 的版型。

## 實作時的做法（請本人知道）

- **DNS 已經有一筆 Google 的驗證紀錄**。寫清單時查 `tingpal.tw` 的 TXT，除了寄信用的 SPF，還有一筆 `google-site-verification=…`，多半是設定 Google 登入時留下的。所以清單多了「第 0 步：先看 Search Console 裡是不是已經有 `tingpal.tw`」，有的話直接跳到提交 sitemap。這筆不確定是哪個帳號用的，清單寫明不要刪。
- **sitemap 與 robots.txt 自己也帶禁止收錄**：sitemap 是 Django 內建就加的，robots.txt 是 #585 的全站預設。意思是「這兩個檔案本身不要出現在搜尋結果」，搜尋引擎照樣會讀。
- **主機取自請求**：正式站的 `www` 和 `http://` 都會先轉到 `https://tingpal.tw`，所以 sitemap 上只會出現 `https://tingpal.tw/…`。本機用 `http://localhost` 開的話，sitemap 上的網址會是 `https://localhost…`，點了打不開；只影響本機手動點，不影響測試和正式站。
- **「不讀 session」沒有完全做到，我決定不改**。規格寫 sitemap 和 robots.txt「不用登入、不讀 session」。實際上全站的同意書檢查會先看「是不是已登入」，這一步會碰到 session。
  - 爬蟲不帶登入 cookie，所以不會讀到資料庫裡的 session，也不會被設 cookie，對搜尋引擎沒有影響。
  - 只有「已登入、還沒同意新版同意書」的人自己打開這兩個網址時，會被帶去同意頁。
  - 要改就得把它們加進同意書檢查的開放清單，那算碰到權限，按規則要交叉審查。為了一個實際上不會發生的情況不划算，所以維持現狀。您想改的話告訴我。

## 驗收條件

測試檔：T＝`screening/tests/test_sitemap.py`。

- [x] 規格驗收 9　sitemap 回 200、是合法的 sitemap（`application/xml`，用 sitemap 的命名空間解析得出每一筆），列出的網址跟公開頁面清單完全一樣：T:26、T:27、T:30
- [x] 規格驗收 10　每一筆都是完整網址，沒有更新日期、更新頻率、優先度：T:36（每一筆只有網址一個欄位）、T:37（`https://` 加主機開頭）
- [x] 規格驗收 11　robots.txt 回 200 的純文字，全部允許，寫出 sitemap 的完整網址：T:72、T:73、T:75（三行逐字比對，沒有任何擋頁面的行）
- [x] 規格驗收 12　sitemap 列出的每個網址沒登入打開都回 200：T:44
- [x] 規格驗收 7　已下架的題目不在 sitemap：T:53（拿掉一題後它的網址不在）、T:54（其他題還在）
- [x] 規格驗收 6 的後半　沒有題目的主題頁不在 sitemap：T:63（每個主題：頁面有列題目才在 sitemap）、T:65（現在確實有一個沒題目的主題，「網站怎麼用」加第一題那天要改這一行）
- [x] Search Console 清單寫好，部署文件的索引加一條連結：文件，無測試
- [x] 不需交叉審查，做自審

驗收 9、11 先寫測試、看它失敗（網址不存在，404），再寫程式。驗收 10、7 的測試一寫就通過（第一步就有這個行為），所以我暫時把 sitemap 改壞（加上優先度、多列一個不公開的註冊頁），確認 T:30、T:36 會失敗，再還原。

## 自動測試

2026-11-16，本機：

| 項目 | 結果 |
|---|---|
| Django 測試（`--parallel 4`） | 2639 項通過（自審修正之後） |
| `ruff check`、`ruff format --check` | 通過 |
| e2e（`e2e.main_flow --parallel 4`） | 444 項通過（自審修正之前的 commit；修正只搬了一個類別的位置、改了測試與文件，畫面沒有變） |

## 自審（Matt 的 `/code-review`，基準點 `origin/main`）

**Standards 軸**：沒有硬性違規。

- `https` 在 sitemap 和 robots.txt 各寫了一次，註解說兩者一致、程式卻沒共用 → robots.txt 改讀 sitemap 的設定。
- 公開頁面清單的模組原本只管「哪些是公開頁面」，又多了 sitemap 的格式設定 → sitemap 類別搬到跟 robots.txt 同一個檔案。
- 測試為了模擬「拿掉一題」要清掉清單的快取，等於知道清單有快取 → 不改：不清的話換題目測不出來，repo 裡已有一樣的寫法。
- 清單寫死「29 個」 → 不改：有註明是 2026-11-16 的數字，本人照做時拿來對照用。

**Spec 軸**：沒有一定要修的。

- 「沒有題目的主題不在 sitemap」的測試要靠現在剛好有空主題，以後加了題目會照樣綠燈卻沒在驗 → 補 T:65。
- 「合法的 sitemap」沒驗 `application/xml` → 補 T:27。
- 「不讀 session」沒有完全做到 → 見上面「實作時的做法」，維持現狀。
- 中文介面的選單名稱可能跟清單寫的不同 → 清單開頭註明對不上時以英文為準。

## 本人操作

這一張沒有要本人操作的驗收。合併、部署之後就可以做 #591：照 `docs/deployment/search-console.md` 從第 0 步開始。
