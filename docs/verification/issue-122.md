# #122：Tailwind 遷移用的截圖比對工具

日期：2026-10-21。規格：[#122](https://github.com/minuet878-prog/HearWell/issues/122)（母規格 #119）。基準：`b3471bd`（main）；分支：`test/screenshot-compare`；commit：`6c8cb25`、`ed9416a`。

狀態：2026-10-21 本人回覆「ok」，驗收通過。實測與自審（Standards／Spec）已通過。只新增工具，不改網站；沒碰計分、門檻、資料 migration、權限，不需交叉審查。未操作真實資料、沒有啟動開發伺服器；截圖都在 e2e 的臨時網站與測試資料庫上拍。

## 用法

```bash
npm run build --prefix frontend
SHOTS_DIR=e2e-artifacts/shots/main py313/bin/python manage.py test --settings=config.test_settings e2e.screenshots
SHOTS_DIR=e2e-artifacts/shots/branch SHOTS_GROUPS=answering py313/bin/python manage.py test --settings=config.test_settings e2e.screenshots
py313/bin/python e2e/compare_shots.py e2e-artifacts/shots/main e2e-artifacts/shots/branch --group answering
```

- 群組：`public`（公開頁與帳號頁，#127）、`answering`（問卷目錄、作答、結果、配戴比較，#128）、`history`（我的紀錄、聽力圖，#129）、`report`（報告與分享，#130）、`chrome`（每頁的頁首、導覽、頁尾，加上 App 版頁首，#124）。
- 比對結果寫在 `<新資料夾>-diff/report.md`，每張有差異的截圖附差異圖（紅色是變了的像素）；有任何差異時結束碼是 1。
- 全站拍一次約 3 分鐘（364 張）。

## 拍照範圍（364 張怎麼算）

- 整頁截圖 46 種 × 2 種寬度（390、1024）＝ 92 張：
  - public 13：首頁、隱私、家屬指南、加到主畫面（各拍未登入和登入）、登入、註冊、同意書（尚未同意的帳號）、帳號設定、刪除帳號。
  - answering 19：問卷目錄、HHIE-S 配戴比較、四份問卷作答頁（有 JavaScript 與沒有各一）、HHIE-S 與 HHIA-S 三種分級、無法判讀、SSQ12、IOI-HA 結果頁。
  - history 10：我的紀錄四份問卷分頁、聽力圖清單、新增、檢視、編輯、比較、刪除。
  - report 4：聽力報告（螢幕、列印）、分享封面、分享報告（未登入）。
- chrome：45 種螢幕版頁面 × 2 寬度 × 頁首／導覽／頁尾 ＝ 270 張，加上 App 版頁首 2 張。
- 「需要登入的頁面另拍未登入的樣子」的解讀：需要登入的頁面未登入時只會被導到登入頁，所以只對**登入前後都看得到**的頁面（首頁、隱私、家屬指南、加到主畫面）各拍兩種。本人已確認這個解讀。

## 讓兩次截圖一樣的做法

- 網站時間固定在 2026-10-01 10:00（`django.utils.timezone.now`），瀏覽器時間也固定；作答日期改成固定的相對天數。
- 臨時網站固定用埠號 8765：家屬指南、報告會印出網址，隨機埠號會讓每次不同。
- 擋掉 Google Fonts，用系統字型：Noto Sans TC 分片下載的時機會讓英文字形位置每次不同。代價是截圖看不出字型本身；改成每次另外記錄每頁要求的字型與基礎字級（`styles.json`），比對時一併比較。
- 圖表頁等動畫跑完（1.6 秒）才拍；瀏覽器用固定的字型繪製設定。
- 假問卷（無法判讀）只在拍它自己的結果頁時登記，其他頁面看不到它。

## 驗收對照

| 驗收條件（#122） | 驗證 | 證據 |
|---|---|---|
| 在 `main` 上產生清單裡每一頁、每種寬度與狀態的截圖 | ✅ 實測 | 364 張，與上方推算一致（`e2e/screenshots.py:196` 起的 `shots()`、`:289` 的 `test_capture`） |
| 同一個 commit 拍兩次，比對零差異 | ✅ 實測 | 第一版有 7 張不同（埠號、字型分片），修正後連拍兩次：「共 364 張，364 張畫面相同，0 張畫面有差異；0 頁的字型或基礎字級不同」，而且是**任何一個像素都不能不同**的標準 |
| 故意改一個顏色或間距，報告列出頁面並附差異圖 | ✅ 實測（試驗後已還原） | 同時把「正常」結果橫幅底色改紅、結果橫幅上下內距 1rem→2rem、拿掉字型裡的 Noto Sans TC，只拍 answering：14 張畫面不同（7 個有結果橫幅的結果頁 × 2 寬度，高度 1286→1322，都有差異圖），38 頁字型不同；SSQ12、IOI-HA 結果頁沒有結果橫幅，正確地沒被列出。之後還原，`git diff screening/` 為空 |
| 指定群組時只拍、只比對那一群 | ✅ 實測 | `SHOTS_GROUPS=answering` 只產生 38 張 answering 截圖；`--group answering` 只比 answering（`compare_shots.py:123`） |
| 平常的 `manage.py test` 與 `e2e.main_flow` 不會跑到 | ✅ 實測 | 檔名不是 `test*.py`；`manage.py test` 仍是 644 項（與 main 相同）；單獨叫但沒設 `SHOTS_DIR` 會 skip |

## 已知限制

- 一次只能跑一個拍照（固定埠號 8765）；兩個 worktree 同時拍會直接報錯，不會拍錯。
- 年齡用 `date.today()` 算，基準和新圖跨年拍時，報告上的年齡會不同；遷移期間請在同一天重拍基準。
- 字型本身（Noto Sans TC 有沒有真的載入）不在截圖裡比；字型設定由 `styles.json` 比。

## 測試與審查

- `ruff check .`、`ruff format --check .`：全過。`manage.py test`：644 項全過。
- 沒有新增任何套件：比對用 Playwright 已安裝的 Chromium 的 canvas。
- 自審（`/mattpocock-skills:code-review`，基準 `origin/main`）：
  - **Spec**：3 項要修，都已修——改間距時頁面高度變了只寫「尺寸不同」沒有差異圖（改成以較大尺寸比對、缺的部分算不同，並附差異圖）；擋掉 Google Fonts 後字型掉了看不出來（加 `styles.json`）；顏色容差 16 會放過 #6c757d→#6b7280 這種小偏移（改成任何像素不同都列出）。可考慮：假問卷出現在其他頁（已改成只在自己的結果頁登記）；未登入的解讀（列給本人確認）；埠號與跨年（列為已知限制）。
  - **Standards**：1 項要修——`--tolerance`、`--pixels` 是規格沒要求的設定選項（已拿掉）。採納：App 版頁首改用 `main_flow` 原有的 `STANDALONE`、`--only` 改成用群組名稱的 `--group`、聽力圖改用固定名稱、檔名旗標的寫法統一、`chrome` 判斷只算一次。不採納：e2e 幾個類別重複的 Playwright 開關與登入 cookie，抽共用要改 `main_flow`，超出這張票（`CODING_STANDARDS.md` 第 19 條）。

## 人工驗收

2026-10-21 本人回覆「ok」：同意 (1)「未登入」只對登入前後都看得到的頁面各拍兩種；(2) 擋掉 Google Fonts、改比 `styles.json` 的取捨；(3) 已知限制。
