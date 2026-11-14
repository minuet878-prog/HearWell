# 只收 POST 的表單在同意書頁或登入頁後回 405（#552）

日期：2026-11-14。基準：`6a9381d`（origin/main）；分支：`fix/gate-next-after-post`；PR #553。

狀態：2026-11-14 本人回覆「驗收通過」。自動測試全過。改動碰到權限（登入、同意書檢查），依規定要交叉審查，**本人決定跳過**。沒有 migration，沒有操作真實資料。

## 原因

正式站 nginx 紀錄（2026-11-13，兩次都一樣）：`POST /journey_todo_tick 302` → `GET /consent?next=/journey_todo_tick` → `POST /consent 302` → `GET /journey_todo_tick 405`。

- 同意書改到第 8 版後要重新同意。首頁在「同意前也能開」的清單裡，還沒同意也看得到待辦、按得到打勾。
- 同意書檢查把送出網址本身當 `next`；同意後瀏覽器用 GET 回到只收 POST 的網址，回 405。`@login_required` 在登入失效時也一樣。
- 同樣會出事的網址共四個：`journey_todo_tick`、`route_answer`、`report_share_create`、`report_share_cancel`。

## 修法

- 新增 `form_address`（`screening/views/common.py`），取代這四個 view 的 `@login_required` 加 `@require_http_methods(["POST"])`：沒登入時 `next` 是表單的 `next`（只接受同站網址），沒有就回首頁。
- 同意書檢查（`screening/middleware.py`）只對標了 `form_address` 的 view 改用同一條規則；其他頁面照舊回原網址（例如 `/account/confirm?action=add_line` 本身可以用 GET 開）。
- 代價：被攔下的那一次操作不會存，回到頁面要再按一次。分享頁的兩個表單沒有 `next`，會回首頁。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。

| #552 驗收條件 | 驗證 | 證據 |
|---|---|---|
| 1 還沒同意時打勾 → `/consent?next=/` | ✅ 自動 | `screening/tests/test_consent.py:362` |
| 2 同意後回首頁 200，不是 405 | ✅ 自動（照正式站紀錄的流程；修改前紅燈 `405 != 200`） | `screening/tests/test_consent.py:380` |
| 3 選配路線作答 → 表單的 `next` | ✅ 自動 | `screening/tests/test_consent.py:362` |
| 4 分享兩個按鈕（沒有 `next`）→ 首頁 | ✅ 自動 | `screening/tests/test_consent.py:362`、`screening/tests/test_share.py:430` |
| 5 外部網址的 `next` → 首頁 | ✅ 自動 | `screening/tests/test_consent.py:362` |
| 6 沒登入：登入頁的 `next` 照 3、4，不寫資料 | ✅ 自動 | `screening/tests/test_accounts.py:86`、`screening/tests/test_journey_todos.py:652`、`screening/tests/test_share.py:240` |
| 7 其他頁面照舊回原網址 | ✅ 自動（既有，未改） | `screening/tests/test_line_confirm_identity.py:571` |
| 8 四個網址仍只收 POST、仍算要登入的頁面 | ✅ 自動 | `screening/tests/test_accounts.py:103`、`screening/tests/test_standards.py:473` |
| 實際操作：登出後在舊分頁打勾，登入後回首頁 | ✅ 本人 | 見下方「人工驗收」 |

## 測試與審查

- 單元測試 `manage.py test --settings=config.test_settings --parallel 4`：2591 項全過。
- `ruff check .`、`ruff format --check .`：全過。
- 沒有改畫面，沒跑 e2e；前端沒有改動。
- 改了三個既有測試的預期（刻意的行為改變）：登出時打勾、分享兩個按鈕被攔下後的 `next`，從送出網址改成首頁。
- 第一版對所有 POST 都改 `next`，整套測試抓到 `/account/confirm` 會被改成回首頁（它本身可以用 GET 開），改成只動標了 `form_address` 的四個網址。
- 自審：對照 `CODING_STANDARDS.md` 沒有違規；`test_standards` 依實際轉址判斷要登入的頁面，換 decorator 不會漏掉健康資料頁的檢查。
- 交叉審查：本人決定跳過。

## 人工驗收

2026-11-14 本人回覆「驗收通過」（8001 開在這個分支的 worktree，已確認行程 cwd）。

1. 登入後停在首頁。
2. 另開分頁登出。
3. 回到原分頁勾一個待辦：被帶到登入頁。
4. 登入後回到首頁，沒有出現 405。

「還沒同意新版同意書」那條路要刪帳號的同意紀錄才能重現，等於動資料庫，由自動測試（驗收條件 1、2）證明。
