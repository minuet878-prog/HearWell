# views.py、models.py 依功能拆成 package（#380）

日期：2026-10-26。基準：`bf4381b`（開工時的 origin/main，PR #370 合併後），之後合進 `ddb8ec5`（#383、#384，沒有碰到拆分的檔案）。分支：`refactor/380-split-views-models`。規格：[#380](https://github.com/minuet878-prog/HearWell/issues/380)，子票 [#381](https://github.com/minuet878-prog/HearWell/issues/381)（models）、[#382](https://github.com/minuet878-prog/HearWell/issues/382)（views）。

狀態：2026-10-26 本人回覆「人工驗收五項都通過」。自動測試與比對全過；交叉審查（Codex）要修 0 項。沒有 migration，沒有操作真實資料。

## 做了什麼

只搬不改：每個頂層函式、類別、常數的本體原封不動搬到新檔，只改 import、`urls.py` 的引用、測試的 import／mock 指向／寫死的檔名，以及提到舊檔名的註解。

- `screening/models/`：accounts、questionnaires、submissions、sharing、audiograms、hearing_aids、guide。入口檔把原本每個名字都轉出，`from screening.models import X` 照舊；舊 migration 0022 指名的 `_share_token`、`_share_expiry` 也轉出，Django 判定欄位沒變。
- `screening/views/`：common、home、guide、accounts、monitoring、answering、my_hearing、results、reports、export、audiograms。入口檔是空的，`urls.py` 直接寫「小檔.函式」。
- `AGENTS.md`：結構段改寫成兩個資料夾的分工；已知陷阱加「mock 要指到實際用到它的小檔，同一個值有兩處讀取時兩邊都要換」。

Commits：`a02cedc` 拆 models、`ff58c6d` 拆 views、`8d62fbc` 自審修正、`a0235ca` 合進最新 main。

## 證明「行為不變」的比對

比對程式是一次性的，不進版控；結果如下（最新一次是合進 `ddb8ec5` 之後重跑）。

| 比對 | 方法 | 結果 |
|---|---|---|
| 程式本體 | 用 Python `ast` 逐一比對拆前檔與新 package 每個頂層名字的語法樹（含 decorator 與順序；註解不算） | views 93／93、models 31／31，沒有缺、沒有多、沒有不同 |
| 網址 | 列出所有網址的路徑、名稱、對應函式名，拆前拆後 diff | 87 條完全相同 |
| API | `manage.py spectacular` 產生 OpenAPI schema，拆前拆後逐位元組比對 | 相同 |
| 資料庫 | `makemigrations --check --dry-run` | No changes detected |

比對程式先自測過：內容相同時回報 0；故意改一個常數、拿掉 `@health_data_page` 時逐項抓出來。

## 測試改了什麼（斷言都沒刪）

| 測試 | 改動 | 原因 |
|---|---|---|
| `test_consent` 版本升級那一個 | 同時換掉 `screening.models.accounts.CONSENT_VERSION` 和 `screening.models.CONSENT_VERSION` | User 讀小檔那份、view 讀入口那份；拆前一次就換到兩邊 |
| `test_answering` | `_find_by_key` 的取用與 mock 改指 `views.answering` | 呼叫它的作答頁在那裡 |
| `test_monitoring` | `render` mock 改指 `views.home`；表單 save 改指 `answering`、`accounts`；堆疊檔名改成 `screening/views/home.py` | 首頁程式換了檔名，錯誤回報要看得到出錯的檔 |
| `test_guide`、`test_questionnaire_cards` | import 改從 `views.guide`、`views.answering` | 位置變了 |
| `test_standards` | `health_data_page` 從 `views.common` 匯入；問卷代碼掃描改成斷言 views 資料夾的每個檔都在掃描範圍 | 原本只確認單一個 `views.py` |

## 驗收對照（#380）

| 驗收 | 驗證 | 證據 |
|---|---|---|
| views 11 個功能檔、入口空、舊檔不在 | ✅ | diff 與檔案清單 |
| models 7 個功能檔、入口轉出全部名字 | ✅ | `models/__init__.py`；`makemigrations` 無變更 |
| 每個頂層名字語法樹一致 | ✅ 一次性比對 | 見上表 |
| 沒有新 migration | ✅ | 見上表；`test_standards` 的 migration 檢查也過 |
| 網址不變 | ✅ 一次性比對 | 見上表 |
| OpenAPI schema 不變 | ✅ 一次性比對 | 見上表 |
| 單元測試全過、斷言沒改 | ✅ | 見「測試與審查」；測試 diff 只有上表各項 |
| e2e 全過 | ✅ | 見「測試與審查」 |
| 錯誤回報堆疊指到首頁小檔 | ✅ 自動 | `test_monitoring.py:142` |
| 問卷代碼掃描涵蓋整個 views 資料夾 | ✅ 自動 | `test_standards.py:399`、`:401`（每個 views 檔都在範圍）、`:407` |
| `urls.py` 寫成「小檔.函式」 | ✅ | diff |
| 提到舊位置的註解已改 | ✅ | `git grep` 只剩 `models/__init__.py` 說明為何全部轉出的那句（刻意提到舊檔）；改了 serializers、test_sadl、privacy／ioi_ha_summary／score_gauge 模板、site.css 註解 |
| Ruff 通過 | ✅ | `ruff check .` |
| AGENTS.md 結構與陷阱 | ✅ | `AGENTS.md` 結構段、已知陷阱 |
| 至少兩個 commit、各自測試會過 | ✅ | `a02cedc`：1448 全過；`ff58c6d`：1448 全過、e2e 276 全過 |
| 合併後開後續票 | ⏳ 合併後 | 跨檔借用底線名字的清單見下 |

## 測試與審查

- 單元測試 `manage.py test --settings=config.test_settings --parallel 4`：1449 項全過（合進最新 main 後；main 多了 #384 的 1 項）。
- 前端 `npm test --prefix frontend`：363 項全過；建置成功。
- 端對端 `e2e.main_flow --parallel 4`：276 項全過（先建置前端）。
- `ruff check .`：通過。
- 自審（Standards／Spec 兩軸）：沒有要修。採納三項：`test_consent` 恢復兩邊都換、問卷代碼掃描斷言整個 views 資料夾、AGENTS.md 補齊 models 說明與陷阱。不採納（留給後續票）：底線名字跨檔借用、結果頁經匯出依賴到指引的長鏈。
- 交叉審查（Codex，基準 `origin/main` `ddb8ec5`，HEAD `8d62fbc`）：Standards、Spec 要修都是 0。另外獨立確認 20 個 `@login_required`、15 個 `@health_data_page` 都在，`urls.py` 正規化後路徑、名稱、函式一致。

## 後續票要列的跨檔借用（使用的檔 ← 定義的檔）

- home ← answering：`_continue_notice`；home ← results：`_score_bar`、`_score_gauge`、`_ioi_ha_summary`
- guide ← answering：`_wearing_follow_ups`；guide、accounts ← common：`_safe_next`
- results ← my_hearing：`_shows_wearing_comparison`；results ← export：`_has_subscores`
- reports ← audiograms：`_audiogram_context`；reports ← results：`_ioi_ha_summary`
- 原本就有：answering ← `screening.api.views`：`_find_by_key`（網頁層借 API 層）
- 依賴鏈：結果頁 ← 匯出 ← 指引 ← 作答，改匯出會牽動結果頁

## 人工驗收

這次沒有改任何畫面，請用預覽網站隨手走一輪，確認每一區都還打得開、資料都在：

1. 首頁 → 選問卷 → 作答一份 → 結果頁。
2. 我的紀錄：問卷、聽力圖兩個分頁；打開一張聽力圖。
3. 聽力報告 → 建立分享連結 → 用無痕視窗打開家人分享頁。
4. 選配指引：打開一章，回答路線上的一個問題。
5. 帳號設定 → 下載我的資料。

回覆：2026-10-26 本人確認五項都通過。
