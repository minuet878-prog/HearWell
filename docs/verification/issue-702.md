# #702 從 iPhone 匯入 Apple 聽力測試、聽力圖記來源

日期：2026-11-17。分支：`feat/702-apple-import`（基準：合併了 2026-11-17 的 `origin/main`，含 #693、#656、#677）。規格：#702；子票 #703–#710。決策：[拷問決定](../planning/apple-hearing-test/grill-decisions.md)、[ADR 0068](../adr/0068-self-tests-are-audiograms-not-for-disability.md)。設計圖選定：[issue-703.md](issue-703.md)。

狀態：自動測試全過；本人用 iPhone 實機驗收通過（2026-11-17，#710）。

## 審查

- 每張票都做了自審（規範、規格兩軸，各由另一個子代理只看 diff 與規格），發現都已修正並補測試。
- **交叉審查略過**：本人決定（2026-11-17，Codex 額度用完）。這個分支照規則屬於必做交叉審查：#704 的 migration 0041 把既有聽力圖補成「聽力檢查、自己標」（會動資料），#706 改了身障鑑定估算。風險是實作與審查都是同類代理，盲點可能相同；Codex 額度恢復後可在合併前或合併後補審。
- 已知風險：pdfminer.six 沒有解壓大小上限，刻意做成「解壓後很大」的 2 MB PDF 仍可能吃滿記憶體或 CPU。

## 本人在實作中的決定

| 日期 | 決定 |
|---|---|
| 2026-11-17 | 設計圖 #703 七題：1C、2A、3A、4A、5A、6A、7A（見 issue-703.md） |
| 2026-11-17 | 「我的聽力」趨勢圖只畫問卷，規格驗收 20 與故事 24 不做，改成比較頁標「自我測試」（#702、#705 留言） |
| 2026-11-17 | 選配指引路線站、語言香蕉區標題不標「自我測試」，照驗收清單 |
| 2026-11-17 | 首頁照顧旅程「記錄聽力圖」卡片三顆按鈕：有，記錄聽力圖／從 iPhone 匯入／還沒，看要去哪裡檢查 |
| 2026-11-17 | 預覽過期、被改、別人的預覽：「沒有存到，請重新選一次 PDF。」（擬稿 B） |
| 2026-11-17 | 示意圖畫法 A（網站藍色線條），六張逐張審過 |
| 2026-11-17 | 鑑定估算的日期句照網站日期規範寫「依您 2024/05/03 的聽力檢查估算。」（原句寫 YYYY 年 M 月 D 日） |

## 跟規格或設計圖不一樣的地方

- 預覽頁的數值表改成每列一個頻率（設計圖是橫的 9 欄），手機 200% 字級才放得下。
- 匯入頁多一顆「讀取這份 PDF」：不用 JavaScript 的表單要有送出鈕。
- 健康報告的重點摘要那一行與摺疊列也標「自我測試」（設計圖只畫標題旁），紙本給醫師看時摘要最先看到。
- 路線「身障鑑定」站的「估算未達門檻」也只看聽力檢查（規格沒寫，照 ADR 0068）。
- 結果頁的「建議下一步」沒有加「從 iPhone 匯入」，只有首頁卡片有。
- Migration 編號因 main 先用了 0039、0040，改成 0041（聽力圖來源）、0042（匯入失敗月計數）。

## 驗收對照

| # | 驗收條件（摘要） | 證明 |
|---|---|---|
| 1 | 讀得出來 → 預覽頁（存進誰、核對句、測試日期、16 個值），還沒存 | `screening/tests/test_audiogram_import.py:101`；e2e `AppleHearingTestImportTest`（`e2e/main_flow.py:17323`） |
| 2 | 存下來 → 自我測試、Apple PDF 匯入、原值、轉詳細頁 | `test_audiogram_import.py:122`；e2e 同上 |
| 3 | 低於 -10 照存、圖畫得出 | `test_audiogram_import.py:122`、`test_apple_hearing_test.py:28`、`test_audiogram.py:224`、`frontend/src/AudiogramChart.test.jsx:98`、`test_audiogram_thumbnail.py:42` |
| 4 | 存測試日期，不是輸出日期 | `test_apple_hearing_test.py:21`、`:39`；`test_audiogram_import.py:101` |
| 5 | 三句提醒只在 PDF 有寫時出現，不存 | `test_audiogram_import.py:381`、`test_apple_hearing_test.py:78` |
| 6 | 重複匯入擋下、連到那張；舊預覽再存也不多一張 | `test_audiogram_import.py:336`、`:354` |
| 7 | 各種讀不出來：訊息、自己標、當月該原因加一、不存 | `test_audiogram_import.py:312`、`test_apple_hearing_test.py:54`、`:64` |
| 8 | PDF 不留、資料庫沒有姓名生日 | `test_audiogram_import.py:162` |
| 9 | 預覽過期、被改、別人的：不存、請重選 | `test_audiogram_import.py:364` |
| 10 | 沒登入被帶去登入 | `test_audiogram_import.py:148` |
| 11 | 自己標要選哪一種，選了自我測試就存成自我測試 | `test_audiogram.py:197`、`:207`；`frontend/src/AudiogramApp.test.jsx:554`、`:566` |
| 12 | 修改能改來源，點不變 | `test_audiogram.py:923`；`AudiogramApp.test.jsx:590` |
| 13 | 匯入的沒有修改；修改頁與 API 拒絕、資料不變 | `test_audiogram_import.py:173` |
| 14 | 既有聽力圖補成聽力檢查、自己標 | `test_audiogram.py:1763`（migration 0040 → 0041） |
| 15 | 只有自我測試：不估算、請去檢查 | `test_guide_self_test.py:43` |
| 16 | 新自我測試＋舊聽力檢查：用舊的、寫日期 | `test_guide_self_test.py:55`；缺頻率時不說日期句 `:99` |
| 17 | 最新是聽力檢查：照舊 | `test_guide_self_test.py:71` |
| 18 | 只有自我測試：旅程第 2 步、路線第 1 站完成，照 #693 判斷 | `test_guide_self_test.py:89`；路線標記 `:80` |
| 19 | 清單、詳細頁、比較頁、報告、分享報告標「自我測試」 | `test_audiogram.py:422`、`:524`、`:1215`；`test_report.py:187`、`:210` |
| 20 | 趨勢圖（更正後不做，改比較頁） | `test_audiogram.py:1215` |
| 21 | 下載資料有來源、輸入方式 | `test_export.py:142`、`:171` |
| 22 | API 有 source、entry | `test_audiogram.py:207`、`:218` |
| 23 | 隱私權說明新句、同意書不升版 | `test_audiogram_import.py:207`、`test_consent.py`（兩處新句）；`test_family_zone.py` 審過頁面指紋只多那一行 |
| 24 | admin 看得到每月失敗次數、只能看 | `test_audiogram_import.py:404`、`:413` |

其他：入口按鈕 `test_audiogram_import.py:250`–`:265`；匯入頁步驟與示意圖 `:52`、`:76`。

## 測試結果（最後一輪，commit `d5bd6dba`）

- 後端：`python manage.py test --settings=config.test_settings --parallel 4`，3104 個，OK。
- 前端：`npm test --prefix frontend`，760 個，OK。
- e2e：`python manage.py test --settings=config.test_settings e2e.main_flow --parallel 4`，504 個，OK。
- Ruff：`ruff check .`、`ruff format --check .` 都通過。
- 本人的真實 PDF（不在 repo）用讀取函式讀過：日期 2026-11-17，16 個數值與紙本一致，有星號、鼻塞否、噪音暴露否。

## 本人實機驗收（#710，2026-11-17 通過）

在本機用這個分支開伺服器（`runserver 0.0.0.0:8001`，本機資料庫暫時跑到 migration 0042，驗收後退回 0040），本人用自己的 iPhone 與 AirPods 測的結果走過：

- [x] 從「健康」輸出 PDF、存到「檔案」，在聽伴選檔上傳
- [x] 預覽頁的數值、日期跟 PDF 一致，按「存下來」
- [x] 詳細頁、清單看得到「自我測試」
- [ ] 選配指引的鑑定估算：實機上沒有打開選配指引（伺服器紀錄沒有 `/guide`）；由 `test_guide_self_test.py` 的自動測試證明
- [x] 再上傳同一份，看到「這份已經匯入過了。」

## 上線時要做

- `PRIVACY_UPDATED_ON` 目前是 2026-11-17；合併上線那天若不同，改成當天。
