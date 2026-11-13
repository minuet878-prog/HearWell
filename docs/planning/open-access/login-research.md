# Google 登入、LINE 登入：研究

開放階段第 2、3 項（`plan.md`）拷問前的研究。所有來源查詢日期都是 2026-11-13，連結列在文末〔代號〕。

**摘要**
- 建議**自己寫一個很薄的 OpenID Connect 用戶端**（只服務 Google、LINE 兩家，用 Python 標準函式庫，不加新套件），Authlib 當備案；不建議 django-allauth：我們的規則（不存大頭貼、同 email 不合併、先同意書）幾乎都要改掉它的預設。
- 最大的風險：**Google 很可能在 LINE 內建瀏覽器裡被擋**（`disallowed_useragent`），而跳到 Safari／Chrome 後，第 1 項的訪客作答可能帶不過去（瀏覽器儲存空間不共用，LINE 沒有官方說明，要實機確認）。
- 第二個風險：**LINE 的使用者代號依「提供者（Provider）」而不同**，LINE 後台的 Provider 建好就不能換，換了所有 LINE 帳號都登不進來。
- 費用：兩家官方文件都沒寫收費，也沒有明文寫「免費」；用量上限 Google 依應用程式信譽調整、LINE 不公開。

名詞：**OIDC**（OpenID Connect）＝建在 OAuth 2.0 上的登入標準，對方回傳一張「ID token」（簽過名的身分證明，裡面的 `sub` 是這個人在對方那邊的代號）。

---

## 1. 現成套件 vs 自己實作

現況：`User`（AbstractUser＋`birth_year`）、`Consent`、自訂的 `login.html`／`register.html`（Django `LoginView`＋自己的 `register`）、`ConsentRequiredMiddleware` 用 URL 名稱白名單（`OPEN_PAGES`）擋未同意的人。`requirements.txt` 沒有 `requests`、`cryptography`、JWT 套件。

| 比較項目 | django-allauth 65.22（一般模式） | allauth headless | Authlib 1.9.5（Django client） | mozilla-django-oidc 5.0.2 | 自己寫 |
|---|---|---|---|---|---|
| 新增依賴 | allauth＋`requests`、`oauthlib`、`pyjwt[crypto]`〔A1〕 | 同左 | `authlib`、`cryptography`、`joserfc`〔A5〕，Django client 另需 `requests` | `requests`、`pyjwt`、`cryptography`〔M1〕 | 無（`urllib`、`hmac`、`secrets`、`hashlib` 都是標準庫） |
| 新資料表 | 要裝 `allauth.account`（必裝）＋`allauth.socialaccount`：EmailAddress、SocialAccount、SocialToken 等〔A2〕 | 同左 | 無 | 無（只認 email 對帳號，見下） | 一張「登入方式」表（user、provider、sub） |
| 只拿最少資料 | `SOCIALACCOUNT_STORE_TOKENS` 預設 False，不存 token〔A3〕；但 `SocialAccount.extra_data` 會存對方回傳的整包資料（Google 含 `picture`），要自己寫 adapter 清掉〔A4〕 | 同左 | 不存 token（要存得自己寫 model）〔A6〕；拿到什麼由我們決定存不存 | `OIDC_STORE_ACCESS_TOKEN` 預設 False〔M2〕 | 完全由我們決定 |
| 跟現有登入頁、`User`、`Consent` | 要換 `AUTHENTICATION_BACKENDS`、加 `AccountMiddleware`〔A2〕；會多出 `/accounts/login/` 等自己的頁面；email 撞到既有帳號時預設跳它的註冊表單〔A3〕，要改成「請用密碼登入再連結」 | 給前後端分離用（`/_allauth/` API、`HEADLESS_ONLY`）〔A7〕；我們登入註冊不 React 化（AGENTS.md），用不到 | 不碰現有登入頁，只多兩個 view | **只支援一家**（單一組 `OIDC_OP_*` 設定）〔M2〕，不適用 | 不碰現有登入頁 |
| LINE 支援 | 有內建 LINE provider，但**沒申請 email 時它會拿 access token 去呼叫 `/v2/profile`**〔A8〕，也就是一定要 `profile` 權限（名稱＋大頭貼），做不到「只要 `openid`」；改用它的通用 OIDC provider 可能可以，未實測 | 同左 | 用 discovery 自動設定；但 LINE 網頁登入的 ID token 是 **HS256（用 channel secret 簽）**〔L3〕，而 LINE 的 discovery 文件只列 ES256〔L5〕，Authlib 的 `parse_id_token` 依 discovery 的演算法與金鑰組驗證〔A6〕→ 很可能驗不過，要自己處理 | — | 直接呼叫 LINE 的驗證端點（見第 2 節），不用處理簽章 |
| PKCE、nonce | PKCE 預設關（`pkce_enabled_default = False`，要設 `OAUTH_PKCE_ENABLED`）〔A9〕；Google／LINE provider 原始碼裡沒看到 nonce〔A8〕 | 同左 | nonce 有送就一定比對〔A6〕；PKCE 設 `code_challenge_method='S256'`〔A6〕 | nonce 預設開、PKCE 預設關〔M2〕 | 自己做，各 10 行左右 |
| 維護成本 | 版本更新頻繁（65.x），升級要看 changelog；但很多人在用、問題有人回報 | 同左 | 中等；套件範圍大（含伺服器端），我們只用一小塊 | — | 約 150–250 行我們自己負責；兩家端點固定，不需要通用化；**安全全靠我們的測試和交叉審查** |
| 測試（不連真的對方） | 要 mock 它內部的 HTTP 呼叫（token、profile）；它的測試工具不是公開 API | 同左 | patch `authorize_access_token` 會跳過套件自己的驗證，要測 state／nonce 被竄改得更深入 mock | — | 只有一個「換 token」的接縫好 patch；LINE 的假 ID token 可以用測試用 secret 真的簽 HS256，Google 的可以直接組 |

**建議：自己寫**，理由：
1. 兩家官方文件讓這件事變得很小：Google 說「直接從 token 端點經 HTTPS、用 client secret 換到的 ID token」可以不驗簽章〔G1〕；LINE 有一個驗證端點替我們驗簽章、iss、aud、exp、nonce〔L4〕。剩下的 state、PKCE、nonce 都是幾行標準庫。
2. 我們的規則（只存 provider＋sub、同 email 不合併不登入、同意書前不存健康資料、訪客認領、帳號設定裡連結／解除）是帳號邏輯，不管用哪個套件都要自己寫；allauth 的價值主要在帳號邏輯，偏偏是我們要改掉的部分。
3. 不加資料表以外的東西，`ConsentRequiredMiddleware` 只要把兩個回呼網址加進 `OPEN_PAGES`。

**代價**：協定層的錯誤沒有套件替我們擋，所以每一條安全檢查都要有「被竄改就失敗」的測試，且這張票碰權限，依 AGENTS.md 必做交叉審查。備案：如果本人比較想用套件，選 Authlib（Google 用它、LINE 的 ID token 改走 LINE 驗證端點）。

---

## 2. 安全項目

| 項目 | 是什麼 | Google | LINE | 自己寫怎麼做 |
|---|---|---|---|---|
| `state` | 隨機字串，出發前存 session，回來時比對，防偽造回呼 | 官方「強烈建議」〔G1〕 | 必填〔L1〕 | `secrets.token_urlsafe`，存 session；回呼時 **pop**（用一次就刪）、10 分鐘過期 |
| `nonce` | 隨機字串，對方會原樣放進 ID token，防 ID token 被拿去重放 | 參數表標「Required」〔G1〕 | 選填，會放進 ID token〔L1〕 | 跟 state 一起存、一起 pop；Google 自己比對 `nonce` claim，LINE 交給驗證端點的 `nonce` 參數〔L4〕 |
| PKCE | 出發前產生 `code_verifier`，只送它的雜湊；換 token 時才送原值，防授權碼被攔截 | discovery 文件列出 `S256`〔G1〕；網頁伺服器流程的文件沒提，未找到官方說明是否必要 | 選填、只支援 `S256`、官方建議實作〔L2〕 | 兩家都送 `S256`；verifier 存 session |
| 回呼網址完全比對 | 對方只把人送回後台登記過的網址 | 必須完全相符，含大小寫與結尾斜線；必須 HTTPS（localhost 例外）；不能有萬用字元、`#`〔G2〕 | 完全相符，或登記的網址後面多加查詢參數；可登記多個〔L6〕；換 token 時的 `redirect_uri` 要跟出發時相同〔L4〕 | 用固定字串組回呼網址（不用 `request.build_absolute_uri` 拼 Host 標頭），`tingpal.tw` 與 `www` 只登記實際用的那個 |
| ID token 驗證 | 確認是對方發給「我們」、沒過期 | 驗簽章（jwks）、`iss` 是 `https://accounts.google.com` 或 `accounts.google.com`、`aud` 等於 client ID、`exp` 未過；直接從 token 端點拿的可以不驗簽章〔G1〕 | 網頁登入是 HS256、用 channel secret 驗〔L3〕；或呼叫 `POST /oauth2/v2.1/verify`，它會回「Issuer／expired／Audience／Nonce 不符」等錯誤〔L4〕 | Google：解開 payload，比對 iss、aud、exp、nonce；LINE：呼叫驗證端點，帶 `client_id`、`nonce` |
| 認人用什麼 | — | 用 `sub`（不重複、不重用）；**不要用 email 當識別**（會變、可能不唯一）〔G1〕 | 用 user ID（`sub`），不會變〔L7〕；但**不同 Provider 拿到的 ID 不同**〔L8〕 | 「登入方式」表以 (provider, sub) 唯一 |

**重放舊回呼怎麼擋**：三層。(1) state 用一次就從 session 刪掉，同一個網址再打一次就找不到 state 而拒絕；(2) 授權碼依 OAuth 2.0 標準只能用一次、且要短效〔R1〕，對方會拒絕；(3) nonce 綁在這次的 session，舊 ID token 對不上。另外 Django `login()` 會換 session 代號，state 要在登入前就 pop 掉。

套件對照：allauth 的 state 存在 session、用一次就刪、10 分鐘過期、最多留 10 組〔A10〕；PKCE 要手動開；nonce 未看到。Authlib 有送 nonce 就一定驗〔A6〕。

---

## 3. LINE 內建瀏覽器

| 問題 | 查到的 | 來源 |
|---|---|---|
| localStorage／cookie 跟 Safari／Chrome 共不共用 | **未找到 LINE 官方說明**（LINE 的瀏覽器比較文件只講 LIFF 功能差異〔L9〕）。一般認知：iOS 的 App 內網頁元件（WKWebView）資料跟 Safari 分開，Android 的 WebView 也是每個 App 各自一份；**要實機確認** | 未找到官方來源 |
| 在 LINE 內建瀏覽器走 LINE Login | 手機已登入 LINE 時，從「LINE 內建瀏覽器」打開授權網址會**自動登入**，不用輸入帳密；私密瀏覽可能失敗；電腦版 LINE 不支援 | 〔L1〕 |
| Google 擋不擋 | Google 政策禁止在「內嵌網頁元件」（Android WebView、iOS WKWebView）裡走 OAuth，會出現 `disallowed_useragent`；官方建議網站方「請對方 App 改用系統瀏覽器開連結」。LINE 內建瀏覽器是哪一種元件，LINE 沒有官方說明 → **很可能被擋，要實機確認** | 〔G3〕〔G2〕 |
| 「用外部瀏覽器打開」參數 | 網址加 `?openExternalBrowser=1`：從 LINE 裡打開時改用外部瀏覽器（iOS、Android 都支援，LIFF 除外）；`openInAppBrowser=0` 在 Android 改用 Chrome Custom Tab | 〔L10〕 |
| 加到主畫面 | LINE 沒有官方說明。iPhone 只能在 Safari 用「分享 → 加入主畫面」〔AP1〕。網站已有 `add_to_home` 頁，可在 LINE 內建瀏覽器裡顯示「用 Safari 打開」連結（`/add_to_home?openExternalBrowser=1`） | 〔AP1〕〔L10〕 |

**對第 1 項訪客認領的影響**：
- 全程在 LINE 內建瀏覽器裡：訪客作答存在 LINE 瀏覽器自己的 localStorage → 用 LINE 註冊（自動登入、回到同一個瀏覽器）→ 同意 → 送出。**認領得到**（理論上，要實機驗）。
- 在 LINE 裡做完、按 Google：可能被擋；若改用 `openExternalBrowser=1` 跳到 Safari／Chrome，**訪客作答留在 LINE 那邊，認領不到**。
- 所以「在 LINE 內建瀏覽器裡要不要顯示 Google 按鈕」需要本人決定（見最後一節）。辨認 LINE 內建瀏覽器只能看 User-Agent 字串，LINE 未公開官方格式（未找到官方來源）。

---

## 4. Google OAuth 同意畫面

- **測試中**：最多 100 位測試使用者；一般而言非測試使用者不能授權、授權 7 天後失效。**例外**：只要求 `openid`、email、profile 這幾個基本範圍的應用程式，不在名單上的人也能登入、不會看到警告、授權也不會 7 天到期；多要任何其他範圍例外就失效〔G4〕。
- **已發布（In production）**：任何 Google 帳號都能用，按「Publish app」切換〔G4〕。
- **要不要送驗證**：只用非敏感範圍不需要完整的應用程式驗證；但想在同意畫面**顯示 App 名稱和 logo**，且是「外部、已發布」就要做「品牌驗證」〔G5〕〔G6〕。未做品牌驗證時畫面顯示什麼，未找到官方說明。
- **品牌驗證要準備**〔G6〕：
  - 在 Google Search Console 驗證 `tingpal.tw` 的擁有權（用專案的擁有者或編輯者帳號）。
  - 首頁要公開、不是只有登入頁、說明 App 做什麼。
  - 隱私權說明要放在同網域，首頁和同意畫面連到同一份，寫清楚怎麼取得、使用、儲存、分享 Google 使用者資料。
  - 自動審查通常幾分鐘，轉人工 2–3 個工作天；驗證結果 7 天內要發布。
- **其他注意**〔G7〕：OAuth 用戶端**閒置 6 個月會被自動刪除**（建議接近上線才建）；client secret **只在建立時能看一次**；改回呼網址要 5 分鐘到幾小時才生效。

---

## 5. LINE Login 頻道

- **開發中（Developing）**：只有在頻道裡有 Admin 或 Tester 角色的人能登入。**已發布（Published）**：所有人可用；**改成已發布後不能改回**〔L11〕。
- **scope 與拿到的資料**〔L1〕〔L3〕：
  - `openid`：只有 ID token，內含 user ID（`sub`），**沒有名稱、大頭貼、email** → 可以做到「連名稱都不拿」。
  - `profile openid`：多了顯示名稱（`name`）與大頭貼網址（`picture`）。
  - `email` 要另外申請，不申請就不能要。
- **使用者代號**：同一個 LINE 使用者在不同 Provider 下的 user ID 不同〔L8〕；LINE 的 discovery 文件也標 `pairwise`〔L5〕。→ Provider 一旦建立就不要換。
- LINE 建議登出時撤銷 access token〔L7〕；我們登入完就不再用 token，可在拿到 ID 後立刻撤銷（見最後一節）。

---

## 6. 費用與用量限制

| | 費用 | 用量限制 |
|---|---|---|
| Google | **未找到官方明文**寫免費或收費（OAuth 說明文件沒有任何計費內容） | 有「新使用者授權速率」上限，依應用程式歷史、開發者信譽、風險而定；超過時使用者看到 `Error 403: rate_limit_exceeded`；可在同意畫面頁看目前用量、申請提高（約 5 個工作天回覆）〔G8〕 |
| LINE | **未找到官方明文**；LINE Login 文件與 API 參考都沒提收費〔L11〕〔L4〕 | 門檻**不公開**；超過回 HTTP 429 暫時限制；官方要求不要大量請求（含壓力測試）〔L4〕 |

本人「兩者登入都免費」的理解：官方文件沒有寫收費，但也找不到「免費」的明文。以我們的規模（還沒有真實使用者）碰不到上限。

---

## 7. 本人要在兩家後台填的值

依建議的「自己寫」，路徑由我們定（跟現有 `login`、`register` 一樣不加結尾斜線）。若改用 allauth，路徑會變成 `/accounts/google/login/callback/`、`/accounts/line/login/callback/`〔A11〕。

**Google Cloud（Google Auth Platform）**
- 品牌（Branding）：App 名稱「聽伴」、使用者支援 email、首頁 `https://tingpal.tw/`、隱私權政策 `https://tingpal.tw/privacy`、授權網域 `tingpal.tw`、開發者聯絡 email；logo 選填（填了就要品牌驗證）。
- 目標對象（Audience）：External，設定好後按 Publish app。
- 資料存取（Data access）範圍：`openid`、`.../auth/userinfo.email`（不勾 profile；Google 規定 `openid` 之外至少要 profile 或 email 其中一個〔G1〕，選 email 是為了做「同 email 不合併」的提示，見最後一節）。
- 用戶端（Clients）：類型 Web application；已授權的 JavaScript 來源**留空**（伺服器端流程不需要）；已授權的重新導向 URI：`https://tingpal.tw/login/google/callback`（本機測試另加 `http://localhost:8001/login/google/callback`，Google 允許 localhost 用 http〔G2〕）。
- 取得：Client ID、Client secret（只顯示一次）→ VPS `.env` 的 `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`（名稱待規格定）。

**LINE Developers**〔L11〕
- Provider：例如「聽伴」。**之後不要換**（換了所有 LINE 使用者代號都變）。
- 建立頻道：類型 LINE Login；服務地區 Taiwan；公司／擁有者所在地 Taiwan；頻道名稱（不能含「LINE」字樣）；頻道說明；App types 勾 **Web app**；email（收重要通知）；同意 LINE Developers Agreement；隱私權政策網址選填（建議填 `https://tingpal.tw/privacy`）。
- LINE Login 分頁 → Callback URL：`https://tingpal.tw/login/line/callback`（本機 http 能不能登記：未找到官方來源，驗收用正式站）。
- OpenID Connect 的「Email address permission」：**不申請**。
- 取得：Channel ID、Channel secret → `.env` 的 `LINE_CHANNEL_ID`、`LINE_CHANNEL_SECRET`。
- 驗收時先把本人加為 Tester 測試，確定後再切「已發布」（不能改回）。

---

## 要本人決定的事

1. **做法**
   - A. 自己寫（建議）：不加套件、不加多餘的表；代價是安全檢查全靠測試和交叉審查。
   - B. Authlib：協定交給套件；代價是多 4–5 個依賴，LINE 的 ID token 還是要自己改走驗證端點。
   - C. django-allauth：最多人用；代價是多一批資料表和頁面，大頭貼、email 撞號、LINE 只要 `openid` 都要改它的預設。
2. **Google 要 `openid email` 還是 `openid profile`**
   - email（建議）：做得到 `plan.md` 的「同 email 不合併、請他用密碼登入再連結」；代價是拿到 email。要不要寫進 `User.email`？寫了，「忘記密碼」寄信之後用得到；不寫，最少資料。
   - profile：拿到名稱和大頭貼網址（要丟掉），做不到 email 撞號提示。
3. **LINE 要 `openid` 還是 `openid profile`**
   - `openid`（建議，符合最少資料）：畫面上不知道怎麼稱呼他，要另外問。
   - `profile`：拿得到 LINE 名稱可以稱呼，但同時會拿到大頭貼網址，要自己丟掉。
4. **LINE 內建瀏覽器裡的 Google 按鈕**
   - 隱藏 Google，只顯示 LINE 和密碼，旁邊放「用 Safari／Chrome 打開」（`openExternalBrowser=1`）；代價：跳出去後訪客作答帶不過去，要說清楚。
   - 照常顯示、被擋再說；代價：長輩看到 Google 的錯誤頁，很可能就放棄。
   - 先實機測 LINE 內建瀏覽器到底會不會被擋，再決定（建議在拷問前由本人用 iPhone、Android 各試一次）。
5. **Google 品牌驗證**：做（同意畫面顯示「聽伴」，長輩比較敢按；要先在 Search Console 驗證網域）或不做（少一步，但畫面上的名稱顯示方式未確認）。
6. **LINE access token 要不要拿到 ID 後立刻撤銷**：撤銷（LINE 建議，多一次呼叫）或不管（反正不存，token 自己會過期）。
7. **Google 用戶端何時建立**：閒置 6 個月會被刪，建議等實作到要驗收時才建。

---

## 來源（查詢日期皆 2026-11-13）

- 〔A1〕django-allauth PyPI：https://pypi.org/project/django-allauth/
- 〔A2〕allauth 安裝：https://docs.allauth.org/en/latest/installation/quickstart.html
- 〔A3〕allauth socialaccount 設定：https://docs.allauth.org/en/latest/socialaccount/configuration.html
- 〔A4〕allauth Google provider 原始碼：https://codeberg.org/allauth/django-allauth/src/branch/main/allauth/socialaccount/providers/google/
- 〔A5〕Authlib PyPI：https://pypi.org/project/Authlib/
- 〔A6〕Authlib Django client：https://docs.authlib.org/en/stable/oauth2/client/web/django.html ；`parse_id_token`：https://github.com/authlib/authlib/blob/main/authlib/integrations/base_client/sync_openid.py
- 〔A7〕allauth headless：https://docs.allauth.org/en/latest/headless/configuration.html
- 〔A8〕allauth LINE provider 原始碼：https://codeberg.org/allauth/django-allauth/src/branch/main/allauth/socialaccount/providers/line/views.py
- 〔A9〕allauth OAuth2 provider 原始碼：https://codeberg.org/allauth/django-allauth/src/branch/main/allauth/socialaccount/providers/oauth2/provider.py
- 〔A10〕allauth statekit 原始碼：https://codeberg.org/allauth/django-allauth/src/branch/main/allauth/socialaccount/internal/statekit.py
- 〔A11〕allauth Google provider 文件：https://docs.allauth.org/en/latest/socialaccount/providers/google.html
- 〔M1〕mozilla-django-oidc PyPI：https://pypi.org/project/mozilla-django-oidc/ ；〔M2〕設定：https://mozilla-django-oidc.readthedocs.io/en/stable/settings.html
- 〔G1〕Google OpenID Connect：https://developers.google.com/identity/openid-connect/openid-connect
- 〔G2〕Google 網頁伺服器 OAuth：https://developers.google.com/identity/protocols/oauth2/web-server
- 〔G3〕Google 內嵌網頁元件政策（2021）：https://developers.googleblog.com/en/upcoming-security-changes-to-googles-oauth-20-authorization-endpoint-in-embedded-webviews/
- 〔G4〕Google 目標對象與發布狀態：https://support.google.com/cloud/answer/15549945
- 〔G5〕Google 驗證需求：https://support.google.com/cloud/answer/13463073
- 〔G6〕Google 品牌驗證：https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification
- 〔G7〕Google 管理 OAuth 用戶端：https://support.google.com/cloud/answer/15549257
- 〔G8〕Google OAuth 速率限制：https://support.google.com/cloud/answer/9028764
- 〔L1〕LINE Login 網頁整合：https://developers.line.biz/en/docs/line-login/integrate-line-login/
- 〔L2〕LINE PKCE：https://developers.line.biz/en/docs/line-login/integrate-pkce/
- 〔L3〕LINE 驗證 ID token：https://developers.line.biz/en/docs/line-login/verify-id-token/
- 〔L4〕LINE Login v2.1 API 參考（verify、token、速率限制）：https://developers.line.biz/en/reference/line-login/
- 〔L5〕LINE discovery 文件：https://access.line.me/.well-known/openid-configuration
- 〔L6〕LINE 安全檢查清單：https://developers.line.biz/en/docs/line-login/security-checklist/
- 〔L7〕LINE 管理使用者：https://developers.line.biz/en/docs/line-login/managing-users/
- 〔L8〕LINE 使用者 ID 依 Provider 不同：https://developers.line.biz/en/docs/messaging-api/getting-user-ids/
- 〔L9〕LIFF 瀏覽器與 LINE 內建瀏覽器差異：https://developers.line.biz/en/docs/liff/differences-between-liff-browser-and-line-in-app-browser/
- 〔L10〕LINE URL scheme（外部瀏覽器參數）：https://developers.line.biz/en/docs/line-login/using-line-url-scheme/
- 〔L11〕LINE Login 開始使用（建立頻道、發布狀態）：https://developers.line.biz/en/docs/line-login/getting-started/
- 〔R1〕OAuth 2.0（RFC 6749）§4.1.2 授權碼只能用一次：https://www.rfc-editor.org/rfc/rfc6749#section-4.1.2
- 〔AP1〕Apple iPhone 使用手冊（Safari 加入主畫面）：https://support.apple.com/guide/iphone/bookmark-favorite-webpages-iph42ab2f3a7/ios
