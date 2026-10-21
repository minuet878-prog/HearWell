# #104：擋住寫死的問卷代碼，證明「加問卷只需定義」

日期：2026-10-21。規格：[#104](https://github.com/minuet878-prog/HearWell/issues/104)（母規格 [#99](https://github.com/minuet878-prog/HearWell/issues/99)，決策見 ADR 0005）。基準：`713a05e`（#100 的 PR #113 合併後的 `main`）；功能分支：`refactor/questionnaire-code-guard`。

狀態：2026-10-21 本人人工驗收通過（回覆「#104 驗收 ok」）。沒有動真實資料，沒有 migration，也沒有改正式程式碼（只加測試和一句規範）。

## 行為

- 新的規範檢查（`test_standards.py` 的 `QuestionnaireCodeTests`）：掃 `screening/` 和 `frontend/src`，問卷代碼只能出現在問卷定義（`screening/questionnaires/`）裡。代碼清單直接取自定義的註冊表，以後新增的問卷自動納入檢查。
- 不掃的地方：測試（`screening/tests/`、前端 `*.test.*`）、migration、fixture、問卷定義套件本身，以及前端 build 產物 `screening/static/screening/frontend/`（不進版控，內容由 `frontend/src` 產生）。
- 比對規則：代碼前後不能接英數字或連字號才算。所以聽力報告裡的 HTML id `report-ioi-ha`、`ioi-ha-title` 不算寫死代碼：它們是報告的錨點，#99 要求錨點照舊，不改名。畫面上的顯示名稱（大寫的 `HHIE-S`）也不算。
- 假問卷全流程：測試中只登記一份假的問卷定義（含名稱、題目、選項、門檻、建議），由 `seed_questionnaires` 建立問卷，再用 test client 走完目錄 → 作答 → 結果 → 我的紀錄。第一次跑就通過，表示 #100–#103 已經把判斷搬進定義，這張票負責補上證據。
- 遺留清理：查證後沒有要清的。只用到一次的名稱都是 Django 自己會呼叫的（設定值、admin 權限方法、列舉值）；`scoring.py` 的 `IOI_HA_*` 常數仍在用（IOI-HA 專屬功能，#99 規定維持原樣）；舊指令 `seed_hhia_s`、`seed_ssq12` 只剩歷史文件提到。
- `CODING_STANDARDS.md` 第 9 條補一句：問卷代碼字串只寫在問卷定義裡，並註明由 `test_standards.py` 自動檢查。

## 驗收對照

勾選代表自動驗證通過，不代替本人實際操作確認。

| 條件 | 自動驗證 | 證據 |
|---|---|---|
| 1. 問卷定義以外沒有寫死代碼；故意加一行時檢查會失敗 | ✅ | 沒有寫死代碼 `test_standards.py:94`；確實掃到 `views.py` 和前端 jsx `:88`；偵測器抓到寫死的那一行、放過錨點 id `:98`。另做過試驗：在 `views.py`、`trend.js` 各加一行代碼，檢查失敗並指出 `screening/views.py:941`、`frontend/src/trend.js:79`，試驗後已還原 |
| 2. 只有定義的假問卷走完目錄 → 作答 → 結果 → 歷史 | ✅ | 目錄 `test_questionnaire_definitions.py:459-460`；作答頁 `:463-464`；送出後轉到結果頁 `:479`；結果（總分、滿分、分級、建議、答案文字）`:482-485`；我的紀錄 `:488-490`。假問卷只靠 `register()` 在測試中暫時登記，沒有改任何定義以外的檔案 |
| 3. 後端、前端、端對端測試全過；現有測試沒改 | ✅ | 見下方「測試與審查」；`git diff main --stat` 的測試檔只有新增，沒有刪改既有測試 |
| 4. 沒有重構遺留、沒人用的常數、函式或 import | ✅ 人工查證 | `ruff check .` 通過（含沒用到的 import）；腳本列出 `screening/`、`config/` 所有頂層與類別內名稱並搜尋引用；模板檔、前端模組都有人引用 |

## 測試與審查

- 完整 Django：642 項通過（34.389 秒）。前端：12 個檔、186 項通過。端對端：先 `npm run build` 再跑，26 項通過（78.481 秒）。`ruff check .` 通過。
- 重新 build 前，本機舊的 `answer.js` 還留著 #100 之前比對 `ssq12-tw` 的寫法；build 後消失。這個檔不進版控，部署時由 `build.sh` 重新產生。
- 自審（Matt `/code-review`）：Standards 0 項硬性違規，6 項判斷題，採納 2 項（`code_lines` 改名 `questionnaire_code_lines`、`CODING_STANDARDS.md` 補註），其餘（formset 資料重複、兩種寫法並存）跟著現有寫法不修。Spec 0 項要修，採納 1 項建議（加斷言鎖住掃描範圍，避免路徑寫錯時檢查空轉）。
- 交叉審查：本人 2026-10-21 決定這個 session 跳過。

## 人工驗收

2026-10-21 本人回覆「#104 驗收 ok」，以下操作範圍確認通過。這張票沒有改畫面和正式程式碼，驗收以跑測試為主：

1. 跑這次的兩組測試，結果是 OK：
   `python manage.py test --settings=config.test_settings screening.tests.test_standards screening.tests.test_questionnaire_definitions`
2. 試著寫死一個代碼：在 `screening/views.py` 最後加一行 `X = "ioi-ha"`，再跑一次 `screening.tests.test_standards`，應該失敗並指出 `screening/views.py` 的行號。看完用 `git checkout screening/views.py` 還原。
3. （可選）打開本機網站的問卷目錄、任一份結果頁、我的紀錄：跟 `main` 一樣（這次沒改正式程式碼）。
