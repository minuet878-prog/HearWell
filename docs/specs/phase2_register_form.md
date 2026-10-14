# Phase 2 規格：註冊改用內建表單，選填出生年

- **狀態**：已完成
- **分支**：`feat/register-form`
- **擬稿**：AI　　**確認人**：本人　　**確認日期**：2026-10-14

> 給 AI 的說明：本規格狀態為「已確認」之前，不得開始實作。
> 規格沒寫到、而且會影響行為的地方，先停下來問，不要自行決定。

---

## 1. 目標

註冊的驗證交給 Django 內建、經過驗證的表單，錯誤訊息出現在出錯的欄位旁，長輩知道要改哪裡。同時用最少的個資（只有出生年、選填）為之後的年齡導引（A1）做準備。

## 2. 範圍

### 要做
- 註冊改用 Django 內建 `UserCreationForm` 為基礎：使用者名稱、電子郵件（必填）、密碼、密碼確認、出生年（選填）。
- 出生年用**民國**輸入：畫面是「民國 ___ 年」的數字框，旁邊說明「選填。用來推薦適合您年齡的問卷，不會公開。」；系統內部存**西元**年。
- 出生年可填範圍：民國 1 年 ～（今年 − 18 − 1911）年，也就是西元 1912 ～ 今年減 18。超出範圍或不是數字時，欄位旁顯示「請輸入民國 1 到 N 年之間的數字」（N 依今年計算）。
- 錯誤訊息用 Django 內建繁體中文翻譯，顯示在對應欄位旁；出錯時已填的使用者名稱、電子郵件、出生年保留。
- 密碼規則說明在出錯重新顯示時也要出現（修正原本出錯後消失的問題）。
- 資料欄位：現有的「完整生日」換成「出生年」。搬移時，已經有生日的帳號保留年份、丟掉月日（**本人已同意修改正式資料庫的使用者資料**）。
- 年齡改用出生年計算（今年 − 出生年），沒填就是「沒有年齡」。
- admin 的使用者頁面跟著改成出生年。
- 上一輪的「登入／註冊後回到原本的頁面」行為不變。

### 不做
- 登入改用內建 `LoginView`。
- Django 內建訊息裡的「你」改成「您」（記進 roadmap）。
- 舊使用者補填出生年的提示。
- A1 年齡導引（推薦問卷）。
- 忘記密碼、電子郵件驗證。
- 對比度、`text-muted`（屬於無障礙基準線；新加的文字不使用 `text-muted`）。

## 3. 必須遵守的規則

- 一律遵守 CLAUDE.md「不可違反的規則」。
- 本 phase 特別注意：
  - 個資：出生年不寫進 log，測試用假資料。
  - 密碼相似度檢查（`UserAttributeSimilarityValidator`）必須仍然有效（見 decisions/security.md 2026-08-31）。
  - migration 會修改正式資料庫：要可逆，或明確說明不可逆的部分（月日丟掉後無法還原）。
    - **不可逆的部分（審查後補充）**：往前套用後，月日永久消失；如果再退回 0014，`birth_date` 會變成空的、`birth_year` 被刪掉，**全部出生資料都會遺失**。
    - **部署空窗（審查後決定，本人選擇接受）**：Render 在舊版程式仍在服務時就跑 migration，0016 刪掉 `birth_date` 後到新版上線前，已登入的請求可能短暫 500。不採用「先擴充、再收縮」分兩次部署。
  - 新文字字級用 `rem`。

## 4. 行為描述

### 4.1 註冊頁

| 項目 | 內容 |
|---|---|
| 網址與方法 | 既有註冊頁，GET 顯示、POST 註冊 |
| 誰可以使用 | 所有人 |
| 回傳／顯示的欄位 | 使用者名稱、電子郵件、密碼（含密碼規則）、密碼確認、出生年（民國，選填，含說明） |
| **不能**回傳／顯示的欄位 | 出錯重新顯示時，密碼欄位不回填 |
| 需要計算的資料 | 民國 → 西元（＋1911），由後端計算 |
| 空資料時的行為 | 出生年空白 → 存成「沒有出生年」，照常註冊 |

### 4.2 使用者資料

| 項目 | 內容 |
|---|---|
| 欄位 | 出生年（西元整數，可為空） |
| 年齡 | 今年 − 出生年；沒有出生年 → 沒有年齡 |
| 舊資料 | 有完整生日的帳號 → 出生年 = 生日的年份 |

## 5. 驗收條件

- [x] 1. 假設未登入，當打開註冊頁，則看到使用者名稱、電子郵件、密碼、密碼確認、「民國 ___ 年」出生年欄位，出生年旁有說明「選填。用來推薦適合您年齡的問卷，不會公開。」，並顯示密碼規則。
- [x] 2. 假設所有必填欄位正確、出生年空白，當送出，則建立帳號、出生年為空、自動登入並回首頁。
- [x] 3. 假設出生年填民國 44，當註冊成功，則存下的出生年是西元 1955。
- [x] 4. 假設出生年填民國 1 或民國 N（今年 − 18 − 1911），當送出，則都能註冊成功。
- [x] 5. 假設出生年填 0、N＋1、「abc」或 1955（西元），當送出，則不建立帳號，出生年欄位旁顯示「請輸入民國 1 到 N 年之間的數字」。
- [x] 6. 假設兩次密碼不同，當送出，則不建立帳號，密碼確認欄位旁顯示「輸入的兩個密碼不一致。」，已填的使用者名稱、電子郵件、出生年保留，密碼規則仍顯示。
- [x] 7. 假設使用者名稱已被使用，當送出，則不建立新帳號，使用者名稱欄位旁顯示錯誤。
- [x] 8. 假設使用者名稱、電子郵件或密碼空白，當送出，則不建立帳號、顯示必填錯誤，不會 500。
- [x] 9. 假設密碼跟使用者名稱太像，當送出，則不建立帳號，顯示密碼太相近的錯誤。
- [x] 10. 假設一個帳號原本有完整生日 1955-06-01，當套用 migration，則出生年變成 1955。
- [x] 11. 假設出生年 1955，則年齡 = 今年 − 1955；沒有出生年，則年齡為空。
- [x] 12. 假設從主按鈕來到註冊頁，當註冊成功，則仍然到原本要去的頁面；外部網址仍然回首頁（上一輪的測試全部通過）。
- [x] 13. 新加的說明文字字級用 rem、不用 `text-muted`。

## 6. 待決問題

- [x] ~~生日怎麼收？~~ → 只收出生年、選填
- [x] ~~電子郵件？~~ → 維持必填
- [x] ~~登入要不要一起換？~~ → 這次只換註冊
- [x] ~~錯誤訊息用詞？~~ → Django 內建繁中翻譯，顯示在對應欄位旁
- [x] ~~出生年範圍？~~ → 1900～今年減 18；因為改用民國輸入，實際下限為民國 1 年（西元 1912）
- [x] ~~欄位說明？~~ → 「選填。用來推薦適合您年齡的問卷，不會公開。」
- [x] ~~內建訊息的「你」？~~ → 這次不處理，記進 roadmap
- [x] ~~舊生日資料？~~ → 保留年份、丟掉月日（本人同意修改正式資料）
- [x] ~~輸入方式？~~ → 民國數字框（比較頁選 B）

---

## 完成後回報（由 AI 填寫）

- **改了哪些檔案、為什麼**：
  - `screening/models.py`：`birth_date` → `birth_year`（西元、可空）；`age` = 今年 − 出生年。
  - `migrations/0015_user_birth_year.py`：新增 `birth_year`，`RunPython` 複製舊生日的年份；反向不捏造月日。`0016_remove_user_birth_date.py`：刪 `birth_date`。拆兩個檔，避免 PostgreSQL 同一交易內「改資料 → 改結構」。
  - `screening/forms.py`：新增 `RegisterForm(UserCreationForm)`：email 必填、民國出生年（`isdecimal()` 檢查範圍，`save()` 加 1911）、所有欄位加 `form-control`。
  - `screening/views.py`：`register` 改成標準表單流程，刪掉手寫檢查與 `validate_password`。
  - `register.html`：逐欄輸出 label、輸入框、錯誤、說明；出生年用「民國 ___ 年」。
  - `field_messages.html`（新）：輸出錯誤與說明，帶上 Django `aria-describedby` 指向的 id。
  - `screening/admin.py`：使用者頁改成 `birth_year`。
  - `screening/tests.py`：新增 `RegisterFormTests`（14 個）、`BirthYearMigrationTests`；`LoginNextTests` 改用新欄位名稱。
  - `docs/roadmap.md`：打勾，記下還沒做的與已知風險。
- **驗收條件對應的測試**：
  1. `RegisterFormTests.test_register_page_fields`
  2. `test_register_without_birth_year`
  3. `test_roc_year_is_stored_as_western_year`
  4. `test_roc_year_boundaries_accepted`
  5. `test_invalid_roc_year_rejected`（含「²」）
  6. `test_password_mismatch_keeps_input`
  7. `test_duplicate_username_rejected`
  8. `test_required_fields`
  9. `test_password_similar_to_username_rejected`（暫時拿掉驗證器時會失敗）
  10. `BirthYearMigrationTests.test_birth_date_year_is_kept`
  11. `test_age_from_birth_year`
  12. `LoginNextTests` 註冊相關測試
  13. `test_note_uses_readable_style`、`test_password_rules_use_rem_size`
  - 另有 `test_aria_describedby_targets_exist`（螢幕閱讀器能讀到錯誤與說明）。
- **規格以外的決定**：
  - 審查後修正：上標數字「²」會讓註冊 500（`isdigit()` 與 `int()` 定義不一致），改用 `isdecimal()`。
  - 審查後修正：輸入框的 `aria-describedby` 指向不存在的 id；密碼規則用 `form-text`（.875em）改成 `fs-5`。
  - 新增共用模板 `field_messages.html`，避免同一段在註冊頁寫兩次。
  - 出生年說明改成欄位的 `help_text`，讓 Django 自動把說明連到輸入框。
  - 使用者名稱重複改成不分大小寫比對（`UserCreationForm` 內建行為）；密碼相似度也會比對 email。
- **這次用到的新概念**：`UserCreationForm`、ModelForm 的 `save(commit=False)`、資料 migration（`RunPython`）、遷移測試（`MigrationExecutor`、`TransactionTestCase`）、部署空窗與 expand/contract、`isdecimal` vs `isdigit`、`aria-describedby`、個資最小蒐集。
- **面試可能追問的 2–3 題**：Q22（改欄位的 migration 與部署空窗）、Q23（`isdigit()` 讓 500 漏出來）、Q24（只收出生年的取捨）。要點見 `docs/interview.md`。
- **建議寫進 decisions/ 的內容**：見對話（由本人撰寫）。
