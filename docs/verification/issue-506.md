# LINE 登入（規格 #506，#539–#544）

日期：2026-11-14。分支：`feat/506-line-sign-in`（整合分支，從 #545 合併後的 `main` 開出，途中帶進了 `main` 的 #519）。規格：[#506](https://github.com/minuet878-prog/HearWell/issues/506)；票：#539 設計圖、#540 用 LINE 註冊與登入、#541 帳號設定新增／移除 LINE、#542 確認本人任選一家與只有 LINE 的人刪帳號、#543 用 LINE 保存訪客結果、#544 本人在 LINE Developers 的設定。

狀態：自動測試、自審、交叉審查（Codex，複核「沒有要修」）、本人在本機實際操作驗收都已通過。第 28–30 條要部署到正式站後用真機做，跟著 #544。

## 本人決定

- 拷問：[login-grill-decisions.md](../planning/open-access/login-grill-decisions.md)，ADR 0056、0057。
- 設計圖 #539（2026-11-14，全部照建議）：D1 LINE 按鈕不用官方綠底白字（白字對比 2.3:1，字放大會斷行、違反 LINE 規範），改成跟 Google 同一款白底灰框、左邊 LINE 官方圖示；D2「使用 LINE 帳號登入／註冊／繼續／確認」；D3 在 LINE 裡「用 Safari／Chrome 打開」灰框搬到表單下面；D4 帳號設定三列照帳號密碼、Google、LINE。字句 W1–W11 是草稿，驗收時審定。
- 同意書升第 8 版：正式站已經是 Google 的第 7 版，不是同時上線，照拷問 Q12 不併成一版。
- 用 LINE 確認本人不強制重新登入（不帶 `prompt=login`、`disable_auto_login`），跟 Google 同樣的強度，長輩不用記 LINE 密碼；拿著本人已解鎖手機的人擋不住。寫在[登入研究](../planning/open-access/login-research.md)第 10 節。
- ADR 0007 補一句：第三方登入標誌照各家規定的顏色，只用在標誌本身（自審時問）。
- LINE 圖示用官方檔案：本人 2026-11-14 從 LINE Developers 下載按鈕素材（下載即同意 LINE 的使用規範），用其中只有圖示的 `images/DeskTop/2x/44dp/btn_base.png`，一個像素都沒改（交叉審查 Spec 2）。
- 交叉審查處理方式：[#506 留言](https://github.com/minuet878-prog/HearWell/issues/506#issuecomment-6864789776)。

## 實作時的做法（請本人知道）

- 對外的出口統一成 `oidc.post_to_provider`，Google、LINE 的換 token、驗證、作廢權杖都走它；測試只換這一個函式。
- LINE 的身分證明交給 LINE 的驗證端點驗，我們再查一次 iss、aud、exp、nonce；拿到代號後立刻請 LINE 作廢存取權杖，作廢失敗只送錯誤監控、照樣登入。
- 只採用 Google 的 email；LINE 回應就算帶了 email 也不用（交叉審查 Spec 5）。LINE 取名稱頁的 email 欄位選填、上限 254 字。
- 回呼帶回錯誤時，只有使用者自己按取消才寫「沒有完成…」，其他錯誤寫「暫時沒有回應…」；Google 一起改（自審，#505 驗收 20、#506 驗收 14）。
- Google 的取消、沒回應兩句改成「或用其他方式登入」（W8）。
- 沒有密碼的人移除登入方式：從 LINE／Google 確認回來就直接移除，不再多一頁按一次（跟有密碼時輸入密碼就移除一致）。移除前鎖住帳號再檢查，兩個瀏覽器同時移除也一定留下一種；金鑰關掉的那一家不算備援（交叉審查 Standards 1）。
- 新增、移除登入方式的回呼，寫入前重查有沒有同意新版；為了刪帳號確認本人照舊可以（交叉審查 Standards 2）。
- 回呼的錯誤原文不寫進紀錄（交叉審查 Standards 3）。
- 各家的字句集中在 `screening/views/provider_words.py`；「在 LINE 裡不提供 Google」只寫在 `views/common.works_here`；按鈕的 class 改成中性的 `.btn-provider`。
- 規格寫「不加 e2e 路線」，但保留了 `GuestSaveWithLineTest`（和 #505 的 `GuestSaveWithGoogleTest` 共用 `GuestSavesFromTheCard`）：它攔在我們自己的出發網址、不連到 LINE，是唯一能證明第 23、24 條「瀏覽器裡那份被清掉」的測試。
- 已知限制，不修（交叉審查已記）：
  - 用 LINE 註冊、後來加了 Google 又移除 LINE 的人，保存會算到帳號密碼那一格（註冊時用的那一列沒了就查不到）。
  - 同一個 session 同時打兩個回呼時兩邊都可能去換 token；LINE 的授權碼只能換一次，最多一邊成功。
- `PRIVACY_UPDATED_ON` 還是 2026-11-14（第 7 版的日期）。**合併當天要改成第 8 版上線那天**，再合併。

### 代理擬的字句（設計圖沒有，驗收時審）

| 位置 | 字句 |
|---|---|
| LINE 取名稱頁等太久 | 等太久了，請再按一次「使用 LINE 帳號登入」。 |
| 用 LINE 確認本人失敗、取消或沒回應 | 沒有完成 LINE 確認，請再試一次。 |
| 新增 LINE 登入失敗 | 沒有完成新增 LINE 登入，請再試一次。 |
| 刪帳號頁、有 LINE 與 Google、沒有密碼 | 您的帳號沒有密碼，請用 LINE 或 Google 確認是本人。 |
| 同意頁重點多一行 | 用 LINE 登入時，只拿 LINE 給您的代號，不拿名稱、大頭貼、email 和好友名單。 |
| 隱私權說明 | 「用 LINE 登入時」整段 |

句型不一致、驗收時一起決定：LINE 已用在別的帳號是「這個 LINE 帳號已經用在另一個帳號。」（W7），Google 現有的是「這個 Google 帳號已經用在另一個聽伴帳號，所以沒有新增。」

## 自動測試

提交 `d062a8a`（驗收時的修正），2026-11-14，本機：

| 項目 | 結果 |
|---|---|
| Django 測試 | 2585 項通過 |
| 端對端測試（`--parallel 4`） | 427 項通過 |
| 前端測試 | 557 項通過 |
| 前端建置、`ruff check`、`ruff format --check`、`makemigrations --check` | 通過 |

## 自審

`/mattpocock-skills:code-review`，基準 `main`。Standards：沒有硬性違規；壞味道（13 個依登入方式分的對照表、「在 LINE 裡不提供 Google」寫了四份、`.btn-google` 名稱、作廢權杖的紀錄寫死 LINE）都已整理。Spec：驗收 1–27 都找得到測試；修了 LINE 回錯誤一律當取消（驗收 14），日期註解改正。ADR 0007 的品牌色由本人決定補一句。

## 交叉審查

Codex，`/code-review`，基準 `main`。要修 9 項（Standards 4、Spec 5 項），不修 5 項附理由；處理方式見 [#506 留言](https://github.com/minuet878-prog/HearWell/issues/506#issuecomment-6864789776)。修正在 `1626a42..ba1726d`、LINE 官方圖示 `67efc86`；第一次複核還有兩項（並行移除測試沒走到檢查、資料庫衝突的處理範圍太寬），修在 `b2c69b9`、`5ef04b3`。第二次複核：沒有要修。

## 驗收條件

測試檔（都在 `screening/tests/`，E 除外）：LS＝`test_line_sign_in.py`、LM＝`test_line_sign_in_methods.py`、LC＝`test_line_confirm_identity.py`、LV＝`test_line_save_card.py`、E＝`e2e/main_flow.py`。

**按鈕與設定**

- [x] 1 沒設金鑰時沒有 LINE、LINE 網址 404、Google 與帳號密碼照常：LS；LV；LM
- [x] 2 由上往下 LINE、Google、「或用帳號密碼」；按鈕是白底灰框加 LINE 官方圖示（比對檔案雜湊值）：LS
- [x] 3 LINE 裡有 LINE、沒有 Google，「用 Safari／Chrome 打開」在表單下面：LS

**第一次用 LINE**

- [x] 4 出發帶 state、nonce、PKCE S256、只要 `openid`、固定回呼網址：LS
- [x] 5 取名稱頁三個欄位、W5、W6、資料庫沒有新帳號；LINE 回的 email 不採用：LS
- [x] 6 不填 email 建帳號、沒有可用密碼、註冊時用的 LINE、到同意書：LS
- [x] 7 email 格式不對同密碼註冊的錯誤；254 字上限；正確的存成帳號 email：LS
- [x] 8 email 跟既有帳號相同照樣建立：LS
- [x] 9 作廢權杖；作廢失敗（含空白 4xx）照樣登入並記錯誤；有存取權杖沒身分權杖也作廢：LS

**再次登入與安全**

- [x] 10 同一個代號回到同一個帳號：LS
- [x] 11 state 不符、沒有、用過、超過 10 分鐘都拒絕且不呼叫 LINE（同時到達的兩個請求見上方說明）：LS
- [x] 12 驗證端點拒絕，或回傳的 nonce、aud、iss 不符、過期：LS
- [x] 13 在 LINE 按取消：LS
- [x] 14 LINE 沒回應或回錯誤；錯誤原文不進紀錄：LS

**帳號設定、確認本人、刪帳號**

- [x] 15 三列登入方式：LM
- [x] 16 確認本人後新增 LINE、之後用 LINE 進同一個帳號：LM
- [x] 17 LINE 已屬於別的帳號（含兩邊同時新增、同帳號同時新增兩個不同 LINE、其他資料庫錯誤照樣丟出）：LM
- [x] 18 只有 LINE 時沒有移除、直接送出被拒：LM
- [x] 19 有 LINE 與 Google、沒有密碼，用任一家確認後移除；兩個瀏覽器同時移除只成功一個；金鑰關掉的那一家不算備援：LC
- [x] 20 只有 LINE 時「用 LINE 確認」後刪帳號；不是帳號上的 LINE 不刪：LC
- [x] 21 沒有密碼時每一家一顆按鈕，LINE 在上：LC
- [x] 22 管理員沒有那一塊、請求被拒、LINE 屬於管理員時不登入：LM；LS

**保存卡與月計數**

- [x] 23 LINE 裡做完、用 LINE 保存、取名稱、同意後直接保存，瀏覽器裡那份被清掉：LV；E `GuestSaveWithLineTest`
- [x] 24 既有帳號先問、「不要」就清掉：LV；E `GuestSaveWithLineTest`
- [x] 25 保存次數加在 LINE 那一格（已知限制見上方）：LV；LS

**匯出、隱私權說明**

- [x] 26 匯出有 LINE 登入方式、沒有權杖：LS
- [x] 27 隱私權說明的 LINE 段落、同意書第 8 版、舊版的人被請再同意：LS

**真機（本人驗收）**

- [ ] 28 iPhone、LINE 裡打開正式站、做完 HHIE-S、「使用 LINE 帳號繼續」、取名稱、同意，全程不離開 LINE（等 #544）
- [ ] 29 同一支手機用 Safari 打開正式站、用 LINE 登入，進到同一個帳號（等 #544）
- [ ] 30 頻道切成「已發布」後，非 Tester 的 LINE 帳號登入成功（等 #544）

## 本人驗收

2026-11-14，本機。本人在 LINE Developers 用 email 註冊的商用帳號（LINE Business ID）建了 Provider「聽伴」與 LINE Login 頻道（只勾 Web app、「開發中」），回呼網址加了本機 8001、8002 與正式站；把個人的 LINE 加為頻道的 Tester。整合分支在 8002 開（`SITE_URL=http://localhost:8002`），本機開發資料庫套用了 0035（不動資料）。用真的 LINE（電腦上掃行動條碼）走完：

- [x] 登入頁、註冊頁：LINE 按鈕（官方圖示、白底灰框）在 Google 上面
- [x] 帳號設定：密碼帳號新增 LINE、用 LINE 登入進同一個帳號、輸入密碼後移除
- [x] 用 LINE 註冊：取名稱頁（email 選填）、同意後進到首頁，再用 LINE 登入回到同一個帳號
- [x] 只有 LINE 的帳號：沒有移除、用 LINE 確認本人後刪除帳號
- [x] 訪客結果用 LINE 保存：新帳號同意後直接保存；既有帳號先問
- [x] 伺服器紀錄這次執行沒有 4xx／5xx 錯誤（`/favicon.ico` 除外）

驗收時發現並修好的問題：瀏覽器裡有沒保存的訪客結果時，打開「先確認是您本人」頁會被帶去保存頁，新增 LINE 就中斷了（新增或移除 Google、刪帳號也一樣，`main` 上已有這個問題）。原因是確認本人頁不在「不問訪客結果」的名單上；改成這頁不問，等流程走完再問（`d062a8a`，先寫了會失敗的測試）。

本人看到的：頻道還在「開發中」時，只有頻道的管理員或 Tester 能用 LINE 登入；個人 LINE 沒加進 Roles 時，LINE 會回「This channel is now developing status. User need to have developer role.」，不是程式的問題。字句沒有提出修改。

第 28–30 條（正式站、iPhone、從 LINE 裡打開、頻道發布）跟著 #544 做，結果寫回 #544。
