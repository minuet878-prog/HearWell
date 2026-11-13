# Google 登入（規格 #505，#507–#514）

日期：2026-11-13。分支：`feat/505-google-sign-in`（整合分支，從 #492 的分支開出，#517 合併後已把 `main` 合進來）。規格：[#505](https://github.com/minuet878-prog/HearWell/issues/505)；票：#507 設計圖、#508 用 Google 註冊與登入、#509 同 email 不合併、#510 確認本人與沒有密碼的人刪帳號、#511 帳號設定新增／移除 Google、#512 LINE 內建瀏覽器不顯示 Google、#513 用 Google 保存訪客結果、#514 本人在 Google 後台的設定。

狀態：自動測試、自審、交叉審查（Codex，複核「沒有要修」）都已完成。**本人實際操作驗收還沒做**；第 40、41 條要等 #514 在 Google 後台建好用戶端。

## 本人決定

- 拷問：[login-grill-decisions.md](../planning/open-access/login-grill-decisions.md) Q1–Q18，ADR 0056、0057。
- 設計圖：#507 全部照建議（D1 甲、D2「使用 Google 帳戶登入／註冊／繼續」、D3「使用 Google 帳戶確認」、D4 圓角 14px、D5 登入方式自成一組）；字句 W1–W18 是草稿，驗收時審定。
- 交叉審查後（[#505 留言](https://github.com/minuet878-prog/HearWell/issues/505#issuecomment-6854477648)）：
  - 移除 Google 改成在確認本人頁輸入密碼的同一個請求裡就移除，不用 307 重送表單。
  - 取名稱頁的 email 欄位標題改成「帳號的電子郵件（來自 Google）」，不加說明列。
  - 註冊頁字句以設計圖 W2 為準（「使用 Google 帳戶註冊」「或填寫資料註冊」），不照規格第 2 條的「或用帳號密碼」。

## 實作時的做法（請本人知道）

- 同意書從第 5 版升到第 6 版，隱私權說明多一段「用 Google 登入時」。
- 有設 `GOOGLE_CLIENT_ID` 卻沒設 `SITE_URL` 時網站不啟動，避免回呼網址組錯。三個環境變數與回呼網址 `https://tingpal.tw/login/google/callback` 寫在 [部署說明](../deployment/README.md)。
- Google 不支援強制重新登入（沒有 `max_age`、`prompt=login`），確認本人與新增 Google 時帶 `prompt=select_account`，一定跳出選帳號畫面；拿著本人已解鎖手機的人擋不住（規格「其他說明」已寫）。查證寫在 [登入研究](../planning/open-access/login-research.md) 第 8 節。
- LINE 內建瀏覽器用 User-Agent 裡的 `Line/版本號` 認（跟 LINE 官方 LIFF 套件同一條規則），寫在登入研究第 9 節；2025 年後的 Android 實際字串沒有公開樣本，靠第 41 條確認。
- 在 LINE 裡，除了規格寫的登入頁、註冊頁，確認本人頁、刪除帳號頁和帳號設定的「新增 Google 登入」也改放「用 Safari／Chrome 打開」（同一個問題、同一種處理）。保存卡只拿掉 Google 按鈕、不放提示框（設計圖沒畫，而且訪客結果不會跟過去）。
- 「這個 email 已經有帳號」那一頁不寫出那個帳號的使用者名稱。
- 管理員與停用的帳號都不能用 Google 登入。
- 從保存卡用 Google 出發卻在 Google 取消或失敗時，回登入頁；訪客結果仍留在瀏覽器裡。
- 第 8 條：密碼註冊從一般註冊頁進來、同意後是回首頁，只有從「開始篩檢」進來才進推薦精靈；Google 註冊行為完全一樣，沒有另外改。
- 同一個 session 同時打兩個回呼時兩邊都可能去換 token，不修：Google 的授權碼只能換一次，最多一邊成功（登入研究有記）。
- 規格寫「不加 e2e 路線」，但保留了 `GuestSaveWithGoogleTest`：它攔在我們自己的出發網址、不連到 Google，是唯一能證明第 35、36 條「瀏覽器裡那份被清掉」的測試。
- 寫這個 e2e 的前兩版沒攔到轉址，測試瀏覽器帶著假的用戶端編號連到 Google 幾次，拿回錯誤頁；沒有送出任何個資，已改掉。
- Google 的 G 圖示是照設計圖的四色路徑內嵌，不是 Google 官方下載包的檔案。

### 代理擬的字句（設計圖沒有，驗收時審）

| 位置 | 字句 |
|---|---|
| Google 回傳的是管理員帳號 | 這個帳號請用帳號密碼登入。 |
| 用 Google 確認本人失敗、取消或沒回應 | 沒有完成 Google 確認，請再試一次。 |
| 新增 Google 登入失敗 | 沒有完成新增 Google 登入，請再試一次。 |

## 自動測試

提交 `a38d73b`，2026-11-13，本機：

| 項目 | 結果 |
|---|---|
| Django 測試 | 2350 項通過 |
| 端對端測試（`--parallel 4`） | 422 項通過 |
| 前端測試 | 540 項通過 |
| 前端建置、`ruff check`、`ruff format --check`、`makemigrations --check` | 通過 |

`SharedLayoutTest.test_icon_circle_stays_visible_on_hover`（問卷清單頁，不是這次改的）在 `--parallel 4` 時偶爾失敗：卡片背景有 0.15 秒變色動畫，讀色太早。單獨跑會過，這次整套也過了。

## 自審

`/mattpocock-skills:code-review`，基準 `origin/main`。Standards：沒有硬性違規，壞味道 10 項；Spec：找到移除 Google 用 GET 改資料、確認本人沒綁動作（5 分鐘內被跨站誘點就會移除）、竄改的回呼沒送錯誤監控、用密碼登入後取名稱的 Google 身分還在 session。都已修，壞味道修了 7 項（`GoogleNameForm` 的結構與 `sign_in_methods.py` 多一道管理員檢查保留）。

## 交叉審查

Codex，`/code-review`，基準 `main`。Standards 5 項、Spec 8 項，加上移除 Google 的 307 重送；處理方式見 [#505 留言](https://github.com/minuet878-prog/HearWell/issues/505#issuecomment-6854477648)。修正在 `8fd9739..a38d73b`，Codex 複核：沒有要修。

## 驗收條件

測試檔（都在 `screening/tests/`，E 除外）：GS＝`test_google_sign_in.py`、SE＝`test_google_same_email.py`、CI＝`test_confirm_identity.py`、SM＝`test_sign_in_methods_settings.py`、LB＝`test_line_in_app_browser.py`、SC＝`test_google_save_card.py`、E＝`e2e/main_flow.py`。

**按鈕與設定**

- [x] 1 沒設金鑰時沒有按鈕、Google 網址 404：GS；SC；SM
- [x] 2 Google 按鈕在表單上方、下面是分隔字（註冊頁照 W2）：GS
- [x] 3 LINE 裡沒有 Google、有「用 Safari／Chrome 打開」與那一句：LB

**第一次用 Google**

- [x] 4 出發帶 state、nonce、PKCE S256、只要 `openid email`、固定回呼網址：GS
- [x] 5 取名稱頁、資料庫沒有新帳號、email 標題「帳號的電子郵件（來自 Google）」：GS
- [x] 6 名稱重複的錯誤同密碼註冊；建帳號、沒有可用密碼、註冊時用的登入方式：GS
- [x] 7 10 分鐘後送出不建帳號：GS
- [x] 8 同意後去處跟密碼註冊相同（見上方說明）；不同意被登出、帳號還在：GS
- [x] 9 email 沒驗證不建帳號：GS

**再次登入**

- [x] 10 同一個帳號、email 改了也不變：GS
- [x] 11 管理員不登入：GS

**同 email 不合併**

- [x] 12 不登入、不加登入方式、「這個 email 已經有帳號」：SE
- [x] 13 「不是我的，建立新帳號」另建、原帳號不變：SE
- [x] 14 用帳號密碼登入後回到登入方式那一塊：SE；SM

**回呼安全**

- [x] 15 state 不符、沒有、用過、非 ASCII，帶 `error` 也先查 state：GS
- [x] 16 超過 10 分鐘：GS
- [x] 17 nonce（含非 ASCII）、aud、iss、過期：GS
- [x] 18 重放：GS（同時到達的兩個請求見上方說明）
- [x] 19 在 Google 取消：GS
- [x] 20 Google 沒回應、回錯誤（含 HTTP 200 的錯誤內容），送錯誤監控：GS
- [x] 21 Host 標頭被改，回呼網址不變：GS

**帳號設定：登入方式**

- [x] 22 登入方式那一塊：SM
- [x] 23 新增前先確認本人、密碼錯誤的訊息：SM
- [x] 24 新增後用 Google 進同一個帳號、看得到原有紀錄、email 不變：SM
- [x] 25 Google 已用在別的帳號（含兩邊同時新增）：SM
- [x] 26 移除（啟用 CSRF 檢查）、之後那個 Google 變成沒見過：SM
- [x] 27 只有 Google 時沒有移除、直接送出也被拒：SM
- [x] 28 管理員沒有那一塊、請求被拒：SM
- [x] 29 確認超過 5 分鐘要再確認：SM

**確認本人與刪帳號**

- [x] 30 沒有密碼時用 Google 確認後才能刪（含還沒同意新版的人）：CI
- [x] 31 別的 Google 不能確認、不能拿去新增或移除：CI；SM
- [x] 32 有密碼照舊輸入密碼、密碼錯帳號仍在：CI
- [x] 33 登入方式與健康資料全刪或全不刪：GS
- [x] 34 匯出有登入方式、沒有權杖：GS

**接上訪客結果保存**

- [x] 35 保存卡用 Google 註冊、同意後直接保存、瀏覽器裡那份被清掉：SC；E `GuestSaveWithGoogleTest`
- [x] 36 既有帳號先問、寫出名稱、「不要」就清掉：SC；E `GuestSaveWithGoogleTest`
- [x] 37 保存次數加在註冊方式那一格：SC

**同意書與隱私權說明**

- [x] 38 隱私權說明的 Google 段落、同意書第 6 版：GS
- [x] 39 同意舊版的人被請再同意：GS

**真機（本人驗收）**

- [ ] 40 正式站、iPhone Safari 第一次用 Google 登入，Google 畫面顯示「聽伴」與 logo（等 #514）
- [ ] 41 從 LINE 打開正式站：沒有 Google 按鈕；用 Safari 打開後登入成功；記下 Safari 看不看得到 LINE 裡的訪客結果、Google 在 LINE 裡是不是真的會擋（等 #514）

## 本人驗收

（待填）
