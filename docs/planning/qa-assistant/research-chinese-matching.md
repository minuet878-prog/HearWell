# 問答小助手 FAQ 版：繁體中文問句比對方案研究

[回功能規劃](../README.md)

- 對應票：[#374](https://github.com/minuet878-prog/HearWell/issues/374)（地圖 [#371](https://github.com/minuet878-prog/HearWell/issues/371)，擋住 [#375](https://github.com/minuet878-prog/HearWell/issues/375)）
- 查核日期：2026-10-26
- 前提：不呼叫外部服務；FAQ 只有幾十到一兩百題；Django 5.2、PostgreSQL 18（正式站 Neon 免費方案、本機 Docker `postgres:18`）；部署在 Render，每次部署跑 `build.sh`。
- 原則：以第一手來源為準（官方文件、套件 repo、PyPI、原始碼）。沒有一手來源支持的推論會標「推論」。
- 信心程度：**高**＝讀過一手原文；**中**＝一手來源但只看到部分，或由原文推論；**低**＝沒有一手來源。
- 這份研究**沒有**在真的資料庫上跑過任何查詢（規則不碰資料庫）。第 6 節的數字是用 Python 照官方文件描述的演算法模擬出來的，不是 PostgreSQL 的實測值。

---

## 0. 結論（先看這裡）

**推薦：在 Python 裡做比對，不靠資料庫的搜尋功能。** 流程是「正規化 → 同義詞表換成標準詞 → 兩字一組（bigram）重疊計分」，再視需要加兩個小套件：OpenCC（簡轉繁）和 pypinyin（同音字容錯）。

理由三句話：

1. 一兩百題全部讀進記憶體比對，耗時可以忽略，不需要資料庫索引；比對邏輯是純函式，好寫測試，本機 Docker 和 Neon 跑出來一樣。
2. 資料庫端的三條路都有硬傷：`pg_trgm` 用「三個字一組」，對兩三個字的短問句（「耳朵癢」）分數極低（第 6 節）；PostgreSQL 內建全文檢索沒有中文；中文斷詞的 extension 中，`zhparser` 不在 Neon 支援清單上，Neon 的 `lakebase_tokenizer` 雖然 2026-10-16 剛支援中文，但本機 Docker 裝不到、文件沒提繁體中文，也不能自訂中文同義詞。
3. 斷詞套件（jieba）不是必要的：bigram 本身就繞過「中文沒有空格」，而 jieba 從 2020 年後沒有新版本，在 Render 免費方案（約 0.1 顆 CPU）上首次載入詞典還要多等幾秒。

**準確度的大概**：沒有真實問句的測試集，現在給不出百分比。可以確定的是相對排序：「同義詞表＋bigram」在短問句、換句話說、簡體字（加 OpenCC 後）都優於 `pg_trgm`；最難的是「字形相近的錯字」，所有方案都只能靠同義詞表把常見錯字一條一條加進去。建議 #375 或之後的 prototype 票先收 30–50 句長輩真實會打的問法當驗收集，再定門檻。

**要本人確認的事**：見第 8 節，最重要的是 Neon 資料庫的 `datctype`（只影響「要不要用 `pg_trgm`」，推薦方案不受影響）。

---

## 1. 五個要處理的問題，各方案擋不擋得住

| 問題 | A. 同義詞表＋bigram（Python） | B. `pg_trgm` | C. jieba 斷詞＋比對 | D. PG 全文檢索（內建／zhparser／lakebase） |
|---|---|---|---|---|
| 中文沒有空格 | 擋得住：bigram 不需要斷詞 | 部分：整句被當成一個「詞」，短問句分數極低 | 擋得住：這就是斷詞的用途 | 內建擋不住；zhparser、lakebase 擋得住 |
| 同義詞（助聽器／集音器／耳機） | 擋得住：同義詞表 | 擋不住：要另外做同義詞替換 | 要另外做同義詞表 | 內建同義詞字典要放伺服器檔案系統（Neon 不行）；lakebase 的中文模式沒有同義詞選項 |
| 簡體字 | 加 OpenCC 就擋得住 | 擋不住（要先轉繁） | jieba 不做簡繁轉換 | 未見文件說明繁體 |
| 注音選字錯誤（同音字） | 加 pypinyin 的拼音 bigram 可部分擋住 | 只剩部分分數 | 斷詞反而可能切壞 | 擋不住 |
| 字形相近的錯字 | 只能靠同義詞表逐條加 | 只剩部分分數 | 擋不住 | 擋不住 |

---

## 2. 方案 A：手寫同義詞表＋子字串／bigram（Python，記憶體內）

### 做法（建議的流程）

1. **正規化**：Python 標準函式庫 `unicodedata.normalize("NFKC", ...)` 把全形英數轉半形；去掉標點和空白；英文轉小寫。
2. **簡轉繁**（選用）：OpenCC 的 `s2twp`（簡體 → 台灣正體，含台灣慣用詞，例如「数据库 → 資料庫」）。
3. **同義詞換成標準詞**：一張手寫的表，例如「耳鳴、耳朵嗡嗡叫、耳朵有聲音 → 耳鳴」。表裡可以順便放已知常見錯字（「助聽氣 → 助聽器」）。
4. **計分**：把問句和每題 FAQ（題目＋本人寫的關鍵字）都切成兩字一組，算「問句的 bigram 有多少比例出現在這題」。分數最高的前幾題當答案，低於門檻就回「找不到」。
5. **同音容錯**（選用）：再用 pypinyin 把兩邊都轉成不帶聲調的拼音，用拼音再算一次 bigram，當作備用分數。

「兩字一組」是處理中日韓文字的常見做法：Elasticsearch 內建的 CJK 分析器就是把中日韓文字切成重疊的兩字一組（例如「東京都」→「東京」「京都」），底層是 Lucene 的 `CJKBigramFilter`。來源：[Elasticsearch CJK bigram token filter](https://www.elastic.co/docs/reference/text-analysis/analysis-cjk-bigram-tokenfilter)（信心：高）。

### 「集音器」的領域提醒

同義詞表不能把「集音器」直接換成「助聽器」。專案既有研究寫明集音器一般被當作非醫療器材，不得宣稱醫療效能（[助聽器研究「集音器、輔聽器和助聽器的差別」](../hearing-aid-guide/research.md)）。比較安全的做法是：「集音器」「耳機」各自對到一題「集音器、耳機和助聽器差在哪」，不要讓它們跟助聽器共用答案。這是同義詞表要由本人審核的原因之一。

### 準確度、維護、負擔、授權

- **準確度**：短問句（「耳朵癢」）、句子裡多了贅字（「戴助聽器耳朵很癢」）都抓得到（第 6 節模擬）。同義詞的效果完全取決於表寫得好不好。
- **維護成本**：同義詞表由本人維護，跟 FAQ 一起審核。表可以放在程式定義檔（像問卷定義那樣）或資料庫，這是 #375 之後的決定。上線後看「找不到答案」的提問來補表（地圖 #371 的「Not yet specified」已列）。
- **伺服器負擔**：一兩百題 × 每題幾十個 bigram，一次查詢是幾萬次集合運算，在 0.1 顆 CPU 上也是毫秒級（推論，信心：中；沒有實測）。不需要資料庫索引、不需要 migration、不動 `build.sh`。
- **授權**：只用標準函式庫時沒有授權問題。選用套件見第 5 節（OpenCC：Apache-2.0；pypinyin：MIT）。

---

## 3. 方案 B：`pg_trgm` 相似度

### 一手事實

- `pg_trgm` 把字串切成「三個字一組」（trigram）。**每個詞**前面補兩個空白、後面補一個空白；**非文字字元（非英數）會被忽略**。例如 `cat` 的 trigram 是 `"  c"`、`" ca"`、`"cat"`、`"at "`。來源：[PostgreSQL 18 文件 F.35 pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html)（信心：高）。
- 三個比較函式：`similarity`（兩字串整體的相似度，0–1）、`word_similarity`（第一個字串和第二個字串「任一連續片段」的最高相似度）、`strict_word_similarity`（片段邊界要對齊詞邊界）。預設門檻：`similarity_threshold` 0.3、`word_similarity_threshold` 0.6、`strict_word_similarity_threshold` 0.5。同上來源（信心：高）。
- `pg_trgm` 是「trusted」extension：有資料庫 `CREATE` 權限的非 superuser 就能安裝。同上來源（信心：高）。
- GIN／GiST 索引（`gin_trgm_ops`）可以加速 `LIKE`、`ILIKE`、正規表示式，而且不必從字首比對。同上來源（信心：高）。一兩百題用不到索引。
- Neon 支援 `pg_trgm` 1.6（PG14–PG18）。來源：[Neon Postgres extensions](https://neon.com/docs/extensions/pg-extensions)（信心：高）。
- Django 5.2 有 `TrigramSimilarity`、`TrigramWordSimilarity` 和 `trigram_similar`、`trigram_word_similar` lookup；要把 `django.contrib.postgres` 加進 `INSTALLED_APPS`，並用 `TrigramExtension` migration 安裝 extension。來源：[Django 5.2 PostgreSQL full text search](https://docs.djangoproject.com/en/5.2/ref/contrib/postgres/search/)、[Django 5.2 PostgreSQL lookups](https://docs.djangoproject.com/en/5.2/ref/contrib/postgres/lookups/)（信心：高；以 context7 查 5.2 版文件）。目前 `config/settings.py` 的 `INSTALLED_APPS` 沒有 `django.contrib.postgres`。

### 中文字算不算「文字」：取決於資料庫的 `LC_CTYPE`

- `pg_trgm` 判斷是不是文字字元用 `ISWORDCHR`，也就是 `t_isalnum_with_len`。來源：[pg_trgm 原始碼 `trgm.h`（REL_17_STABLE）](https://github.com/postgres/postgres/blob/REL_17_STABLE/contrib/pg_trgm/trgm.h)（信心：高）。
- `t_isalnum` 的邏輯：如果字元只有 1 byte **或資料庫的 ctype 是 `C`**，就用 C 函式庫的單位元組 `isalnum`；否則轉成寬字元用 `iswalnum`。PG17 和 PG18 都是這樣。來源：[`ts_locale.c`（REL_17_STABLE）](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/backend/tsearch/ts_locale.c)、[`ts_locale.c`（REL_18_STABLE）](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/tsearch/ts_locale.c)（信心：高）。
- **推論**（信心：中）：資料庫 ctype 如果是 `C`，中文字（3 bytes）會被當成非文字字元而**整個忽略**，`pg_trgm` 對中文完全沒作用。ctype 是 `C.UTF-8` 或 `en_US.utf8` 時才會走 `iswalnum`。glibc 的 `C.UTF-8` 的 LC_CTYPE 是 `copy "i18n_ctype"`（[glibc `localedata/locales/C`](https://github.com/bminor/glibc/blob/master/localedata/locales/C)），i18n 字元分類涵蓋 Unicode 漢字，所以中文應該被當成文字。
- Neon：「Neon 現在預設用 `C.UTF-8` collation」，以前預設是 libc 的 `C`（[Neon changelog 2024-11-15](https://neon.com/docs/changelog/2024-11-15)、[Neon Postgres compatibility](https://neon.com/docs/reference/compatibility)）；資料庫建立後不能改 encoding 或 collation（同上）。本專案 2026-10-01 才改用 Neon（[`docs/decisions/deploy.md`](../../decisions/deploy.md)），推測是 `C.UTF-8`，**但沒有實際查證**（見第 8 節）。
- 本機 Docker：`postgres` 官方映像設定 `ENV LANG en_US.utf8`（[docker-library/postgres Dockerfile](https://github.com/docker-library/postgres/blob/master/18/bookworm/Dockerfile)，信心：高）。本機和 Neon 的 locale 不一樣，但兩者應該都把中文當文字（推論）。

### 中文的實際問題（推論，信心：中）

中文句子沒有空格，整句是一個「詞」，trigram 是連續三個字。長輩的問句常常只有兩三個字（「耳鳴」「耳朵癢」），三字一組加上句首句尾補空白之後，跟 FAQ 題目共用的 trigram 很少。第 6 節模擬：「耳朵癢」對「戴助聽器耳朵癢怎麼辦」的 `similarity` 約 0.07，遠低於預設門檻 0.3；同一題用 bigram 覆蓋率是 1.0。

### 準確度、維護、負擔、授權

- **準確度**：長問句、跟題目很像的問句還可以；短問句和關鍵字式問句差。同義詞、簡體字都要另外處理。
- **維護成本**：門檻要調；同義詞還是要手寫表，只是換成在 SQL 前處理。
- **部署負擔**：要加 `django.contrib.postgres`、一個 `TrigramExtension` migration；`build.sh` 本來就會跑 `migrate`，不用改。本機 Docker 和 Neon 都有 `pg_trgm`。
- **授權**：PostgreSQL License（PostgreSQL 內建 contrib 模組）。

---

## 4. 方案 C：斷詞套件

### jieba

- 授權 MIT；最新版 0.42.1，2020-01-20 發布；PyPI 只有原始碼套件（sdist，19.2 MB），沒有 wheel；classifier 只列到 Python 3.4。來源：[PyPI jieba](https://pypi.org/project/jieba/)（信心：高）。
- 繁體：附的 `dict.txt.big` 詞典「對繁體支援較好」，用 `jieba.set_dictionary()` 載入；可用 `load_userdict`、`add_word`、`suggest_freq` 自訂詞；`cut_for_search` 會把長詞再切短以提高召回。詞典是第一次用到時才載入，官方說初始化「1–3 秒」。jieba 不做簡繁轉換。來源：[fxsjy/jieba README](https://github.com/fxsjy/jieba)（信心：高）。
- jieba 讀詞典的方式：先 `import pkg_resources`，失敗才退回直接開檔。來源：[`jieba/_compat.py`](https://github.com/fxsjy/jieba/blob/master/jieba/_compat.py)（信心：高）。`pkg_resources` 屬於 setuptools，未來版本移除時會走退回路徑，應該還能用（推論，信心：低；沒有實測）。
- **負擔**（推論，信心：中）：官方的 1–3 秒是一般電腦的數字；Render 免費方案約 0.1 顆 CPU（[Render compute plans](https://render.com/docs/compute-plans)），閒置 15 分鐘後會休眠、喚醒約一分鐘（[Render free](https://render.com/docs/free)），醒來後第一個提問可能還要再多等幾秒到十幾秒載詞典。
- **準確度**：斷詞對「找 FAQ」幫助有限：問句被切成詞之後，還是要做同義詞和比對。斷詞錯了反而會漏（例如錯字讓詞切壞）。對一兩百題的規模，bigram 已經夠用（推論，信心：中）。

### CKIP Transformers（中研院，繁體中文）

- 專為繁體中文，有斷詞、詞性、實體辨識；需要 PyTorch 和 HuggingFace Transformers；模型 4M–102M 參數；可以只用 CPU。**程式碼授權 GPL-3.0**。來源：[ckiplab/ckip-transformers](https://github.com/ckiplab/ckip-transformers)（信心：高）。
- 不適合：PyTorch 本身就很大，Render 免費方案只有 512 MB 記憶體（[Render compute plans](https://render.com/docs/compute-plans)）；GPL-3.0 對本專案的授權影響要另外評估。

### Lindera（Rust，有 Python 綁定）

- MIT；有 jieba 和 CC-CEDICT 兩種中文詞典；`pip install lindera`。來源：[lindera/lindera](https://github.com/lindera/lindera)（信心：中，repo 首頁沒說繁體支援）。Neon 的 `lakebase_tokenizer` 就是用它（見第 5 節）。

---

## 5. 方案 D：PostgreSQL 全文檢索

### 內建全文檢索：沒有中文

- 預設 parser 判斷「字母」靠資料庫的 `lc_ctype`；文件沒有提到不留空格的語言。來源：[PostgreSQL 18 文件 12.5 Parsers](https://www.postgresql.org/docs/current/textsearch-parsers.html)（信心：高）。**推論**（信心：中）：一整串中文會變成一個很長的 token，無法用詞查。
- 內建的詞幹（Snowball）沒有中文。來源：[Snowball algorithms](https://snowballstem.org/algorithms/)（信心：高）。
- 內建同義詞字典和 thesaurus 的檔案要放在伺服器的 `$SHAREDIR/tsearch_data/`。來源：[PostgreSQL 18 文件 12.6 Dictionaries](https://www.postgresql.org/docs/current/textsearch-dictionaries.html)（信心：高）。Neon 是託管服務，不能放檔案（推論，信心：中）。

### zhparser

- 以 SCWS（簡易中文分詞）為基礎的 PostgreSQL 中文全文檢索 extension；要自己編譯安裝 SCWS 和 zhparser；建立 extension 和自訂詞庫要 superuser；預設詞典是簡體，繁體要另外下載 XDB 詞典；授權是寬鬆的 COPYRIGHT 聲明（沒有標準授權名稱）。來源：[amutu/zhparser](https://github.com/amutu/zhparser)（信心：高）。
- **Neon 不支援**：Neon 的 extension 清單沒有 `zhparser`（也沒有 `pg_jieba`、`pg_bigm`、`pgroonga`）。Neon 說想要清單外的 extension 可以向客服或 Discord 提出，但「不保證支援」。來源：[Neon Postgres extensions](https://neon.com/docs/extensions/pg-extensions)（信心：高）。

### Neon 的 Lakebase Search（`lakebase_tokenizer`）

- 2026-10-16 起 `lakebase_tokenizer` 0.2.0 支援中日韓，內建 `tokenizer_chinese` 設定；輸出一般的 `tsvector`，可以配 GIN 索引或 `lakebase_text` 做 BM25 排序。來源：[Neon changelog 2026-10-16](https://neon.com/docs/changelog/2026-10-16)（信心：高）。
- 中文用 Lindera 加 Jieba 詞典；`tokenizer_chinese` 用 `mixed` 模式（保留斷詞結果，再補較短的詞）；要求 PG16 以上。文件的例子是簡體（「现代分布式文件系统架构」），**沒有提到繁體**；中文模式（`tokenizer_morph`）的選項只有 Language、Mode、Normalize、Lowercase、Stemmer，**同義詞和停用詞只在另一種 tokenizer 有**。來源：[Neon lakebase_tokenizer](https://neon.com/docs/extensions/lakebase-tokenizer)（信心：高）。
- 文件沒寫：免費方案能不能用、授權、能不能在本機或 Docker 安裝。來源：同上、[Neon Lakebase Search](https://neon.com/docs/ai/lakebase-search)（信心：高，指「文件沒寫」這件事）。
- Neon 原本的 `pg_search`（ParadeDB）已標「Unavailable」「deprecated」，改推 Lakebase Search。來源：[Neon Postgres extensions](https://neon.com/docs/extensions/pg-extensions)（信心：高）。
- **不適合現在用的原因**：本機 Docker 和 CI 的 PostgreSQL 沒有這個 extension，測試和正式站會不一致；剛上線十天；繁體支援和同義詞都不確定；把比對綁在單一廠商的專有 extension 上，之後換資料庫平台要重寫。

### Neon extension 支援整理（來源：[Neon Postgres extensions](https://neon.com/docs/extensions/pg-extensions)，查核日 2026-10-26）

| extension | Neon 支援 | 備註 |
|---|---|---|
| `pg_trgm` | 有，1.6（PG14–18） | trusted，不需要 superuser |
| `unaccent` | 有，1.1（PG14–18） | 對中文沒用 |
| `fuzzystrmatch` | 有（PG16–18 為 1.2） | Levenshtein、Soundex 等；文件以英文為主，對中文用處小（推論） |
| `pgvector` | 有（PG18 為 0.8.6） | 語意搜尋要先算向量，需要模型，留給 RAG 版 |
| `lakebase_tokenizer` | 有，0.2.0（PG16 以上） | 見上 |
| `rum` | PG14–17 有，PG18 沒有 | 本專案是 PG18 |
| `zhparser`、`pg_jieba`、`pg_bigm`、`pgroonga` | 清單上沒有 | 可以申請，不保證 |
| `pg_search` | 不可用、已淘汰 | — |

---

## 6. 模擬：三字一組 vs 兩字一組（Python 模擬，不是 PostgreSQL 實測）

照第 3 節官方描述的切法（每個詞前補兩個空白、後補一個），拿一題 FAQ「戴助聽器耳朵癢怎麼辦」比對五種問法。`word_similarity` 欄是我照官方定義寫的近似算法，跟 PostgreSQL 的實作可能有出入。

| 長輩打的問句 | trigram `similarity`（預設門檻 0.3） | `word_similarity` 近似（預設門檻 0.6） | bigram 覆蓋率 |
|---|---|---|---|
| 耳朵癢 | 0.07 | 0.25 | 1.00 |
| 助聽器 | 0.07 | 0.25 | 1.00 |
| 戴助聽器耳朵很癢 | 0.43 | 0.67 | 0.71 |
| 戴助聽氣耳朵癢（同音錯字） | 0.27 | 0.38 | 0.67 |
| 带助听器耳朵痒（簡體） | 0.06 | 0.12 | 0.33 |

讀法：

- 短問句在 `pg_trgm` 預設門檻下會被判「找不到」，bigram 則完整命中。門檻調低可以救一部分，但會讓不相關的題目也冒出來（推論）。
- 簡體字兩種方法都不行，要先用 OpenCC 轉繁。
- 同音錯字兩種方法都掉分，拼音 bigram（第 7 節）或同義詞表補錯字可以救回來。
- 這只是示意。「助聽器」也會命中所有含「助聽器」的題目，所以實際計分還要考慮多題同分時怎麼排（例如關鍵字加權），這是 prototype 要試的。

---

## 7. 輔助套件

| 套件 | 用途 | 授權 | 安裝負擔 | 來源 |
|---|---|---|---|---|
| OpenCC | 簡轉繁，`s2twp` 轉成台灣正體並換台灣慣用詞 | Apache-2.0 | 1.4.2（2026-08-22）；有 CPython 3.13 的 Linux x86_64、macOS arm64 wheel；Linux wheel 2.4 MB | [BYVoid/OpenCC](https://github.com/BYVoid/OpenCC)、[PyPI OpenCC](https://pypi.org/project/OpenCC/)（信心：高） |
| pypinyin | 漢字轉拼音或注音（`Style.BOPOMOFO`），處理同音選字錯誤；`heteronym=True` 取多音字的所有讀音 | MIT | 0.55.0（2025-07-20）；純 Python wheel（`py2.py3-none-any`），840 kB；README 說繁體是「簡單支援」 | [mozillazg/python-pinyin](https://github.com/mozillazg/python-pinyin)、[PyPI pypinyin](https://pypi.org/project/pypinyin/)（信心：高） |
| RapidFuzz | 字串模糊比對（`ratio`、`partial_ratio`、`process.extract`） | MIT | Linux x86_64、macOS、Windows 有 wheel | [rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz)（信心：高；README 沒寫 Unicode 字元層級的行為，信心：低） |
| `difflib`（標準函式庫） | `SequenceMatcher` 字元層級相似度 | Python 授權 | 不用安裝 | Python 標準函式庫 |

**注音選字錯誤的處理思路**（推論，信心：中）：長輩用注音輸入法選錯字，錯字通常跟正確字**同音**（助聽「氣」／助聽「器」）。兩邊都轉成不帶聲調的拼音（`qi`）再比 bigram，就會一樣。代價是同音不同義的詞也會被拉近，所以拼音分數只當備用，權重要比字面分數低。字形相近的錯字（手寫輸入或眼花選錯）沒有便宜的通用解法，只能靠同義詞表逐條收錄。

---

## 8. 還沒查到、要本人確認的事

1. **Neon 資料庫的 `datctype`**（只影響方案 B）：本人可以在 Neon SQL Editor 跑唯讀查詢 `SELECT datname, datcollate, datctype FROM pg_database;`。如果是 `C`，`pg_trgm` 對中文完全無效；如果是 `C.UTF-8`，就照第 3 節的分析。這次研究依規則沒有連資料庫。
2. **真實準確率**：要先有長輩實際會打的問句。建議在 prototype 票收 30–50 句（含短問句、口語、錯字、簡體），用它們調門檻。
3. **Lakebase 的細節**：免費方案能不能用、授權、繁體中文效果、能不能本機安裝，文件都沒寫。如果以後 FAQ 變成上千題或做 RAG 版，再回頭查。
4. **jieba 在 Python 3.13 和新版 setuptools 的相容性**、**pypinyin 對繁體多音字的正確率**：都沒有實測（規則不裝套件、不跑程式）。推薦方案可以先不用 jieba；pypinyin 是選用的。
5. **CKIP 的 GPL-3.0** 對本專案的影響沒有評估，因為記憶體限制已經排除它。
6. **一次查詢的實際耗時**：第 2 節的「毫秒級」是推論，實作時用測試量一次。

---

## 9. 建議給 #375 的選項

| 選項 | 內容 | 代價 | 建議 |
|---|---|---|---|
| 1 | 方案 A 最小版：正規化＋同義詞表＋bigram，只用標準函式庫 | 簡體字、同音錯字只能靠同義詞表 | 先做這個，用驗收集看效果 |
| 2 | 選項 1＋OpenCC（簡轉繁） | 多一個 2.4 MB 的套件 | 如果驗收集裡有簡體問句就加 |
| 3 | 選項 2＋pypinyin（同音容錯） | 多一個 840 kB 的純 Python 套件；要調拼音分數的權重 | 如果驗收集裡同音錯字常見就加 |
| 4 | `pg_trgm` | 要加 migration 和 `django.contrib.postgres`；短問句表現差；同義詞還是要手寫 | 不建議當主力 |
| 5 | jieba 斷詞 | 2020 年後沒更新；冷啟動多等幾秒 | 不建議 |
| 6 | Neon `lakebase_tokenizer` | 本機和 CI 沒有；繁體與同義詞不確定；綁單一廠商 | 不建議（FAQ 規模也用不到） |

---

## 來源清單

- PostgreSQL 18 文件：[pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html)、[Text search parsers](https://www.postgresql.org/docs/current/textsearch-parsers.html)、[Text search dictionaries](https://www.postgresql.org/docs/current/textsearch-dictionaries.html)
- PostgreSQL 原始碼：[`contrib/pg_trgm/trgm.h`（REL_17_STABLE）](https://github.com/postgres/postgres/blob/REL_17_STABLE/contrib/pg_trgm/trgm.h)、[`src/backend/tsearch/ts_locale.c`（REL_17_STABLE）](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/backend/tsearch/ts_locale.c)、[同檔（REL_18_STABLE）](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/tsearch/ts_locale.c)
- glibc：[`localedata/locales/C`](https://github.com/bminor/glibc/blob/master/localedata/locales/C)（GitHub 鏡像；官方 sourceware.org 擋自動讀取）
- Django 5.2 文件：[PostgreSQL full text search](https://docs.djangoproject.com/en/5.2/ref/contrib/postgres/search/)、[PostgreSQL lookups](https://docs.djangoproject.com/en/5.2/ref/contrib/postgres/lookups/)
- Neon：[Postgres extensions](https://neon.com/docs/extensions/pg-extensions)、[Postgres compatibility](https://neon.com/docs/reference/compatibility)、[Changelog 2024-11-15](https://neon.com/docs/changelog/2024-11-15)、[Changelog 2026-10-16](https://neon.com/docs/changelog/2026-10-16)、[Lakebase Search](https://neon.com/docs/ai/lakebase-search)、[lakebase_tokenizer](https://neon.com/docs/extensions/lakebase-tokenizer)
- Render：[Compute plans](https://render.com/docs/compute-plans)、[Deploy for free](https://render.com/docs/free)
- Docker：[docker-library/postgres 18 Dockerfile](https://github.com/docker-library/postgres/blob/master/18/bookworm/Dockerfile)
- 套件：[jieba repo](https://github.com/fxsjy/jieba)、[jieba `_compat.py`](https://github.com/fxsjy/jieba/blob/master/jieba/_compat.py)、[PyPI jieba](https://pypi.org/project/jieba/)、[zhparser](https://github.com/amutu/zhparser)、[CKIP Transformers](https://github.com/ckiplab/ckip-transformers)、[Lindera](https://github.com/lindera/lindera)、[OpenCC](https://github.com/BYVoid/OpenCC)、[PyPI OpenCC](https://pypi.org/project/OpenCC/)、[python-pinyin](https://github.com/mozillazg/python-pinyin)、[PyPI pypinyin](https://pypi.org/project/pypinyin/)、[RapidFuzz](https://github.com/rapidfuzz/RapidFuzz)
- 其他：[Snowball algorithms](https://snowballstem.org/algorithms/)、[Elasticsearch CJK bigram token filter](https://www.elastic.co/docs/reference/text-analysis/analysis-cjk-bigram-tokenfilter)
- 專案內：[`docs/decisions/deploy.md`](../../decisions/deploy.md)（2026-10-01 改用 Neon）、[助聽器研究](../hearing-aid-guide/research.md)（集音器的法律地位）
