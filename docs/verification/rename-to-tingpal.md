# 產品改名「聽伴」（無 issue）

日期：2026-11-05。基準：`aa10d90`（main）；分支：`feat/rename-to-tingpal`。決策見 [ADR 0039](../adr/0039-renamed-to-tingpal.md)。

狀態：自動測試全過，**等本人實際操作驗收**。合併前還要本人確認商標。

本人要求不等商標、直接開始，所以跳過拷問、規格和拆票，也沒有規格 issue。

## 怎麼選的

- 名稱：第 0 步查過台灣商標、App Store、網域；英文名從四個拼法裡選 `tingpal`。
- logo：本人看了三批比較頁（A–P）和小鳥加耳朵的組合（Q–T），選 Q。比較頁在暫存資料夾，沒進版控。

## 改了什麼

- 頁面文字、分頁標題、PWA 名稱、匯出檔名、問答小助手的來源名稱、兩色品牌字（「聽」藍、「伴」青綠）。
- logo：標題列、頁尾、開始按鈕、分頁籤、手機主畫面圖示。
- 同意書升到第 3 版，隱私權說明日期改成 2026/11/05。
- 分享封面標題加 `<wbr>`：它原本靠 HearWell 前後的空格換行，拿掉空格後會硬切（e2e 抓到）。
- README、AGENTS.md、CODING_STANDARDS.md、GLOSSARY.md 的名稱，以及 roadmap。

刻意不改：repo、資料庫、服務、`hearwell-frontend`、作答草稿鍵名、`hearwellweb@gmail.com`、`hearwell.onrender.com`、API 文件標題、翻譯檔的中繼資料、舊 ADR 和驗證紀錄。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。

| 需求 | 驗證 | 證據 |
|---|---|---|
| 首頁標題是「聽伴 聽力自我照護」，各頁標題結尾是「｜聽伴」 | ✅ 自動 | `screening/tests/test_pages.py:330` |
| PWA 完整名稱與短名 | ✅ 自動 | `screening/tests/test_pages.py:856` |
| iPhone 主畫面名稱 | ✅ 自動 | `screening/tests/test_pages.py:849` |
| 標題列品牌字兩色 | ✅ 自動 | `screening/tests/test_pages.py:208`、`e2e/main_flow.py:5441` |
| 分頁籤、主畫面圖示、CSS 畫同一隻小鳥 | ✅ 自動 | `screening/tests/test_pages.py:891` |
| 同意過第 2 版的人要再同意一次 | ✅ 自動 | `screening/tests/test_consent.py:171` |
| 隱私權說明的營運者是聽伴開發者 | ✅ 自動 | `screening/tests/test_consent.py:72` |
| 匯出檔名以「聽伴-我的資料」開頭 | ✅ 自動 | `screening/tests/test_export.py:232` |
| 分享封面標題排成整齊兩行 | ✅ 自動 | `e2e/main_flow.py:10264` |
| 聯絡信箱沒被改掉 | ✅ 自動 | `screening/tests/test_layout.py:118` |
| 作答草稿鍵名沒被改掉 | ✅ 檢視 | `frontend/src/draft.js:3`，這次沒有改動這個檔 |
| logo 在 iPhone Safari 顯示正常（耳朵是挖空的，用 SVG 遮罩） | ⬜ 本人 | 自動測試只跑 Chromium |
| 手機加到主畫面後，圖示和名稱正確 | ⬜ 本人 | |
| 舊帳號登入後會看到同意頁，同意後可正常使用 | ⬜ 本人 | |

## 測試結果

- `python manage.py test --settings=config.test_settings`：1623 個全過。
- `python manage.py test --settings=config.test_settings e2e.main_flow --parallel 4`：277 個全過。
- `npm test --prefix frontend`、`npm run build --prefix frontend`：通過。
- `ruff check .`：通過。
- 截圖檢查：`e2e/screenshots.py` 的 public 組，看過手機版首頁和桌面版加到主畫面頁。

## 交叉審查

判斷不需要：沒有動計分、門檻、資料 migration。同意書只升版本號，把關的邏輯沒有改，有測試證明舊版同意的人會被帶去同意頁。本人若要加做，請另一個代理審這個分支。
