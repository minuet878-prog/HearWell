# 每筆紀錄帶一個結果物件，呼叫端不再依結果類型分支（#385）

日期：2026-10-26。基準：`01682b2`（origin/main，#380 拆檔合併後），途中合併 `360c678`（#403）；分支：`refactor/385-result-object`。規格：[#385](https://github.com/minuet878-prog/HearWell/issues/385)；票：#386–#391。來源：2026-10-26 架構審查候選 1。

狀態：2026-10-26 本人回覆「人工驗收六項都通過」。自動測試全過；自審修完；交叉審查（Codex）要修 0 項，摘要已留言到 #385。沒有 migration，沒有操作真實資料。碰到分級呈現、計分查詢與 API，依 AGENTS.md 已做交叉審查。

## 本人決定（2026-10-26，架構審查後逐題確認）

1. 範圍只管「結果怎麼呈現」；推薦精靈、API 不給 IOI-HA 作答、選配路線這些依問卷角色的判斷不動。
2. 沒有分項的分級問卷（THI），API 的 `emotional`、`social` 改成 null，跟匯出一致。這是唯一的行為改變。
3. 每筆紀錄帶一個結果物件（`submission.result`），四種結果類型各一個 class。
4. model 上只對某種類型有用的屬性全部搬進結果物件，舊的拿掉。
5. 結果頁的模板與類型資料由結果物件給，建議下一步、配戴文字、比較連結留在頁面。
6. 分級呈現（候選 4）與聽力報告（候選 5）不在這次。
7. 新增結果物件的測試，既有測試全留當安全網。
8. THI 修正當第一張票，之後的票只搬程式。
9. GLOSSARY 加「結果類型」與「分項」；寫 ADR 0036。
10. 「有沒有分項」在計算總分的同一個 aggregate 多算一個數量。

## 做了什麼

- `screening/questionnaires/results.py`：`GradedResult`（分級）、`AverageResult`（平均）、`NormResult`（常模比對）、`SubscaleResult`（分量表）。問卷定義的 `result` 直接放 class；`Submission.result` 回傳綁定這筆紀錄的結果物件。
- 計分 aggregate 多一個 `subscore_answer_count`（題目性質是情緒或社交的答案數）；分項有沒有由它決定。原本三個 `Sum` 不變。
- 首頁上次結果、我的紀錄每一列、結果頁、聽力報告、家人分享頁、匯出、API 都改問結果物件；模板裡依類型的 if/elif 鏈、程式裡 `result == LEVEL` 這類字串比較都拿掉。
- 拿掉 Submission 的 `classified`、`ssq_average`、`ssq_unavailable_reason`、`ssq_lowest_answers`、`satisfaction`、`emotional_score`、`social_score`，以及 `definition.py` 的四個字串常數與 `averaged`。`total_answer_score` 留著（計分與比較差值用）。
- `score_bar`、`ioi_ha_summary`、`ioi_ha_items` 搬進結果類型旁，questionnaires 不再依賴 views。合併 #403 時沿用它的公開名稱；#403 移到結果頁的 `has_subscores(answers)` 不保留（#386 已改成 aggregate 規則）。
- `GLOSSARY.md` 新增「結果類型」「分項」；`docs/adr/0036-result-types-answered-by-the-result-object.md`。

Commits：`7cefb2d`、`0a10958`（#386）→ `4ad1732`、`053df5e`、`3f79cbb`（#387）→ `30cb8bb`（#388）→ `c106fdc`（#390）→ `59dbf85`（#389）→ `90d981a`（#391）→ `00d4666`（合併 main）→ 自審修正 6 個 commit 至 `026ca86` → `694b280`（格式）→ `62536ec`（查詢數回歸）。

## 驗收對照（#385 的 16 條）

| # | 驗收 | 證據 |
|---|---|---|
| 1 | THI 的 API 分項是 null，測試先失敗 | `test_thi.py:277`。先失敗：`7cefb2d` 只加測試、`0a10958` 才修；修正前執行的失敗訊息為 `AssertionError: {'total': 100, 'emotional': 0, 'social': 0} != {'total': 100, 'emotional': None, 'social': None}`（清單、詳情兩個 subTest） |
| 2 | HHIE-S 全部答 0 照舊是 0 | `test_api.py:211`、`test_result_types.py:133–134` |
| 3 | 四種類型各自回答，沒有的是 None | `test_result_types.py` 四個類別（:84–95、:172–187、:233–245、:288–310），共用 `assert_none`（:62） |
| 4 | THI 有總分與分級、分項 None | `test_result_types.py:139–142` |
| 5 | SSQ12 不適用時平均 None、原因照 ADR 0001 | `test_result_types.py:212–222` |
| 6 | 定義放 class、沒有字串分支、模板沒有 if 鏈 | `test_result_types.py:371`、:399–400、:409（掃描非測試程式）、:658–661、:1020；另以 grep 確認全專案無殘留 |
| 7 | 七個舊屬性不在了 | `test_result_types.py:396` |
| 8 | 結果頁用結果物件的模板、畫面不變 | `test_result_types.py:780–782`；畫面不變見下方「與 main 的輸出比對」 |
| 9 | 列表頁查詢數沒有增加 | `test_thi.py:505`、`test_result_types.py:677`、:696、:1010；實測見下方比對 |
| 10 | OpenAPI schema 只差 nullable | `test_api.py:95–98` 比對簽入檔；`docs/api/schema.yaml` 的 diff 只有 `emotional`、`social` 各多一行 `nullable: true` |
| 11 | 全部單元測試過、既有斷言沒改 | 1489 項全過（`62536ec`）；既有測試只改屬性名稱與 import |
| 12 | 先建置前端再跑全部 e2e | 建置成功；`e2e.main_flow --parallel 4` 276 項全過（`62536ec`） |
| 13 | 沒有 migration | `makemigrations --check --dry-run`：No changes detected |
| 14 | GLOSSARY 兩個詞條、互相標明 | 文件審查：「結果類型」寫明分量表不要跟分項混用，「分項」寫明不要跟分量表混用。請本人在人工驗收時確認用語 |
| 15 | ADR 0036 延伸 ADR 0005 | 文件審查：`docs/adr/0036-…md` 第 3、7 行連到 0005。請本人確認內容 |
| 16 | `ruff check .` | 通過；`ruff format --check .` 也通過（CI 會跑） |

## 與 main 的輸出比對（一次性試驗，測試檔已刪除）

同一份測試資料（6 個帳號、四種類型＋THI、存一組配戴比較與一個分享連結）在 main（`360c678`）與這個分支各跑一次，擷取 60 個輸出：首頁 6、我的紀錄 7、結果頁 15、聽力報告／分享設定／家人封面／家人報告 4、配戴比較頁 3、下載我的資料 1、API 23、查詢數 1。

- 把 HTML 連續空白壓成一個後，**所有頁面完全相同**。匯出、聽力報告、家人報告、配戴比較頁、`/api/questionnaires/` 連原始內容都相同。
- 唯一的差異：THI 紀錄在 API 的 `scores.emotional`、`scores.social` 從 0 變 null（預期）。
- 查詢數：第一次比對發現我的紀錄 HHIE-S 分頁（有存配戴比較）從 12 變 14。原因是比較模板改讀 `result.total`，而讀比較時沒有一起載入問卷。改成連問卷一起載入（`62536ec`，先寫失敗測試 14≠12 再修）後重跑比對：**每一頁的查詢數都和 main 相同**。

## 測試與審查

- 單元測試 `manage.py test --settings=config.test_settings --parallel 4`：1489 項全過。
- 端對端：`npm run build --prefix frontend` 後 `e2e.main_flow --parallel 4`：276 項全過。
- `ruff check .`、`ruff format --check .`、`makemigrations --check --dry-run`：通過。
- 自審（Standards／Spec）：要修的都修了：GLOSSARY 反向標明、結果頁不再傳重複的原始分數、配戴文字改由結果類型宣告（`page_shows_wearing`）、顯示用總分一律從結果物件拿（模板裡已沒有 `total_answer_score`）、比對寫法統一用 `is`、兩處過時註解。不採納：片段的 `place` 參數與檔名、`optional_ssq12` 依問卷代碼判斷（角色判斷不在範圍）、「不適用」字串（作答選項標籤和匯出用字意思不同）。
- 交叉審查（Codex，HEAD `62536ec`）：Standards 要修 0 項；Spec 程式缺陷 0 項。另列 6 項「驗收證據缺口」（第 1、11、12、14、15、16 條），原因是審查時不准執行測試；執行證據已補在上表。

## 人工驗收

這次畫面應該完全不變，請用預覽網站走一輪，用有各種紀錄的帳號：

1. 首頁：上次結果（生活影響問卷有半圓儀表與分級；SSQ12、SADL、IOI-HA 顯示平均／滿意度／常模摘要）。
2. 我的紀錄：每個問卷分頁的每一列，以及「和上一次比」。
3. 結果頁：HHIE-S 或 HHIA-S（有情緒／社交分項）、THI（沒有分項）、SSQ12、IOI-HA、SADL 各打開一筆。
4. 聽力報告與家人分享頁。
5. 帳號設定 → 下載我的資料：檔案打得開，THI 的分項是 null。
6. GLOSSARY「結果類型」「分項」與 ADR 0036 的用語，看是否同意。

回覆：2026-10-26 本人確認六項都通過（含 GLOSSARY 用語與 ADR 0036）。

## 後續（不在這次範圍，原本就有）

- 首頁上次結果是 SADL 時要 25 次查詢（SADL 滿意度逐題讀題目）。
- `comparison.py` 組顯示字串時仍讀 `total_answer_score`。
- 摘要片段的 `place` 參數與 `ssq_average.html`／`graded_summary.html` 檔名跟內容對不上。
