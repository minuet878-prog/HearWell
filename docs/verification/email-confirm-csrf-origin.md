# 驗證：確認信箱按鈕「CSRF 驗證未通過」（2026-11-23）

沒有開規格 issue：正式站上本人測試時發現的 bug，修補範圍只有確認信箱頁。

## 問題

2026-11-23 本人在正式站從確認信打開連結、按「確認信箱」，畫面顯示「CSRF 驗證未通過」。資安修補（2026-11-19 上線）之後，正式站沒有人能完成信箱確認。

## 根本原因

- 確認信箱頁由 `email_link_page` 回應，帶 `Referrer-Policy: no-referrer`（不讓連結裡的代碼外流）。
- 照 Fetch 標準（append a request Origin header），從 `no-referrer` 的頁面送出 POST 時，瀏覽器把 `Origin` 填成 `null`。
- Django 的 CSRF 檢查在有 `Origin` 時先比對來源，`null` 對不上網站的網址，回 403。
- 單元測試的測試工具不帶 `Origin`，e2e 沒有測這顆按鈕，所以沒抓到。

本機重現（`RequestFactory` 加 `CsrfViewMiddleware`，HTTPS、`Host: tingpal.tw`）：`Origin: https://tingpal.tw` 通過，`Origin: null` 回 403，log 印出 `Origin checking failed - null does not match any trusted origins.`。

同一個原因的其他地方：`email_link_page` 和分享報告頁（`reports._family_page`）也用 `no-referrer`。取消提醒頁是 `csrf_exempt`（Gmail 一鍵取消要用），分享報告頁沒有 POST 表單，兩者都不受影響，不改。

## 修法（本人選）

只有確認信箱頁（還沒按按鈕時那一頁）改成 `Referrer-Policy: same-origin`：送回聽伴自己時照常帶 `Origin`，送到其他網站仍然什麼都不帶。CSRF 保護保留。

## 測試

- 先寫測試 `test_the_button_passes_the_csrf_check_as_a_browser_sends_it`（`screening/tests/test_email_confirmation.py`）：用 `enforce_csrf_checks=True` 的 client，照頁面的 `Referrer-Policy` 決定瀏覽器會送的 `Origin`（`no-referrer` → `null`），帶 CSRF token 送出。修之前失敗（403），修之後通過。
- `test_opening_the_link_asks_and_confirms_nothing` 的斷言從 `no-referrer` 改成 `same-origin`。
- 全部測試：3298 個通過（1 個略過），`--parallel`。
- `ruff check .`、`ruff format --check .` 通過。

## 交叉審查

需要：碰到 CSRF（權限）。2026-11-23 由另一個代理以 `main` 為基準跑 `/code-review`，本人回報通過，沒有要修。

## 本人驗收

- [ ] 部署後在正式站註冊測試帳號、收確認信、按「確認信箱」，看到「信箱確認好了」；帳號設定的「還沒確認」標籤不見。

## 待辦（不在這次範圍）

- 2026-11-19 資安修補的本機驗收第 3 步（按確認信箱）當時通過，跟這次的原因對不起來，原因還沒查清楚（可能跟當時用的瀏覽器有關）。
- e2e 加一條真的瀏覽器按「確認信箱」的測試，單元測試的測試工具不帶 `Origin`，抓不到這類問題。
