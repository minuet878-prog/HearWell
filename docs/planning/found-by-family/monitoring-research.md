# 外部監控免費方案研究

查閱日期：2026-11-16。資料都來自各家官方文件或價格頁（連結在第 4 節）；查不到的寫「未能確認」。
這份只是研究，還沒註冊任何服務、沒改任何設定。

## 1. 摘要

- **建議第一選擇：Sentry Uptime Monitoring**。現有的 Sentry 免費方案就含 1 個，不用把網址交給新的第三方、不用在 VPS 裝東西、不用改程式。文件寫最短 1 分鐘查一次、連續 3 次失敗才算掛，大約 3 分鐘會發現。
- **主要代價**：免費方案只能寄 email（沒有 LINE、Telegram、app 推播），只有 1 個監控；要靠 iPhone 的 Gmail 通知才會「叫」。
- **備案：UptimeRobot 免費方案**。有 iPhone app 推播，但 5 分鐘才查一次，而且網址和 email 會交給一家新的公司。
- **不建議**：GitHub Actions 排程（官方自己說會延遲、會漏跑）、自架 Uptime Kuma（需要第二台一直開著的機器）。
- 有幾件事要你登入 Sentry 後台才看得到（例如是不是已經自動建了一個監控、有沒有設好通知），列在第 5 節最後。

## 2. 兩個概念

- **由外往內探測**：外面的服務每隔幾分鐘來「敲門」，像訪客一樣打開網址，打不開就通知你。抓得到：整台機器掛掉、網路斷線、Nginx 或 Gunicorn 停了、HTTPS 憑證過期、網域（DNS）壞掉。只要訪客看不到網站，它就看不到。
- **由內往外報平安（heartbeat）**：VPS 自己每隔幾分鐘向外面的服務「打卡」，對方太久沒收到就通知你。抓得到：整台機器掛掉、機器對外網路斷線、排程（cron，Linux 的定時器）壞了。**抓不到「機器活著但網站掛了」**，因為打卡的小程式還在跑；除非把打卡寫成「先在本機確認網站有回應，才打卡」。它也看不到憑證過期、DNS 壞掉這種只有外面才看得到的問題。

**這個情境需要哪一種**：一定要「由外往內」，因為驗收是「把服務停掉幾分鐘要收到通知」，機器還活著，heartbeat 不會叫。heartbeat 是加分項，目前不需要；以後有備份排程要盯的時候再加。

## 3. 比較表

名詞先說明：

- **探測點**：監控服務從哪裡的機器來敲門。只有一個探測點時，那台機器自己網路不好也會誤報。
- **重試／確認**：第一次失敗不馬上通知，再查一兩次確定真的掛了才通知，用來減少誤報。
- **MFA**：登入時除了密碼還要第二道驗證（例如手機驗證碼）。
- **整合（integration）**：把通知轉送到別的工具，例如 Telegram、Slack。

| 方案 | 1 通知方式（免費） | 2 頻率與多久發現 | 3 新的第三方？資料 | 4 免費限制 | 5 設定與維護 | 6 誤報風險 |
|---|---|---|---|---|---|---|
| **Sentry Uptime**（由外往內） | 只有 email。價格頁寫免費方案沒有第三方整合 | 可選 1、5、10、20、30、60 分鐘；預設連續 3 次失敗才開問題。1 分鐘一次約 3 分鐘發現。免費方案能不能選 1 分鐘：未能確認 | **不是新的**（已在用）。Sentry 多拿到要查的網址與回應狀態 | 每個方案含 1 個 uptime 監控、1 個 cron 監控；多的 uptime 每個 1 美元、cron 每個 0.78 美元，要先設預算 | 後台設定即可，不裝東西、不改程式。文件說要自己設「警示」才會通知 | 每次從不同地區輪流查，加上 3 次確認，誤報低。防火牆若擋掉它的機器人會誤報 |
| **Sentry Cron 監控**（heartbeat） | 同上，只有 email | 自己訂打卡間隔與寬限時間 | 不是新的。Sentry 多拿到 VPS 的 IP | 含 1 個 | VPS 加一行 cron 用 `curl` 打卡；不用改程式 | 抓不到「機器活著但網站掛了」 |
| **GitHub Actions 排程**（由外往內） | GitHub 的 email 或網頁通知。手機 app 推播有沒有涵蓋 workflow 失敗：未能確認 | 最短 5 分鐘。官方寫尖峰時會延遲、太忙時排隊的工作可能直接被丟掉。沒有內建重試 | 不是新的。網址會寫在 repo 的 workflow 檔裡（這個 repo 是公開的，網址本來就公開） | 公開 repo 用標準機器免費。公開 repo 60 天沒活動會自動停掉排程 | 要寫一個 workflow 檔（算改 repo）。通知寄給「最後改排程的人」，還要到通知設定打開 Actions 通知 | **高**。排程不準時、可能漏跑；單一探測點；GitHub 自己出事時也不會查 |
| **UptimeRobot**（由外往內） | email、iOS／Android app 推播、另加 5 個整合（官方頁列出 Telegram 等，免費方案能選哪 5 個：未能確認）。簡訊、電話要買點數 | 5 分鐘。失敗後會從同區另一個機房再查一次才開事件，約 5 到 6 分鐘內發現 | **新的**。拿到網址、IP、回應狀態、你的 email、手機推播代碼 | 50 個監控、資料留 3 個月。條款寫「可用於任何用途，含商業」（2026-05-26 加入合理使用政策）；但價格頁的常見問題又寫免費版是「基本的個人監控」，兩處說法不一致 | 註冊帳號、裝 app。不動 VPS、不改程式。MFA 有沒有：未能確認 | 低（有二次確認）。停不到 5 分鐘可能剛好沒被查到 |
| **Better Stack**（兩種都有） | Slack 與 email。app 推播、簡訊、電話看起來要付費的「responder」授權；免費有沒有推播：未能確認 | 免費 3 分鐘（文件頁較舊）。確認時間可自己設 | **新的**。資料同上 | 監控加 heartbeat 合計 10 個、1 個狀態頁。價格頁寫「Free for personal projects」（給個人專案） | 註冊帳號即可 | 低。多地點確認的細節：未能確認 |
| **healthchecks.io**（heartbeat） | email、Telegram、ntfy、Pushover、Signal、Discord、Slack、webhook 等。簡訊、電話是付費方案的額度 | 自己訂。例：每 5 分鐘打卡、寬限 5 分鐘，約 10 分鐘內通知 | **新的**。拿到 VPS 的 IP、打卡時間、通知用的 email；**不需要給網址** | 20 個檢查、每個留 100 筆紀錄。官方寫免費給業餘用途、開源專案、非營利 | VPS 加一行 cron。打卡網址要當密碼保管 | 抓不到「機器活著但網站掛了」，除非打卡前先在本機查網站 |
| **HetrixTools**（由外往內） | email（1 個收件人）、Telegram、Pushover、ntfy、Discord、Slack、webhook。簡訊、電話每則 0.10 美元 | **1 分鐘**，從 4 個地點查。幾個地點失敗才通知：未能確認 | **新的**。資料同 UptimeRobot | 15 個監控。**每 90 天要登入一次**，否則不保證免費帳號繼續有效 | 註冊帳號。Telegram 要先裝 Telegram | 低（多地點） |
| **StatusCake**（由外往內） | 價格頁只寫「透過整合通知」，另一頁寫 14 個整合含 Slack、Teams、Discord。email、推播：未能確認 | 5 分鐘 | **新的** | 10 個監控、1 人 | 註冊帳號 | 未能確認 |
| **Freshping** | 已停止服務 | — | — | 多個非官方來源寫 2026-03-06 停止；官方公告頁打不開，未能確認原文 | — | — |
| **自架 Uptime Kuma**（由外往內） | 90 多種，含 Telegram、email | 最短 20 秒 | 不交給第三方 | 軟體免費，但要多一台機器 | 要顧第二台機器、更新、備份 | 單一探測點；第二台機器掛了沒人知道 |

## 4. 各方案補充與來源

**Sentry Uptime Monitoring**
已經在用 Sentry，所以不新增第三方，這是它最大的好處。文件說 Sentry 可能已經替「最常出現的網域」自動建了一個監控；也說要另外設「警示」才會收到通知。它的機器人名稱是 `SentryUptimeBot/1.0`，Nginx 或防火牆不要擋它。逾時秒數文件前後寫的不一樣（一處 10 秒、一處最多 30 秒）。
- https://sentry.io/pricing/ （免費方案：1 個 uptime 監控、只有 email、沒有第三方整合）
- https://docs.sentry.io/pricing/ （「所有方案含 1 個 cron 監控和 1 個 uptime 監控」、多的 uptime 每個 1 美元、cron 每個 0.78 美元）
- https://docs.sentry.io/product/uptime-monitoring/ （頻率、3 次失敗、通知要設警示）
- https://docs.sentry.io/product/monitors-and-alerts/monitors/uptime-monitoring/troubleshooting/ （機器人名稱、被防火牆擋的誤報）
- https://docs.sentry.io/security-legal-pii/security/ip-ranges/ （探測用的 12 個 IP）

**Sentry Cron 監控**
同一個帳號免費含 1 個，可以當 heartbeat：VPS 的 cron 用 `curl` 打一個網址報平安，太久沒打就開問題。現在不需要，列出來是因為它不用新增第三方。
- https://docs.sentry.io/product/crons/getting-started/http/

**GitHub Actions 排程**
看起來最省事（不用新帳號），但官方文件自己寫了三個問題：最短 5 分鐘、忙的時候會延遲甚至丟掉、公開 repo 60 天沒活動會停掉排程。監控最怕「該叫的時候沒叫」，所以不建議當主要方案。這個 repo 是公開的，分鐘數不用錢；私有 repo 的免費額度現在用金額表示（免費帳號每月 12 美元，我自己換算約 2,000 分鐘），每 5 分鐘跑一次會超過。
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows （schedule：5 分鐘、延遲、丟棄、60 天）
- https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs （通知寄給誰）
- https://docs.github.com/en/subscriptions-and-notifications/how-tos/managing-github-actions-notifications （通知設定、只通知失敗）
- https://docs.github.com/en/billing/concepts/product-billing/github-actions （公開 repo 免費、私有額度）

**UptimeRobot**
免費方案裡通知方式最適合 iPhone：有 app 推播。條款現在明寫可以商業使用；我印象中前幾年曾把免費版限定非商業，但現在的官方頁面找不到這段歷史，所以只能說「現行條款允許」。同一頁的常見問題又說免費版適合個人監控，哪天再改條款的風險是有的。
- https://uptimerobot.com/pricing/ （50 個、5 分鐘、5 個整合、資料留 3 個月）
- https://uptimerobot.com/terms/ （「可用於任何用途，含商業」、2026-05-26 修訂）
- https://uptimerobot.com/terms-fair-use/ （合理使用政策：超出方案用量時可能被限流或要求升級）
- https://uptimerobot.com/ （失敗後從另一個機房再查一次，免費版也有）
- https://uptimerobot.com/alternative-to-uptimekuma/ （app 每個方案都免費、免費版含 email 加 5 個整合）

**Better Stack**
功能完整，但免費版通知只列 Slack 和 email，對不用 Slack 的人等於只有 email，沒有比 Sentry 多什麼，卻多一個第三方。
- https://betterstack.com/pricing
- https://betterstack.com/docs/uptime/check-frequency/ （免費 3 分鐘）
- https://betterstack.com/docs/uptime/confirmation-and-recovery-period/

**healthchecks.io**
heartbeat 類裡最單純，一個人經營、有獲利、程式開源。通知選擇多（Telegram、ntfy 都免費）。但它單獨用抓不到這次驗收要的情況。LINE 的免費通知服務（LINE Notify）已在 2025-03-31 結束（來源是台灣媒體轉述，沒找到 LINE 官方原文），所以各家都沒有簡單的 LINE 通知了。
- https://healthchecks.io/pricing/ （20 個檢查、每個 100 筆紀錄）
- https://healthchecks.io/docs/ 、https://healthchecks.io/docs/configuring_notifications/
- https://healthchecks.io/about/ （誰在經營、免費給哪些用途）
- https://healthchecks.io/ （整合清單）

**HetrixTools**
免費方案裡查得最勤（1 分鐘、4 個地點），Telegram 通知免費。代價是每 90 天要登入一次，忘了就可能失效；公司規模小。
- https://hetrixtools.com/pricing/uptime-monitor/

**StatusCake**
免費 10 個監控、5 分鐘。免費版到底能用哪些通知，官方頁寫得不清楚，沒有比 UptimeRobot 好的地方。
- https://www.statuscake.com/pricing/ 、https://www.statuscake.com/free-website-monitoring/

**Freshping**
多個非官方來源寫 Freshworks 在 2026-03-06 停止這項服務。官方頁面回應 403 打不開，原文未能確認。不用考慮。

**自架 Uptime Kuma**
放在同一台 VPS 沒用：機器掛了，監控也一起掛，沒人發通知。所以一定要第二台「一直開著」的機器；家裡的電腦會關機、會睡眠，不算。多一台 VPS 就不是免費，還多一台要更新和備份的機器，而且那台掛了也沒人知道。
- https://github.com/louislam/uptime-kuma

## 5. 建議

### 第一選擇：Sentry Uptime Monitoring

做法：在 Sentry 後台建（或沿用已自動建立的）1 個監控，查首頁或一個不用登入的公開頁面，間隔設 1 分鐘，再設一個警示寄 email 給你。iPhone 的 Gmail app 打開通知，就等於手機會叫。

代價：
- 只有 email。半夜不會特別吵醒你；信也可能被歸到別的分頁，建議在 Gmail 把 Sentry 的信設成重要。
- 只有 1 個監控。以後想多查一個網址要付錢或換方案。
- 錯誤回報和掛站通知都靠同一家；Sentry 自己出事時兩個都收不到。
- 驗收時服務要停 **5 分鐘以上**（1 分鐘一次、連續 3 次失敗，再加寄信時間）。如果免費方案只能選 5 分鐘間隔，就要停 15 到 20 分鐘。

### 備案：UptimeRobot 免費方案

適合的情況：你想要手機 app 推播，或 Sentry 後台發現免費方案做不到上面的設定。

代價：
- 多一家第三方拿到網址、你的 email、手機推播代碼。網址本來就是公開的，沒有健康資料外流的問題，但多一個帳號要顧（要開 MFA）。
- 5 分鐘才查一次，驗收時服務要停 **10 分鐘以上**才保險。
- 免費條款以後可能再變。

兩個也可以一起用（Sentry 寄信、UptimeRobot 推播），互相備援；代價就是上面兩邊相加。

如果覺得 5 分鐘太慢又想要手機通知，第三個選擇是 HetrixTools（1 分鐘、Telegram），代價是要裝 Telegram、每 90 天要登入一次。

### 不管選哪個都要注意

- 查的網址用不需要登入的公開頁面，不要帶任何登入資訊。
- 監控每分鐘來一次，會出現在 Nginx 的存取紀錄裡；如果有流量統計要排除它。
- 設好之後一定要照驗收做一次真的停機測試，不要只看後台顯示「正常」。

### 未能確認、需要你登入後台才看得到

1. Sentry 是不是已經自動建了一個 uptime 監控（文件說會替最常出現的網域自動建）。
2. Sentry 免費方案能不能選 1 分鐘間隔（文件列了 1 分鐘，但沒寫各方案有沒有差別）。
3. Sentry 掛站的「問題」會不會照你現有的警示規則寄信，還是要另外建一條警示。
4. Sentry 探測點在哪些地區（只查到共 12 個 IP，沒寫地點）。
5. 你的 Sentry、GitHub 帳號有沒有開 MFA。
6. GitHub 通知設定裡 Actions 那一項目前是什麼（只有選 GitHub Actions 方案才需要看）。
7. UptimeRobot 免費方案可選的 5 個整合是哪些、帳號有沒有 MFA（註冊後才看得到）。
8. Better Stack 免費方案有沒有 app 推播；HetrixTools 幾個地點失敗才通知；StatusCake 免費方案有沒有 email 與推播。
