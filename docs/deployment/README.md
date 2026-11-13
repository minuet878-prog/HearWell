# 部署參考

[回文件首頁](../README.md)

- 正式環境與常用操作：見專案 [README](../../README.md)。
- 舊決策：[部署與環境](../decisions/deploy.md)。
- 本機私有 VPS 筆記已歸檔至本目錄的 `vpsdeploy.md`，延續不進版控；其他環境若沒有此檔，屬正常情況。

本目錄整理操作參考，不代表可以自行啟動、停止或修改服務；實際操作仍依專案工作指引及本人授權。

## Google 登入的環境變數（規格 #505）

放在 VPS 的 `.env`，改完重啟服務。三個都沒設時網站沒有 Google 按鈕，Google 的網址回 404，其他功能照常（本機開發不用設）。

| 變數 | 內容 |
|---|---|
| `GOOGLE_CLIENT_ID` | Google Auth Platform → 用戶端（Web application）的 Client ID |
| `GOOGLE_CLIENT_SECRET` | 同一個用戶端的 Client secret（只在建立時顯示一次） |
| `SITE_URL` | 網站的正式網址，結尾不加斜線，例如 `https://tingpal.tw`。有 `GOOGLE_CLIENT_ID` 卻沒設它，網站不會啟動 |

回呼網址由 `SITE_URL` 組成，不看請求的 Host 標頭。在 Google 後台「已授權的重新導向 URI」要填的就是：

- 正式站：`https://tingpal.tw/login/google/callback`
- 本機測試（另加）：`http://localhost:8001/login/google/callback`，這時 `SITE_URL=http://localhost:8001`

只要 `openid` 和 email 兩個範圍；「已授權的 JavaScript 來源」留空。
