# #525 Resend 寄信設定（照著做）

讓 `noreply@tingpal.tw` 寄出的重設密碼信收得到、不進垃圾信件匣，也讓別人不能冒用 `@tingpal.tw` 寄信。2026-11-14 本人選定：SPF `~all`、DMARC `p=quarantine`、不收 DMARC 報告。

做到每個「→ 回報」的地方停下來告訴代理，代理用 `dig` 指令核對 DNS 有沒有生效。

---

## 一、開 Resend 帳號、新增網域

1. 到 resend.com 註冊。建議用 hearwellweb@gmail.com，以後有問題的信都寄到同一個地方。
2. 帳號設定裡**開兩步驟驗證（MFA）**。
3. 左邊選 **Domains** → **Add Domain**：
   - Name：`tingpal.tw`
   - Region：**North Virginia (us-east-1)**。一定要選這個：隱私權說明寫的是「資料存放在美國」。
4. 按下後，Resend 會列出 DNS 紀錄。2026-11-14 實際畫面是這三筆（值以 Resend 畫面為準，用複製鈕複製）：

| 類型 | 名稱（Name） | 值（Content） | 用途 |
|---|---|---|---|
| TXT | `resend._domainkey` | `p=MIGfMA...QIDAQAB`（很長一串） | DKIM：信上的電子簽章 |
| CNAME | `rsend` | `rsend.fo...mta.net` | 寄信用（Resend 自己的 SPF 掛在這裡） |
| CNAME | `send` | `send.for...mta.net` | 寄信用（退信回到 Resend） |

   畫面下面如果有 **Enable Receiving**（收信）和根網域的 MX 紀錄：**不要開、不要加**，那會把 tingpal.tw 的收信搶走、Gandi 信箱收不到信。

這個頁面先不要關，下一步要從這裡複製。

## 二、在 Gandi 加上 Resend 的紀錄

Gandi 後台 → **Domain** → `tingpal.tw` → **DNS Records** → **Add record**，一筆一筆加：

- **名稱只填 Resend 列出的前半段**，例如 `resend._domainkey`、`send`，**不要**加 `.tingpal.tw`。Gandi 會自動補上網域，自己加了會變成 `send.tingpal.tw.tingpal.tw`。
- TXT 的值整串複製貼上，不用自己加引號。
- CNAME 的值**最後加一個點**（例如 `....mta.net.`）。Gandi 把沒有點結尾的值當成 tingpal.tw 底下的名字，會變成 `....mta.net.tingpal.tw`。
- TTL 用預設值。
- 原本的 MX（`spool.mail.gandi.net`、`fb.mail.gandi.net`）**不要動**。Resend 那筆是加在 `send` 子網域上，不會影響你現在收信。

全部加完 → **回報**。代理用 `dig` 確認，接著你回 Resend 按 **Verify DNS Records**，等它顯示 **Verified**。DNS 生效通常幾分鐘，最久可能幾小時。

## 三、收緊 SPF 和 DMARC

一樣在 Gandi 的 DNS Records，**編輯**現有的兩筆，不要新增第二筆：

| 紀錄 | 現在的值 | 改成 |
|---|---|---|
| TXT `@`（名稱可能顯示成 `@` 或空白） | `v=spf1 include:_mailcust.gandi.net ?all` | `v=spf1 include:_mailcust.gandi.net ~all` |
| TXT `_dmarc` | `v=DMARC1; p=none; pct=100;` | `v=DMARC1; p=quarantine; pct=100;` |

- SPF 只把最後的 `?all` 改成 `~all`，其他字一個都不要動。Resend 的 SPF 已經設在 `send` 那筆上了，這筆不用加 Resend。
- 根網域的 SPF 只能有一筆。發現有兩筆 `v=spf1` 開頭的，先停下來回報。

改完 → **回報**，代理用 `dig` 核對。

## 四、建只能寄信的金鑰

Resend 左邊 **API Keys** → **Create API Key**：

- Name：`tingpal-vps`
- Permission：**Sending access**（只能寄信）
- Domain：選 `tingpal.tw`

按下後金鑰（`re_` 開頭）**只會顯示這一次**。複製後直接進下一步，不要貼到對話裡、不要存進雲端記事。

另外有兩個開關要確認是**關著**的：**Click tracking**、**Open tracking**（在 Domains → `tingpal.tw` 的設定裡）。打開的話，Resend 會改寫信裡的重設連結、在信裡放追蹤，隱私權說明沒寫這件事。

## 五、寫進 VPS 的 `.env`，部署

1. SSH 到 VPS，`nano ~/hearwell/.env`，在檔案最後加兩行。等號兩邊不要空格：

   ```
   RESEND_API_KEY=re_你剛複製的金鑰
   DEFAULT_FROM_EMAIL=noreply@tingpal.tw
   ```

   `DEFAULT_FROM_EMAIL` 只填地址，「聽伴」由程式自己加上。

2. 確認寫進去了，**不要 `cat` 整個檔案**：

   ```
   grep -c '^RESEND_API_KEY=re_' ~/hearwell/.env
   grep '^DEFAULT_FROM_EMAIL' ~/hearwell/.env
   ```

   第一行要印出 `1`；第二行印出的是地址，可以貼給代理看。

3. 照 `vpsdeploy.md`「更新程式碼到最新 main」那張表部署，有三點跟上次不同：
   - `.env` 要先加好上面兩行，再跑第 3 步 `check --deploy`。少一個變數，它會直接報錯，並說出缺哪一個。
   - 第 2 步 `pip install -r requirements.txt` 這次會多裝 django-anymail。
   - 第 6b 步 `python manage.py createcachetable` 這次一定要跑。
   - 部署前照舊先備份資料庫（第 0 步）。這次的 migration 不動資料，但習慣不要省。

4. 重啟後 `systemctl status hearwell --no-pager` 要是 `active (running)` → **回報**。

## 六、上線後實際收一封信

1. 用你自己帳號的信箱，在 `https://tingpal.tw` 走一次「忘記密碼？」。
2. 確認以下幾項，回報給代理：
   - [ ] 幾分鐘內收到信
   - [ ] 寄件人顯示「聽伴」
   - [ ] 不在垃圾信件匣
   - [ ] 點連結能設好新密碼、直接登入
   - [ ] （Gmail）信的「顯示原始郵件」裡，SPF、DKIM、DMARC 三個都是 **PASS**
3. 代理把結果補進 `docs/verification/issue-355.md`，另開一個小 PR，再關掉 #525。

## 出問題時

| 現象 | 先看哪裡 |
|---|---|
| Resend 一直不顯示 Verified | 名稱是不是多加了 `.tingpal.tw`；回報給代理跑 `dig` |
| 部署時 `check --deploy` 報「正式環境缺少 RESEND_API_KEY」 | `.env` 那兩行有沒有打錯字、等號旁邊有沒有空格 |
| 忘記密碼頁顯示「信寄不出去」 | Resend 後台 **Emails／Logs** 看被拒絕的原因；Sentry 也會有一筆 |
| 信進了垃圾信件匣 | 看原始郵件的 SPF／DKIM／DMARC 哪個不是 PASS，回報給代理 |
| 金鑰不小心貼出去了 | 到 Resend 刪掉那把、建一把新的、換掉 `.env` 裡的值、重啟（見 `vpsdeploy.md`「密鑰輪替」） |
