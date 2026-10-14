# 帳號與安全

← [回到索引](README.md)

---

## 2026-08-31 密碼相似度驗證器悄悄失效

**情境**
Code review 指出 `validate_password(password)` 沒有傳入 `user` 參數。設定檔裡列了
四個密碼驗證器，但 `UserAttributeSimilarityValidator`（檢查密碼跟使用者名稱像不像）
的實作，沒收到 `user` 就直接 `return`，等於形同虛設。

**驗證過程**
用 `createsuperuser`（Django 內建指令，內部一定會正確傳 `user`）測試同樣的帳密組合，
確認「密碼跟使用者名稱太像」的檢查確實會被觸發；但走自己寫的 `register` view，同樣
組合完全不會被擋——證實了問題真實存在，不是理論推測。

**決定**
在呼叫 `validate_password` 之前，先用 `User(username=username)` 建構一個「尚未存入
資料庫」的 `User` 物件（只建構 Python 物件，不 `.save()`），把這個物件傳給
`validate_password(password, user=user)`。

**理由**
`UserAttributeSimilarityValidator` 需要一個帶有 `username` 等屬性的 `User` 實例才能
比對，但驗證發生在「使用者真正被建立之前」（要驗證通過才會 `create_user`）。Django
的 `Model(...)` 建構子跟 `.save()` 是分開的兩步，可以先建構出物件、取得需要的屬性，
不用真的寫進資料庫。

**代價 / 取捨**
- 這種「看起來完全正常」的 bug 最危險——設定檔上四個驗證器好好列著，沒有任何錯誤或
  警告，只有讀懂 `UserAttributeSimilarityValidator` 原始碼的邏輯（沒收到 user 就直接
  放行）才會發現。之後任何用到 `validate_password` 的地方，都要記得一併檢查有沒有
  傳 `user`。

---

## 2026-09-01 SECRET_KEY 從「安靜使用不安全預設值」改成「正式環境缺少就報錯

**情境**
`SECRET_KEY` 的 fallback 值已經在 git 歷史裡公開過。正式環境若忘記設定環境變數，
程式不會報錯，會安靜用這把已外洩的 key 簽 session/CSRF，任何人都能偽造 session。

**決定**
`DEBUG=True` 維持原本 fallback；`DEBUG=False` 改成不給預設值，拿到 falsy 值就
`raise ImproperlyConfigured`。同時加上 `SECURE_SSL_REDIRECT`、`SESSION_COOKIE_SECURE`、
`CSRF_COOKIE_SECURE`，一樣用 `if not DEBUG:` 包住。

**除錯過程**
用 `DEBUG=False SECRET_KEY=xxx python manage.py check` 模擬正式環境測試：
- `SECRET_KEY=None` 沒觸發——shell 環境變數永遠是字串，讀到的是字串 `"None"`，
  不是 Python 的 `None`
- `SECRET_KEY=""` 也沒觸發——原判斷式只寫 `is None`，沒涵蓋空字串
- 改成 `if not SECRET_KEY:`（利用 truthy/falsy）才一次涵蓋兩種情況

**代價 / 取捨**
`SECURE_HSTS_SECONDS` 刻意沒加——一旦被瀏覽器記住會強制拒絕降級回 HTTP，若 HTTPS
之後出問題會直接卡死使用者，且無法從伺服器端即時補救。等部署環境穩定後再加。

---

## 2026-09-02 register 表單沒有必填檢查，空 username 直接 500（順手測到的 bug）

**情境**
測試的時候，順手把 register 表單空白送出，結果整個網站噴 500，不是正常的
錯誤訊息。原因是 `<input>` 沒寫 `required`，view 也完全沒檢查欄位是不是空的，
`username` 是空字串一路傳到 Django 內建的 `create_user()`，才在那裡 `raise ValueError`，
但 view 的 `try/except` 沒接住這個例外。

**決定**
view 裡在建立 User 之前，先檢查 `username`/`email`/`password`/`confirmation`
四個欄位是不是空的（用 `not username` 這種寫法，同時涵蓋 `None` 和空字串），
不合格就 render 錯誤訊息。同時在 `<input>` 上補 `required`，讓正常使用者在前端
就會被擋下來，不用等到送出才知道漏填。

**代價 / 取捨**
`required` 只是體驗優化，擋不住繞過前端的請求（curl、改 HTML），真正的防線
還是 view 裡的檢查——這跟前面處理過的好幾個安全性問題是同一個道理：前端擋
使用者體驗，後端擋真正的資料完整性。

---

## 2026-09-24 DEBUG 預設改成 False

- 原本沒設 `DEBUG` 就會開除錯模式，連帶讓 `SECRET_KEY` 退回程式碼裡公開的那把。這是 fail open。
- 改成沒設定就是 False（fail closed）。本機要在 `.env` 明確寫 `DEBUG=True`。
- 坑：比對是區分大小寫的字串比對，`DEBUG=true` 會是 False，而且不會報錯。
- 坑：本機測 `DEBUG=False` 會被 SSL 導向，瀏覽器會記住 301，恢復後要用無痕視窗或清快取。
