# 問答小助手 RAG 版：供應商資料政策、成本與 pgvector 可行性

[回功能規劃](../README.md)

- 對應票：[#378](https://github.com/minuet878-prog/HearWell/issues/378)（地圖 [#371](https://github.com/minuet878-prog/HearWell/issues/371)，結果給 [#379](https://github.com/minuet878-prog/HearWell/issues/379) 拷問用）
- 查詢日期：**2026-10-26**（以下所有連結都是這天讀的；各頁自己標的更新日期另外寫在括號裡）
- 原則：只用官方文件、定價頁、模型卡。沒有官方數字的地方寫「假設」或「未查到」，不補猜測。
- 信心程度：**高**＝官方原文直接寫；**中**＝官方來源但要推論，或只有官方部落格／文章；**低**＝沒有一手來源。
- 本研究沒有呼叫任何付費 API、沒有動資料庫、沒有改程式。

名詞先講一句：
- **RAG**：先從自己的資料庫找出相關段落，再把段落交給 AI 組成答案。
- **embedding（向量）**：把一段文字轉成一串數字，意思相近的文字數字也相近，用來「找相關段落」。
- **token**：AI 計價的單位，大約是一個字或半個字。**MTok** ＝一百萬個 token。
- **ZDR（zero data retention，零保存）**：供應商回完答案後不把你的提問和回答存起來。

---

## 結論（先看這段）

1. **資料政策**：Claude API、OpenAI API、Gemini **付費** API 預設都不拿 API 資料訓練。Gemini **免費**額度會拿來訓練、還可能有人工審閱，健康相關提問不能用免費額度。Voyage（Anthropic 推薦的 embedding 供應商）預設可能收集資料改進模型，**要有付款方式才能關掉**。
2. **零保存**：Claude 和 OpenAI 都要找業務申請，官方沒寫申請門檻。沒有零保存時，Claude 的商用預設是 30 天內刪除（違規例外最長 2 年）。
3. **成本很低**：用 Claude Haiku 5.5，每題上限約 **US$0.0012**，每月 1 萬題上限約 **US$12.7**（含美國限定加價）。改用 Sonnet 5.5 約貴 20 倍、Opus 5.5 約貴 40 倍。embedding 的費用相對小到可以忽略。
4. **pgvector**：Neon 的 Postgres 18 有 pgvector **0.8.6**，免費方案也能用。本機和 CI 現在用的 `postgres:18` 映像要換成 `pgvector/pgvector:0.8.6-pg18`，版本才會跟 Neon 一致。Django 用 `pgvector` 套件（0.5.1）接。
5. **Render 免費方案**：512 MB 記憶體、0.1 CPU，**自架 embedding 模型放不下**，要用 API 型 embedding。對外 HTTPS 連線沒有被擋；要注意 gunicorn 預設 30 秒逾時。

---

## 1. 資料保存、訓練、零保存、處理地區

### 1-1 Claude API（Anthropic）

| 項目 | 官方說法 | 信心 | 來源 |
|---|---|---|---|
| 會不會拿來訓練 | 商用產品（含 API）預設**不會**用輸入輸出訓練。例外：你主動送回饋（例如按讚／倒讚）或明確同意。 | 高 | [Is my data used for model training?](https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training)（頁面日期 2026-08-18） |
| 預設保存期限 | API 輸入輸出「收到或產生後 **30 天內**」從後端刪除。 | 高 | [How long do you store my organization's data?](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)（最後更新 2026-07-01） |
| 例外 | 被自動信任與安全系統判定違反使用政策：輸入輸出最長保留 **2 年**、分類分數最長 **7 年**；送回饋的資料保留 **5 年**；法律要求。 | 高 | 同上 |
| 文件之間的落差 | 開發者文件寫「對話內容預設不保存，Covered Models 除外」，跟隱私中心的「30 天內刪除」說法不同。**估風險時以 30 天為上限**。 | 中 | [API and data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention) |
| 零保存（ZDR） | 可以，但要**聯絡 Anthropic 業務**開通，以「組織」為單位，每個新組織要分別開。官方沒寫申請門檻。 | 高 | [API and data retention › ZDR](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention) |
| ZDR 涵蓋哪些功能 | Messages API、token 計數、prompt caching、citations、`inference_geo` 都在範圍內。**Batch API 不在**（保留 29 天）、code execution 不在（最長 30 天）。 | 高 | 同上「Feature eligibility」表 |
| 哪些模型不能 ZDR | Claude Fable 5／5.1、Mythos 5／5.1 規定要 30 天保存，除非 Anthropic 特別核准。**Haiku／Sonnet／Opus 5.5 不受這條限制。** | 高 | 同上「Model-specific data retention requirements」 |
| 處理地區（推論） | `inference_geo` 只有兩個值：`"global"`（預設，可能在任何地區）、`"us"`（只在美國）。選 `"us"` 價格乘 **1.1**。**沒有亞洲或臺灣選項。** | 高 | [Data residency](https://platform.claude.com/docs/en/manage-claude/data-residency) |
| 儲存地區 | Workspace geo 目前只有 `"us"`，建立 workspace 後不能改。 | 高 | 同上 |
| 臺灣能不能用 | 支援國家清單有「Taiwan」。 | 高 | [Supported countries](https://www.anthropic.com/supported-countries)（頁面標示生效日 Nov 12, 2026） |
| 預算上限機制 | 每個用量等級有每月上限（Start US$500、Build US$1,000、Scale US$200,000），也可以在 Console 自己設**更低的每月上限**；碰到上限 API 會直接拒絕到下個月。 | 高 | [Rate limits › Spend limits](https://platform.claude.com/docs/en/api/rate-limits) |

### 1-2 OpenAI API（對照）

| 項目 | 官方說法 | 信心 | 來源 |
|---|---|---|---|
| 訓練 | 預設**不會**，要自己選擇加入才會。 | 高 | [Your data](https://developers.openai.com/api/docs/guides/your-data) |
| 預設保存 | 濫用監控紀錄最長 **30 天**（`/v1/responses`、`/v1/chat/completions`、`/v1/embeddings` 都是）。`/v1/responses` 另外預設存 30 天應用狀態（可設 `store=false`）；`/v1/embeddings` 沒有應用狀態。 | 高 | 同上 |
| 零保存 | ZDR 和 Modified Abuse Monitoring 都要 OpenAI **事先核准**，經業務申請。 | 高 | 同上 |
| 處理地區 | 有日本、新加坡、南韓、印度等區域，但這些**只存放、不在當地推論**；美國以外的區域要先核准 ZDR／MAM。2026-03-05 之後的模型用區域端點加價 **10%**。沒有臺灣。 | 高 | 同上 |

### 1-3 Google Gemini（對照）

| 項目 | 官方說法 | 信心 | 來源 |
|---|---|---|---|
| 訓練（Gemini Developer API） | **免費額度會**拿來改進產品，且可能有人工審閱；**付費**不會。 | 高 | [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms)（最後更新 2026-04-28） |
| 保存（Developer API） | 濫用監控保留 **55 天**。官方頁沒有提到 ZDR。 | 高 | [Usage policies](https://ai.google.dev/gemini-api/docs/usage-policies)（最後更新 2026-06-09） |
| Vertex AI（Google Cloud 版） | 不經同意不訓練；預設快取最長 24 小時。要達成零保存，得自己關掉 request-response logging、快取等功能，官方沒有寫另外的核准流程。 | 高 | [Vertex AI data governance](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/data-governance)（最後更新 2026-10-22） |
| 處理地區 | Vertex AI 的亞太區清單有 **Taiwan (asia-east1)**，也列了 Gemini 和 embedding 模型；但同頁註明端點不保證資料駐留。要用的話，每個模型要再逐一確認。 | 中 | [Vertex AI locations](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations) |

### 1-4 Embedding 供應商的資料政策

| 供應商 | 重點 | 信心 | 來源 |
|---|---|---|---|
| Voyage AI（MongoDB Atlas） | MongoDB「可以收集」送到 Embedding API 的資料，拿來改進 Voyage 模型。組織設定可以關，但**要有有效付款方式才能關**，「免費使用者不能選擇退出」。官方頁沒寫保存期限。 | 高 | [Model training data](https://www.mongodb.com/docs/voyageai/management/model-training-data/)、[Manage organization settings](https://www.mongodb.com/docs/atlas/tutorial/manage-organization-settings/) |
| OpenAI embeddings | 同 1-2：不訓練、濫用監控 30 天、沒有應用狀態。 | 高 | [Your data](https://developers.openai.com/api/docs/guides/your-data) |
| Gemini embedding | 同 1-3：免費額度會拿來改進產品，要用付費。 | 高 | [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)（最後更新 2026-10-22） |
| 自架模型 | 資料不出自己的主機，但見第 4 節：Render 免費方案跑不動。 | — | — |

**對 HearWell 的意思**：使用者的提問本身可能含健康資訊（例如「我右耳 60 分貝要不要配助聽器」）。不管用哪家，提問都會送到國外（美國）處理；目前網站的 Render（Ohio）和 Neon 本來就在美國，但「把提問交給 AI 供應商」是新增的第三方。這一點留給 #379 拷問決定。

---

## 2. 每題成本

### 2-1 價格（每 MTok，美元，標準價、全球路由）

| 模型 | 輸入 | 快取讀取 | 輸出 | 來源 |
|---|---|---|---|---|
| Claude Haiku 5.5（提示 ≤10 萬 token） | $0.10 | $0.01 | $0.50 | [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| Claude Sonnet 5.5 | $2 | $0.10 | $10 | 同上 |
| Claude Opus 5.5 | $4 | $0.20 | $20 | 同上 |
| OpenAI gpt-6-luna（對照） | $0.10 | $0.01 | $0.50 | [OpenAI pricing](https://developers.openai.com/api/docs/pricing) |
| OpenAI gpt-6.1-sol（對照） | $2.00 | $0.10 | $10.00 | 同上 |
| Gemini gemini-3.1-flash-lite（對照，付費） | $0.25 | $0.025 | $1.50 | [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) |

其他規則（都來自 [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing)、[Data residency](https://platform.claude.com/docs/en/manage-claude/data-residency)）：
- 美國限定推論（`inference_geo: "us"`）所有類別 ×1.1。
- Batch API 五折，但要等，而且**不能 ZDR**，問答不適用。
- Haiku 5.5 提示超過 10 萬 token 會變貴（輸入 $0.50），我們每題只有幾千 token，碰不到。
- prompt caching 最少要 512 token 才會快取，預設存 5 分鐘（[Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)）。
- **思考（thinking）token 算輸出費用**，就算畫面不顯示也照算（[Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)）。Haiku 5.5 在 effort `high` 以下可以關掉思考；Opus 5.5 不能關，只能調低 effort。

### 2-2 假設（每一條都是估計，不是官方數字）

| 項目 | 典型 | 上限 | 說明 |
|---|---|---|---|
| 中文換算 | 1 字 ≈ 1.5 token | 同左 | **假設**。官方只寫「1M token ≈ 2.5M Unicode 字元」，那是混合內容的平均（[Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)）；中文通常比較吃 token，所以取偏高的 1.5 估上限。真正實作時用**免費**的 token 計數 API 量（[Token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting)）。 |
| 系統指示（只能根據段落回答、附來源、以醫師／聽力師為準） | 800 字 → 1,200 token | 同左 | 固定內容，可以快取 |
| 檢索段落 | 3 段 × 300 字 → 1,350 token | 5 段 × 300 字 → 2,250 token，加標題／來源 150 token | 100 篇短文切段後，每段約 300 字 |
| 使用者提問 | 60 字 → 約 100 token | 同左 | |
| **輸入合計** | **約 2,800 token** | **約 4,000 token**（3,700 進位） | |
| 回答 300 字 | 450 token | 450 token | |
| 思考 token | 250 | 1,050 | 假設；Haiku 關思考時是 0 |
| **輸出合計** | **約 700 token** | **約 1,500 token** | |

### 2-3 計算過程

公式：每題費用 ＝ 輸入 token × 輸入單價 ÷ 1,000,000 ＋ 輸出 token × 輸出單價 ÷ 1,000,000

以 Haiku 5.5 上限為例：
- 輸入：4,000 × $0.10 ÷ 1,000,000 ＝ $0.0004
- 輸出：1,500 × $0.50 ÷ 1,000,000 ＝ $0.00075
- 合計 $0.00115；美國限定 ×1.1 ＝ $0.00127

| 模型 | 每題（典型） | 每題（上限） | 每題（上限，美國限定 ×1.1） |
|---|---|---|---|
| Claude Haiku 5.5 | $0.00063 | $0.00115 | $0.00127 |
| Claude Sonnet 5.5 | $0.0126 | $0.0230 | $0.0253 |
| Claude Opus 5.5 | $0.0252 | $0.0460 | $0.0506 |
| gpt-6-luna（對照） | $0.00063 | $0.00115 | $0.00127（OpenAI 區域端點也是 +10%） |
| gpt-6.1-sol（對照） | $0.0126 | $0.0230 | $0.0253 |
| gemini-3.1-flash-lite（對照） | $0.00175 | $0.00325 | — |

注意：各家 tokenizer 不同，同一段中文在 OpenAI、Gemini 算出的 token 數不一樣，對照欄只能看大概。

**prompt caching 能省多少**：系統指示 1,200 token 可以快取。Haiku 每次快取命中省 1,200 × ($0.10 − $0.01) ÷ 1,000,000 ≈ $0.0001，而且 5 分鐘內要有下一題才會命中。流量小時省不了多少，**估預算上限時不扣掉**。

### 2-4 Embedding 費用

| 模型 | 價格（每 MTok） | 建一次索引（100 篇 × 1,500 字 × 1.5 ≈ 22.5 萬 token） | 每題查詢（約 100 token） | 來源 |
|---|---|---|---|---|
| voyage-4 | $0.06（前 2 億 token 免費） | $0.0135（免費額度內） | $0.000006 | [MongoDB Voyage billing](https://www.mongodb.com/docs/voyageai/management/billing/) |
| voyage-4-lite | $0.02（前 2 億 token 免費） | $0.0045 | $0.000002 | 同上 |
| OpenAI text-embedding-3-small | $0.02 | $0.0045 | $0.000002 | [OpenAI pricing](https://developers.openai.com/api/docs/pricing) |
| Gemini gemini-embedding-2（付費） | $0.20 | $0.045 | $0.00002 | [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) |

每月就算 1 萬題，查詢 embedding 最多 $0.2（Gemini），**跟回答費用比可以忽略**。

---

## 3. 繁體中文 embedding 選項

### 3-1 API 型

| 模型 | 語言／中文依據 | 長度、維度 | 來源 |
|---|---|---|---|
| Voyage `voyage-4`／`voyage-4-large`／`voyage-4-lite` | Anthropic 文件寫「multilingual retrieval」；Voyage 4 部落格只公布 29 個 RTEB 資料集的總成績，**沒有中文或多語分項**。 | 32K token；1024 維（可選 256／512／2048） | [Claude embeddings](https://platform.claude.com/docs/en/build-with-claude/embeddings)、[Voyage 4 blog](https://blog.voyageai.com/2026/01/15/voyage-4/) |
| OpenAI `text-embedding-3-small`／`-large` | 官方只給 MTEB 總分（62.3%／64.6%），沒有中文分項。 | 8,192 token；1536／3072 維 | [OpenAI embeddings](https://developers.openai.com/api/docs/guides/embeddings) |
| Gemini `gemini-embedding-2` | 官方寫支援 100 多種語言；`gemini-embedding-001` 有 MTEB 總分（3072 維 68.16），沒有中文分項。 | 8,192 token；預設 3072 維，可選 128–3072 | [Gemini embeddings](https://ai.google.dev/gemini-api/docs/embeddings) |

### 3-2 可自架（開源權重）

| 模型 | 授權 | 語言／中文依據 | 長度、維度 | 來源 |
|---|---|---|---|---|
| BAAI `bge-m3` | MIT | 100 多種語言；論文有多語檢索評測，但模型卡的中文數字只在圖片裡，文字沒寫。 | 8,192 token；1024 維 | [模型卡](https://huggingface.co/BAAI/bge-m3)、[論文 arXiv:2402.03216](https://arxiv.org/abs/2402.03216) |
| Qwen `Qwen3-Embedding-0.6B`（另有 4B、8B） | Apache-2.0 | 100 多種語言；**C-MTEB 平均 66.33**（4B 72.27、8B 73.84），MTEB 多語 64.33。 | 32K token；最多 1024 維 | [模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) |
| Voyage `voyage-4-nano` | Apache-2.0 | 官方沒公布中文分項。 | 32K token；預設 2048 維 | [Claude embeddings](https://platform.claude.com/docs/en/build-with-claude/embeddings) |

### 3-3 中文品質的依據：**找不到繁體中文專用的官方評測**

- 常被引用的中文評測 C-MTEB，資料集（如 T2Retrieval、DuRetrieval）來自中國大陸，是**簡體中文**。用它的分數推論繁體中文和臺灣用語（例如「助聽器驗配」「聽力師」「健保」），**只能當參考**，信心中。
- 這次沒有找到臺灣或繁體中文專用的檢索評測，也沒有任何一家在官方頁面公布繁體中文分數。
- 建議：真的要做時，用 HearWell 自己的 FAQ 出 30–50 題「提問 → 應該找到的段落」，比較 2–3 個模型找回正確段落的比例（例如前 5 段裡有沒有正確段落）。這一題交給 #379 的 eval 討論。

---

## 4. pgvector、Django、Render

### 4-1 Neon

| 項目 | 結果 | 信心 | 來源 |
|---|---|---|---|
| Postgres 18 | Neon 支援 14–18。 | 高 | [Postgres version policy](https://neon.com/docs/postgresql/postgres-version-policy) |
| pgvector 版本 | PG18 是 **0.8.6**（PG14–17 是 0.8.0）。 | 高 | [Supported extensions](https://neon.com/docs/extensions/pg-extensions) |
| 免費方案能不能用 | 能，所有方案都有。 | 高 | [pgvector on Neon](https://neon.com/docs/extensions/pgvector)、[Neon pricing](https://neon.com/pricing) |
| 怎麼開 | `CREATE EXTENSION IF NOT EXISTS vector;`，**每個資料庫各開一次**。 | 高 | [pgvector on Neon](https://neon.com/docs/extensions/pgvector) |
| 索引維度上限 | `vector` 型別建索引最多 **2,000 維**（`halfvec` 4,000）。Gemini 預設 3072 維要調小或改用 `halfvec`。 | 高 | 同上、[pgvector README](https://github.com/pgvector/pgvector) |
| 免費方案容量 | 每專案 1 GB 儲存、每月 100 CU-hours、閒置 5 分鐘自動暫停（不能關）。 | 高 | [Neon pricing](https://neon.com/pricing) |
| 我們需要多少 | 100 篇約切 500 段 × 1024 維 × 4 bytes ≈ **2 MB**（自己算的），加索引也遠低於 1 GB。這個量甚至不建索引、直接全部比對也很快。 | 中 | 推算 |

### 4-2 本機 Docker 與 CI

- 現在 README 的本機指令和 `.github/workflows/ci.yml` 都用 `postgres:18`。pgvector 官方提供另外的映像 `pgvector/pgvector`，標籤格式像 `0.8.7-pg18-trixie`（[pgvector README](https://github.com/pgvector/pgvector)）。
- pgvector 最新是 **0.8.7**，Neon 是 0.8.6。為了跟正式環境一致，可以用 **`pgvector/pgvector:0.8.6-pg18`**（Docker Hub 有這個標籤，2026-08-13 更新，[Docker Hub tags](https://hub.docker.com/v2/repositories/pgvector/pgvector/tags?page_size=100&name=0.8.6-pg18)）。
- 換映像會影響：README 的本機啟動指令、CI 的兩個 `services.postgres.image`。本機已有的 `hearwell-pgdata` volume 能不能直接沿用（同是 PG18），**這次沒有驗證**，實作時要先試，並且這一步要本人來做（不碰本人資料庫）。
- Django 測試會自己建 `test_` 資料庫，migration 裡的 `CREATE EXTENSION` 需要建立擴充的權限；本機和 CI 的預設帳號是超級使用者，應該沒問題（信心中，未實測）。

### 4-3 Django 怎麼接（`pgvector` Python 套件）

- 套件：`pgvector` **0.5.1**（2026-10-09 發布），需要 Python ≥ 3.10（[PyPI](https://pypi.org/project/pgvector/)）。
- 用法（依 context7 查到的 [pgvector-python 文件](https://github.com/pgvector/pgvector-python)）：
  - migration 加 `pgvector.django.VectorExtension()` 開擴充。
  - 欄位用 `VectorField(dimensions=1024)`。
  - 索引用 `HnswIndex(name=..., fields=["embedding"], m=16, ef_construction=64, opclasses=["vector_cosine_ops"])`。
  - 查詢用 `CosineDistance`（`order_by(CosineDistance("embedding", 查詢向量))[:5]`）。
- 套件同時支援 psycopg 2 和 3；我們現在用 `psycopg2-binary`，不用換。

### 4-4 Render

| 項目 | 結果 | 信心 | 來源 |
|---|---|---|---|
| 免費方案規格 | **0.1 CPU、512 MB**。Starter（`0.5c-512mb`）是 0.5 CPU、512 MB；Standard（`1c-2g`）1 CPU、2 GB。 | 高 | [Compute plans](https://render.com/docs/compute-plans)（價格頁這次讀不到數字，**未查到官方月費**） |
| 閒置休眠 | 免費服務 15 分鐘沒流量就休眠，喚醒約 1 分鐘；每月 750 小時。 | 高 | [Deploy for Free](https://render.com/docs/free) |
| 對外連線 | 免費服務只擋 25、465、587 埠（寄信用）。呼叫 AI API 走 HTTPS 443，**不受影響**。 | 高 | 同上 |
| 請求逾時 | Render 本身允許 HTTP 請求最長 **100 分鐘**（只在 Render 官方文章找到，docs 參考頁沒找到）。 | 中 | [Render 文章（2026-01-13）](https://render.com/articles/real-time-ai-chat-websockets-infrastructure) |
| gunicorn 逾時 | gunicorn 預設 `timeout` **30 秒**、`worker_class` 預設 `sync`、`workers` 預設 1（或讀 `WEB_CONCURRENCY`）。sync worker 一次只能處理一個請求，等 AI 回答時其他人會被卡住。 | 高 | context7 查 gunicorn 26.2.0 [settings](https://github.com/benoitc/gunicorn/blob/26.2.0/docs/content/reference/settings.md) |
| 自架 embedding | Qwen3-Embedding-0.6B 有 6 億參數，以 16 位元載入約需 1.2 GB（自己算的），**超過 512 MB**。bge-m3 模型卡沒寫大小。結論：免費方案只能用 API 型 embedding；要自架至少要換 2 GB 以上方案。 | 中 | 推算 |

---

## 5. 每月預算上限估算表

假設同第 2 節（上限情境：每題輸入 4,000、輸出 1,500 token）。單位美元。**embedding 和基礎設施費用已計入「增加的固定費用」欄。**

### 5-1 AI 回答費用（上限情境）

| 每月題數 | Haiku 5.5 | Haiku 5.5 美國限定 | Sonnet 5.5 | Sonnet 5.5 美國限定 | Opus 5.5 | Opus 5.5 美國限定 |
|---|---|---|---|---|---|---|
| 100 | $0.12 | $0.13 | $2.30 | $2.53 | $4.60 | $5.06 |
| 1,000 | $1.15 | $1.27 | $23.00 | $25.30 | $46.00 | $50.60 |
| 10,000 | $11.50 | $12.65 | $230.00 | $253.00 | $460.00 | $506.00 |

典型情境（輸入 2,800、輸出 700）大約是上表的 55%：例如 Haiku 每月 1 萬題約 $6.3。

### 5-2 其他費用

| 項目 | 增加的費用 | 說明 |
|---|---|---|
| embedding（API） | 每月 < $0.2；建索引一次 < $0.05 | 見 2-4。Voyage 有 2 億 token 免費額度，但**要綁付款方式才能關掉資料收集** |
| Neon | $0 | 2 MB 等級，在免費 1 GB 內 |
| Render | $0（維持免費、用 API embedding） | 若改自架 embedding，至少要 2 GB 方案，月費未查到 |

### 5-3 怎麼設上限

- Claude Console 可以設「每月上限」，低於等級上限即可；碰到就停到下個月（[Rate limits › Setting your own spend limit](https://platform.claude.com/docs/en/api/rate-limits)）。
- 舉例：預計每月 1,000 題、用 Haiku，上限情境 $1.27，抓 2–4 倍緩衝，設 **US$5** 就夠；被人狂刷時最多也只損失這個數字。
- 注意：新帳號的 Start 等級本身上限是 US$500；Opus 5.5 美國限定每月 1 萬題（$506）會超過，要先升級等級。
- 防止被刷的做法（每人每天幾題、要登入才能問）屬於設計決定，交給 #379。

---

## 6. 留給 #379 拷問的問題

1. 要不要付費開 ZDR？如果申請不到，能不能接受「30 天內刪除、違規最長 2 年」？
2. 推論地區選 `global`（便宜 10%）還是 `us`（跟 Render／Neon 同在美國）？兩者都不在臺灣。
3. embedding 選 Voyage（要綁卡關掉資料收集）、OpenAI，還是等有預算再自架？
4. 用 Haiku 5.5 夠不夠？答案品質要靠自己的題庫測，這次沒有測。
5. 每月預算上限設多少、被刷時要怎麼處理。

## 沒查到或沒驗證的事

- Render 各方案的官方月費（價格頁內容讀不到）。
- 繁體中文專用的 embedding 評測。
- 各家 tokenizer 對繁體中文的實際 token 數（要用免費的 token 計數 API 實測）。
- 本機現有 volume 換成 pgvector 映像後能不能直接用。
- Voyage／MongoDB 的資料保存期限。
- 個資法對「提問送到國外 AI 供應商」的要求（不在這張票範圍，建議 #379 一起討論）。
