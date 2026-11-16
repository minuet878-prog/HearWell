# 「讓家屬找得到」第 2 項：LINE 預覽與 Google 收錄的查證（2026-11-16）

[規劃](plan.md)第 2 項「先研究再提案」的查證結果。來源標記：【LINE】LINE 官方文件、【OGP】ogp.me、
【Google】Google 官方文件、【三方】第三方文章或實測。官方查不到的寫明查不到。

## 對這一項的影響（先看這裡）

- LINE 預覽只要三個標記：`og:title`、`og:description`、`og:image`。其他標記 LINE 不顯示。
- LINE 沒有公布預覽圖的尺寸與裁切方式，第三方說法互相矛盾。做法：圖做 1200×630（Facebook、iMessage 的官方建議），
  重點放在中央約 630×630 的範圍，被裁成正方形也看得懂；實際樣子要用手機貼一次才知道。
- LINE 官方清快取的工具（Page Poker）已經關掉。預覽一旦被 LINE 抓過，改了標題或圖不會馬上更新，已貼出的訊息也不會變。
  做法：標題與描述定稿後再開始分享；預覽圖檔名帶版本號。
- LINE 的爬蟲會不會理 `robots.txt`、頁面帶「禁止收錄」時預覽還會不會出現，沒有可靠來源，要實測。
  `robots.txt` 不要擋任何要有預覽的頁面。
- 「保證不被收錄」要用 noindex（頁面上的禁止收錄標記）並且允許爬蟲來讀；`robots.txt` 擋住的頁面，爬蟲讀不到 noindex，
  網址仍可能出現在搜尋結果。兩者不能疊用。
- sitemap 用完整網址、同一個主機；`lastmod` 不準就不要放；`changefreq`、`priority` Google 不看。
- 標題和描述 Google 沒有字數上限，只會依螢幕寬度截斷；中文大約顯示幾個字沒有可引用的來源。

## 1. LINE 讀哪些標記

- 【LINE】FAQ「How are URL previews generated in chats?」：只用 `og:title`、`og:description`、`og:image`，
  其他 OGP 標記（`og:url`、`og:site_name` 等）不會出現在預覽。
- 【LINE】退回規則（日文版寫得最細）：沒有 `og:title` 讀 `<title>`；沒有 `og:description` 讀 meta description 或內文，
  可能留空；沒有 `og:image` 會自動抓頁面內的圖。
- `twitter:card`：FAQ 沒提到。
- <https://developers.line.biz/en/faq/tags/line-app/>、<https://developers.line.biz/ja/faq/tags/line-app/>

## 2. 預覽圖的規格

- LINE 官方沒有公布尺寸、比例、檔案大小、格式、是否要 HTTPS 或完整網址。
- 【OGP】協定只定義 `og:image` 是圖片網址，另有 width、height、type、alt 等附屬屬性；範例都用完整網址。<https://ogp.me/>
- 【三方】聊天室的顯示比例：2019 年實測 1200×630 被裁成正方形小圖
  （<https://qiita.com/comorebi_notes/items/59461d77434dbfc79673>）；另一篇稱 2022 年 7 月改為橫式
  （<https://creatorzine.jp/article/detail/3259>，原文打不開，只看到搜尋摘要）。
- 【Facebook 官方】建議至少 1200×630、比例接近 1.91:1、上限 8MB。
  <https://developers.facebook.com/docs/sharing/webmasters/images/>
- 【Apple 官方】圖片寬至少 900px；建議圖上不要放文字；站名放 `og:site_name`，不要放進 `og:title`。
  <https://developer.apple.com/documentation/technotes/tn3156-create-rich-previews-for-messages>

## 3. 快取與清除

- 快取多久，官方沒公布。
- Page Poker 的網域 `poker.line.naver.jp` 2026-11-16 查不到（NXDOMAIN）。【三方】說 LINE 在 2025 年寄了關站通知
  （<https://huan.idv.tw/line-page-poker/>）；沒找到 LINE 官網公告。
- 【三方】替代做法：網址加 `?v=2`、圖檔名加版本號；已貼出的訊息不會更新。
  <https://zenn.dev/kazuma_horiike/articles/497bd4899e0dd0>

## 4. LINE 的爬蟲

- 官方查不到。【三方】2020 年的伺服器紀錄：User-Agent 是 `facebookexternalhit/1.1;line-poker/1.0`。
  <https://www.webmasterworld.com/search_engine_spiders/5006178.htm>
- 是否遵守 `robots.txt`、noindex 是否影響預覽：沒有可靠來源。

## 5. Google 搜尋

- 站內搜尋結果頁：【Google】建議不要讓它被爬。
  <https://developers.google.com/search/docs/crawling-indexing/url-structure>
- noindex 與 `robots.txt`：【Google】noindex 要生效，頁面不能被 `robots.txt` 擋住；meta 與 `X-Robots-Tag` 效果相同。
  <https://developers.google.com/search/docs/crawling-indexing/block-indexing>、
  <https://developers.google.com/search/docs/crawling-indexing/robots/intro>
- sitemap：【Google】完整網址；`lastmod` 只有準確時才採用；忽略 `priority` 與 `changefreq`。
  <https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap>；
  協定規定網址要跟 sitemap 同一主機，<https://www.sitemaps.org/protocol.html>
- 標題與描述：【Google】沒有字數上限；每頁獨立、寫成摘要、不堆關鍵字；品牌名簡短帶過。
  <https://developers.google.com/search/docs/appearance/snippet>、
  <https://developers.google.com/search/docs/appearance/title-link>

## 沒查到、要實測的

- LINE 聊天室現在把預覽圖裁成什麼比例。
- 帶「禁止收錄」的頁面（例如分享報告的封面）貼到 LINE 還有沒有預覽。
- LINE 快取多久。
