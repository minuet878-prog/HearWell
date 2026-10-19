# 審查報告：phase6_login_view（登入改用 Django 內建登入、同名註冊不再 500）

- 規格：`docs/specs/phase-06/phase6_login_view.md`
- 審查者：`reviewer` subagent（唯讀），2026-10-16
- 基準：`main`；分支 `refactor/login-view` 已 stage 的變更（`git diff --cached main`）

## 審查結論（reviewer 原文摘要）

實作與規格相符，沒有要修的 bug。

### 各檢查項目
1. **bug**：未發現。查證過的重點：
   - `next`：`LoginView.get_redirect_url()` 用 `url_has_allowed_host_and_scheme`，參數和原本的 `_safe_next` 相同，沒有放寬。
   - 允許的方法：`http_method_names=["get","post"]` 擋掉 `ProcessFormView` 的 PUT；HEAD、OPTIONS 也回 405，跟原本一樣。
   - 已登入的人打開登入頁：`redirect_authenticated_user` 預設 False，照樣顯示。
   - 不透露帳號存不存在：只要表單有錯，就顯示同一句固定文字。
   - 使用者名稱回填有自動跳脫；密碼欄沒有 `value`。
   - 註冊撞車：`atomic` 讓 `IntegrityError` 之後還能查詢；`cleaned_data["username"]` 已經過 NFKC 正規化，和資料庫一致；訊息和 `clean_username` 走同一條路。
2. **多寫**：「其他 `IntegrityError` 照樣丟出」超出規格字面，但它是把例外範圍收窄的防呆，建議不改；`test_duplicate_username_message` 和舊測試部分重疊，但驗收 12 要比對字樣，建議不改。
3. **漏掉驗收條件**：見下方第 1 項。驗收 4「密碼欄是空的」是間接驗證（頁面上不能出現密碼），效果已經足夠，建議不改。
4. **「不做」清單**：未發現問題。
5. **不可違反的規則**：未發現問題。

### 測試結果
- 後端 365 通過、0 失敗；`ruff check .` 通過；`git status` 只有 8 個 stage 的檔案。

## 發現與查證

### 1. 驗收 1 的測試沒有檢查「已登入」

- **位置**：`screening/tests/test_accounts.py`，`LoginNextTests.test_login_without_next_goes_home`
- **reviewer 說**：驗收 1 寫「轉到首頁，**而且已登入**」，但測試只檢查轉址。首頁未登入也回 200，登入沒成功也會通過。
- **查證**：屬實，已重現。試驗時在記憶體裡把 `LoginView` 的登入動作換成什麼都不做（沒有改檔案），這個測試照樣通過（failures: 0）。
- **分類**：**補測試**。加一行斷言 session 裡是這個使用者。

### 2. 其他 `IntegrityError` 照樣丟出（超出規格字面）

- **查證**：屬實。實作時已經在對話裡說明，會寫進「規格以外的決定」。拿掉那兩行時，對應的測試會失敗（試驗過）。
- **分類**：**不改**。

### 3. 規格狀態和 roadmap 不一致

- **查證**：屬實。規格是「實作中」，roadmap 已經打勾。
- **分類**：**不改**。收尾第 9 步會把規格改成「已完成」，兩邊就一致了。

### 4. 失敗後游標仍停在使用者名稱欄

- **位置**：`screening/templates/screening/login.html` 使用者名稱欄的 `autofocus`
- **reviewer 說**：現在失敗後名稱會留著，但游標還是停在名稱欄，密碼錯的人要自己移到密碼欄。
- **查證**：屬實。以前名稱會清空，所以停在名稱欄是對的；這次留住名稱後，焦點就變得不理想。
- **分類**：**不改**（規格寫明不改排版）。這是需求決定，交給本人：要改的話，失敗時把 `autofocus` 放到密碼欄（一個模板條件）。
