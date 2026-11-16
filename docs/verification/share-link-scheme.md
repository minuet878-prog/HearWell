# 分享連結不再寫死 `https://`

日期：2026-11-16；分支 `fix/share-link-scheme`（從 `main` 的 `95d80b7` 開出）。
狀態：程式與自動驗證完成；**不需交叉審查**（不碰計分、分級、門檻、migration、權限）。等本人驗收。

## 起因

VPS 部署筆記的待辦：分享報告頁與家人專區要給家人的網址，模板寫死 `"https://"` 再接上網址。當初在 Render 的代理後面，Django 分不出原本是不是 https；搬到 VPS 後 Gunicorn 會把 Nginx 帶的 `X-Forwarded-Proto` 告訴 Django，`request.build_absolute_uri()` 已經算得出 https。

寫死的副作用：本機預覽（`http://localhost:8001`）複製出來的是 `https://localhost:8001/...`，打不開。

## 改了什麼

| 頁面 | 原本 | 現在 |
|---|---|---|
| 分享報告（`/share`）的「可以複製這個網址傳給家人」、兩顆按鈕的 `data-url` | 模板 `"https://"` 接 `request.get_host` 接路徑 | view 用 `request.build_absolute_uri()` 算好傳進模板 |
| 家人專區（`/family`）的網址與「複製網址」 | 同上 | 同上 |

正式站（`https://tingpal.tw`）看到的網址跟以前一樣；本機預覽會變成 `http://localhost:8001/...`。

代價：Render 退路沒有設定信任代理的 header，萬一切回 Render，這兩處會顯示 `http://`（點了會被轉到 https，打得開，只是網址看起來不一樣）。

## 驗證

- 先寫測試、看它失敗、再改：`test_family_guide.FamilyGuideTests.test_address_scheme_follows_the_request`、`test_share_page.SharePageTests.test_link_scheme_follows_the_request`，用 http 開看到 `http://`、用 https 開（`secure=True`）看到 `https://`，網址文字和 `data-url` 都查。改之前 7 項失敗（新的 2 項，加上 5 項原本斷言 `https://testserver` 的，測試用戶端是 http，改成斷言 `http://testserver`）。
- e2e：分享流程複製到的連結改成等於 `live_server_url` 開頭（原本把 `https://` 換回 http 才能開），家人專區兩項的網址比對改成 `http://`。
- 全部：Django 2635 項、e2e 444 項全過；`ruff check`、`ruff format --check` 全過。

## 本人驗收

- [ ] 本機預覽：登入 → 分享報告 → 產生連結，「可以複製這個網址傳給家人」是 `http://localhost:8001/shared/…`，按「複製連結」貼到網址列打得開
- [ ] 本機預覽：家人專區最下面的網址是 `http://localhost:8001/family`
- [ ] 部署後在正式站：兩處都是 `https://tingpal.tw/…`
