# 讀取動畫：換頁條、載入中跑條、送出中轉圈（小改動，無 issue）

日期：2026-10-24。基準：`d52245e`（main）；分支：`feat/loading-indicators`。決策見 [ADR 0027](../adr/0027-loading-indicators.md)。

狀態：自動測試全過，**等本人實際操作確認**。只改畫面和送出按鈕的回饋；沒碰計分、分級、門檻、migration、權限，所以不需要交叉審查。沒有操作真實資料。

## 怎麼選的

本人看了讀取動畫比較頁（Artifact，沒進版控）：換頁 A1–A4、頁面裡的載入中 B1–B3、送出按鈕 C1–C3，選 **A3、B1、C1**。「更多互動式頁面」另開需求。ADR 0006 不准循環的規定，本人選「等待中可以循環，最多約 10 秒」。

## 行為

- **A3 換頁**：點站內連結或送出表單後，等 0.3 秒還沒換頁，畫面最上面出現一條 6 像素的淺藍條，藍色小段來回跑，右上角白底藍字「載入中…」。條是固定在畫面頂端，捲到頁面下方點連結也看得到。下載、外部網站、新分頁、同一頁的段落、電話連結、按著 Ctrl 點、中鍵點，都不會出現。
- **B1 載入文字**：「題目載入中…」「趨勢圖載入中…」下面多一條同樣的跑條，0.3 秒後出現。
- **C1 送出按鈕**：主要內容裡會存東西的表單（POST），按下的按鈕變成轉圈＋「送出中…」，不能再按，也不會送第二次；10 秒沒反應或按上一頁回來時恢復原樣。搜尋類表單（查詢、比較、下一步）和頁首「登出」只有頂端條，按鈕不變。React 作答頁的「送出中…」、聽力圖的「存檔中…」也加上轉圈。轉圈 0.3 秒後出現。
- 讀螢幕軟體：送出時念「送出中…」，換頁時念「載入中…」；轉圈和跑條不念。
- 動畫最多約 10 秒就停（條 8 輪 × 1.3 秒、轉圈 12 輪 × 0.8 秒）。
- 開了「減少動態效果」：條不跑、整條填滿藍色，轉圈拿掉，只看字。
- 原本只有作答頁有的 `submit-button.js` 拿掉，改由全站的 `page-loading.js` 處理，作答頁原本的行為（送出中…、不能按、10 秒恢復、上一頁恢復）照舊。
- 配合的小改動：登入、註冊、作答頁的送出按鈕從 `<input>` 改成 `<button>`（`<input>` 裡放不進轉圈）；「下載我的資料」連結加上 `download`，讓頂端條不會因為下載卡住。隱私權頁那個連結只在登入後才加，因為沒登入時它會帶人去登入頁。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。

| 需求 | 驗證 | 證據 |
|---|---|---|
| 換頁時 0.3 秒後出現條和「載入中…」 | ✅ 自動 | `frontend/src/page-loading.test.js:47`；真的瀏覽器裡條會跑、8 輪：`e2e/main_flow.py:2752` |
| 每一頁都有條、狀態區和程式 | ✅ 自動 | `screening/tests/test_pages.py:1222`；每頁載入的程式清單 `test_pages.py` 的 `test_only_expected_scripts` |
| 下載、外站、新分頁、同頁段落、電話、Ctrl、中鍵不出現；頁面自己處理的點擊不出現 | ✅ 自動 | `frontend/src/page-loading.test.js:75`、`:91`；帶段落的別頁連結仍會出現 `:99` |
| 下載連結有 `download`；沒登入時隱私權頁的連結沒有 | ✅ 自動 | `screening/tests/test_pages.py:1234` |
| 上一頁回來條會消失；10 秒還沒換頁就收起來 | ✅ 自動 | `frontend/src/page-loading.test.js:58`、`:67` |
| B1：題目載入中、趨勢圖載入中有跑條 | ✅ 自動 | `screening/tests/test_answering.py:523`、`screening/tests/test_history.py:627`、`frontend/src/TrendChart.test.jsx:110` |
| C1：按下的按鈕變轉圈＋送出中…，讀螢幕念「送出中…」 | ✅ 自動 | `frontend/src/page-loading.test.js:120`；真的瀏覽器：`e2e/main_flow.py:2752` |
| 不能送第二次 | ✅ 自動 | `frontend/src/page-loading.test.js:141` |
| 按鈕的 name／value（同意書的「我同意」）不會因為停用而遺失 | ✅ 自動 | `frontend/src/page-loading.test.js:133`（晚一拍才停用）；真的瀏覽器裡按「我同意，開始篩檢」後照常進到篩檢：`e2e/main_flow.py:242`、`:613` |
| 10 秒恢復、上一頁回來恢復 | ✅ 自動 | `frontend/src/page-loading.test.js:147`、`:159` |
| 搜尋類表單、頁首登出不改按鈕，只有條 | ✅ 自動 | `frontend/src/page-loading.test.js:106`、`:182` |
| 作答頁網頁版表單仍有送出中…（取代舊的 submit-button.js） | ✅ 自動 | `screening/tests/test_answering.py:682`（POST、在 main 裡、是 `<button>`）＋上面 C1 各項 |
| React 作答頁送出中…、聽力圖存檔中…有轉圈、不能再按 | ✅ 自動 | `frontend/src/AnswerApp.test.jsx:428`、`frontend/src/AudiogramApp.test.jsx:477` |
| 送出按鈕都是 `<button>`（轉圈放得進去） | ✅ 自動 | `screening/tests/test_pages.py:1249` |
| 減少動態效果：條不跑、轉圈拿掉 | ✅ 自動 | `e2e/main_flow.py:2763` |
| B1 跑條、轉圈的 0.3 秒延遲和 10 秒上限 | ⚠️ 只寫在 CSS | `frontend/src/site.css` 的 `.loading-message::after`、`.spinner`；轉圈的動畫名稱在 e2e 驗過，延遲秒數沒驗 |
| 實際看起來順不順、會不會太快或太晃、手機上「載入中…」蓋住登出按鈕可不可以接受 | ⚠️ 要人工 | 請本人實際操作 |

## 測試與審查

- 單元測試 `manage.py test --settings=config.test_settings`：1352 項全過。
- 端對端（先 `npm run build --prefix frontend`）`e2e.main_flow --parallel 4`：176 項全過（新增 2 項）。
- 前端 `npm test --prefix frontend`：237 項全過（`submit-button.test.js` 拿掉，改成 `page-loading.test.js` 21 項）。
- `ruff check .`：全過。
- 改了的既有測試（刻意改變，不是行為壞掉）：每頁載入的程式清單多一支 `page-loading.js`、作答頁少了 `submit-button.js`；登入按鈕從 `<input>` 改成 `<button>`；聽力圖連按測試改找「存檔中…」按鈕。
- 自審（`/mattpocock-skills:code-review`，基準 `main`，規格＝ADR 0027 和本檔「行為」段）：
  - **Standards**：沒有硬違規。採納：`page-loading.js` 的註解說「伺服器會擋第二次送出」只對作答頁成立，改正；CSS 註明 0.3 秒、10 秒跟 `page-loading.js` 的常數綁在一起。不採納：兩個 React 頁的「轉圈＋字」只有兩處，不抽元件；`.page-loading-note` 的隱藏規則看狀態切換，沒辦法直接套 `.visually-hidden`；`page-loading-main.js` 跟 `pwa-nav-main.js` 同樣寫法。
  - **Spec**：抓到一個真問題，已修：隱私權頁的「這裡下載」沒登入也看得到，加了 `download` 後沒登入的人按下去會存到一份登入頁 HTML，改成只有登入後才加。補上 B1 的測試、真的瀏覽器裡的條和轉圈、減少動態效果的 e2e。另提到「禁止 `<input type="submit">`」是新的全站規則，見下方待確認。

## 待本人確認

- 「送出按鈕一律用 `<button>`」這條目前只寫成測試，要不要也寫進 `CODING_STANDARDS.md`。

## 人工驗收

預覽：Claude Desktop 預覽（8001，主資料夾的這個分支）。本機換頁很快，條通常只閃一下或不出現；要看清楚可以在 Chrome 開發者工具 Network 選「Slow 3G」。

1. 在首頁點「了解」、「篩檢」等連結：最上面有藍條在跑，右上角「載入中…」，下一頁出來就消失。
2. 登入、註冊、同意書、作答網頁版送出：按下的按鈕變成轉圈＋「送出中…」，連按也只送一次。
3. 帳號設定按「下載我的資料」：檔案下載下來，上面不會出現一直跑的條。
4. 我的紀錄的趨勢圖、作答頁剛打開時：「載入中…」下面有一條在跑。
5. 送出後按上一頁回來：按鈕是一般的樣子，可以再按。
6. （可選）手機開「減少動態效果」：條不跑、整條藍色，按鈕只有「送出中…」沒有轉圈。
