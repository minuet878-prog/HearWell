# #182 健康資料頁面禁止快取

日期：2026-10-22；分支 `feat/182-health-pages-never-cache`（從 `main` 的 `0dc64e9` 開出，之後合進 #205 後的 `main`）。
狀態：自動驗證完成；**本人決定跳過交叉審查**（2026-10-22「開pr跳過交叉」）；等本人實際操作驗收。

## 範圍

- [#182](https://github.com/minuet878-prog/HearWell/issues/182)、拷問 Q37、Q45；用語見 `GLOSSARY.md`「健康資料頁面」。
- `screening/views.py:69` 新增 `@health_data_page`：包 Django 的 `never_cache`，並在 view 上標記。標在 13 個頁面：選問卷精靈、作答頁、結果頁、我的紀錄、配戴狀態比較、資料下載、聽力報告、帳號設定、聽力圖清單／檢視／修改／刪除確認／比較。
- 例外清單 `NO_HEALTH_DATA`（`test_standards.py:119`），每項附理由：同意頁、新增聽力圖（空白頁）、刪除帳號確認頁（只有筆數）、產生與取消分享（只收 POST）。
- `CODING_STANDARDS.md` 第 24 條。
- 沒改：頁面內容、權限、資料；家人分享封面與分享報告（Phase 8 已經禁止快取）；登入後的首頁（2b 已經禁止快取）；`/api/`。

## 驗收條件對照

| 條件 | 證明 |
|---|---|
| 1. 健康資料頁面回應禁止快取 | `test_health_data_pages.py:36` `test_health_data_pages_are_never_cached`：13 個網址逐一檢查 `Cache-Control` 含 `no-store` |
| 2. 分享封面、分享報告照舊禁止快取 | `test_share.py:213`（既有測試，這次沒改） |
| 3. 隱私權、家人溝通、加到主畫面、沒登入的首頁不禁止 | `test_health_data_pages.py:56`（另含註冊頁）；`test_home.py:176` |
| 4. 登出後按上一頁看到登入頁 | 沒有自動測試，見下方「拿掉的端對端測試」；**請本人在 Safari、Chrome 手動操作** |
| 5. 新頁面沒標記也沒列例外，檢查會失敗 | `test_standards.py:158`：用沒登入的身分逐一打網址設定裡的頁面，被帶去登入的就是要登入的頁面，每一個都要有標記或例外；`:169` 證明沒標記的會被抓出來。試驗見下方 |
| 6. 例外清單每一項附理由 | `test_standards.py:119` |
| 7. 規範有一條 | `CODING_STANDARDS.md:53` 第 24 條 |

## 先看到失敗（試驗，做完已還原）

- 頁面測試先寫：13 個網址中 11 個失敗（比較頁、資料下載本來就有），加上標記後通過。
- 規範檢查：把「我的紀錄」的標記拿掉，`test_every_logged_in_view_is_marked_or_excused` 失敗並列出 `['my_hearing']`；還原後通過。

## 拿掉的端對端測試（第 4 條）

規格原本要用 e2e 測「看結果頁 → 登出 → 按上一頁 → 看到登入頁」。試驗：把 `views.py` 換回 `main` 的版本（沒有禁止快取）再跑，測試照樣落在登入頁、照樣通過。測試用的 Chromium 不會從快取還原這一頁，所以這個測試永遠不會失敗，證明不了什麼，就拿掉了。第 4 條改由第 1 條的標頭檢查，加上本人在真的瀏覽器手動確認。

## 自動驗證

| 項目 | 結果 |
|---|---|
| Django 全部 | 803 個通過（合進 #205 後的 `main` 再跑） |
| 前端（Vitest） | 201 個通過 |
| e2e `e2e.main_flow` 全套 | 82 個通過（合進 `main` 之前跑的；合併後由 CI 跑） |
| Ruff | 通過 |

## 自審（`/mattpocock-skills:code-review`）

| 發現 | 處理 |
|---|---|
| Spec：檢查只認得 `views.py` 裡單純的 `@login_required`，帶參數、mixin、其他模組都會漏掉 | 已改：改成打網址設定裡的每一頁，看會不會被帶去登入，跟寫法無關 |
| Standards：`view.health_data_page = True` 沒人讀 | 已改：新的檢查就是讀這個標記 |
| Standards：新函式插在 `HOME_PREVIEW_SCORE` 的註解和常數中間 | 已改：移到註解上方 |
| Standards：第 24 條和兩個用 `add_never_cache_headers` 的頁面（家人分享頁、首頁）不一致 | 已改：第 24 條寫明這兩個例外和各自的測試 |
| Standards：測試變數 `audiogram` 其實是參數清單 | 已改名 `audiogram_args` |
| Spec：第 4 條沒有自動斷言 | 見上方，改由本人手動確認 |

## 交叉審查

本人決定跳過（2026-10-22）。依 `AGENTS.md`，這張碰到資料存取保護，原本要由 Codex 審查；這次只有上面的自審。

## 請本人驗收

- [ ] Safari：登入 → 打開結果頁 → 登出 → 按上一頁，看到的是登入頁，不是結果頁。
- [ ] Chrome：同上。
- [ ] 隨便點幾個頁面（我的紀錄、聽力圖、聽力報告），操作和以前一樣。
