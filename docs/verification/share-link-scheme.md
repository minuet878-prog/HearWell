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

正式站算出 https 靠的是 VPS 上的 Gunicorn 預設信任 127.0.0.1 送來的 `X-Forwarded-Proto`（設定在 VPS，不在 repo），所以「正式站是 https」要部署後看驗收第 3 項。Render 退路：正式環境開著 `SECURE_SSL_REDIRECT`，Django 分不出 https 的話整站會無限轉址；Render 上網站開得起來，代表那邊也分得出來，切回去應該一樣是 https（沒實測）。原本模板註解「Render 的代理後面分不出 https」跟這點對不起來，這次一併拿掉。

## 驗證

- 先寫測試、看它失敗、再改：`test_family_guide.FamilyGuideTests.test_address_scheme_follows_the_request`、`test_share_page.SharePageTests.test_link_scheme_follows_the_request`，用 http 開看到 `http://`、用 https 開（`secure=True`）看到 `https://`，網址文字和 `data-url` 都查。改之前 7 項失敗（新的 2 項，加上 5 項原本斷言 `https://testserver` 的，測試用戶端是 http，改成斷言 `http://testserver`）。
- e2e：分享流程複製到的連結改成等於 `live_server_url` 開頭（原本把 `https://` 換回 http 才能開），家人專區兩項的網址比對改成 `http://`。
- 全部：Django 2635 項、e2e 444 項全過；`ruff check`、`ruff format --check` 全過。
- 自審（`/mattpocock-skills:code-review`，規範、需求兩個代理）：沒有硬性違規；兩處 `build_absolute_uri(reverse(...))` 只有兩處，照「只用一次不抽象」不抽。需求代理 grep 全站，寫死 `https://` 接 host 的只剩這兩處（忘記密碼信本來就用 `{{ protocol }}://{{ domain }}`、家人專區的「傳給家人」用 `location.href`）；指出分享頁兩顆按鈕都帶網址、`assertIn` 證明不了兩顆都對，改成數到 2 次。兩個代理都指出原本「切回 Render 會變 `http://`」是推測，已改寫成上面那段。

## 本人驗收

- [ ] 本機預覽：登入 → 分享報告 → 產生連結，「可以複製這個網址傳給家人」是 `http://localhost:8001/shared/…`，按「複製連結」貼到網址列打得開
- [ ] 本機預覽：家人專區最下面的網址是 `http://localhost:8001/family`
- [ ] 部署後在正式站：兩處都是 `https://tingpal.tw/…`
