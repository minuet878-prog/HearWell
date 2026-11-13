# 註冊頁的電子郵件長度上限

日期：2026-11-14。分支：`claude/confident-carson-f3105c`。來源：交叉審查 LINE 登入（規格 #506）時發現；LINE 的取名頁已經有 254 字的上限，舊的帳號密碼註冊表單從來沒有。

狀態：自動測試做完，等本人確認。

## 問題

註冊表單的電子郵件欄位（`RegisterForm.email`）沒有長度上限，Django 的信箱檢查只擋 320 字以上。所以 255～320 字的信箱會通過表單，到存進資料庫時才因為帳號的 `email` 欄位只放得下 254 字而失敗，使用者看到的是伺服器錯誤（500），不是表單上的提示。

## 修法

- 欄位上限改成跟帳號的 `email` 欄位一樣（`User._meta.get_field("email").max_length`，也就是 254），寫法和 LINE 取名頁相同。
- 255 字：留在註冊頁，欄位下方顯示 Django 的一般訊息「請確認這個值至多包含 254 個字 (目前為 255 個字)。」，跟這頁其他欄位的錯誤（例如名稱已被使用）同一種樣式；不會建帳號。
- 254 字：照常註冊、進同意頁。
- 輸入框帶 `maxlength="254"`，瀏覽器本身就打不進第 255 個字。

## 自動測試

先寫測試看它失敗（輸入框當時是 `maxlength="320"`），再修。

| 項目 | 結果 |
|---|---|
| 新測試 `screening/tests/test_accounts.py` 的 `RegisterFormTests.test_an_email_up_to_the_accounts_254_characters` | 修之前失敗、修之後通過 |
| Django 測試（`--parallel 4`） | 2421 項通過 |
| `ruff check`、`ruff format --check` | 通過 |

## 交叉審查

不需交叉審查：只加欄位長度上限，沒有碰計分、分級、門檻、會動資料的 migration 或權限。
