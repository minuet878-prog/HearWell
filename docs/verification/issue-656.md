# #656 email 重測提醒

日期：2026-11-17。分支：`feat/656-retest-reminder`。規格 [#656](https://github.com/minuet878-prog/HearWell/issues/656)，票 #657（設計圖）、#658（本人寫字）、#659–#665（實作）、#666（本人上線後在正式站做）。

狀態：2026-11-17 本人在本機實際操作後回覆「看過了，沒問題」，**驗收通過**（含「不一樣的地方」第 1 條代理擬的用字）。自動測試全過（單元 2975、端對端 497）。上線後本人做 #666。

- 拷問決定：[retest-reminder-grill-decisions.md](../planning/found-by-family/retest-reminder-grill-decisions.md)，ADR 0065（同意書不升版）。
- 本人在設計圖選定（2026-11-16，#657）：帳號設定 C（狀態＋一顆按鈕）、補上 email 照畫的、結果頁 B（建議下一步下面一塊）、取消頁 B（寫出帳號）、提醒信 A（取消在信尾）。
- 本人的字（2026-11-17，#658）：七段一段一段選定，原文在 [#658 的留言](https://github.com/minuet878-prog/HearWell/issues/658#issuecomment-6921697978)。
- 隱私權說明：代理擬稿、本人照擬稿核准（#664），另加「蒐集哪些資料」一條。同意書維持第 8 版（ADR 0065）。
- 第 4 步自審（`/mattpocock-skills:code-review`，基準 `origin/main`）：Standards 沒有硬性違規；Spec 找到 Resend 429 分不清額度與速率（本人選「分辨錯誤名稱＋每封間停半秒」）、兩個 migration 要合成一個、三個斷言偏弱，都修了。
- 交叉審查（Codex，2026-11-17）：[審查與處理計畫](https://github.com/minuet878-prog/HearWell/issues/656#issuecomment-6936084748)、[第一次複核後的處理](https://github.com/minuet878-prog/HearWell/issues/656#issuecomment-6937379073)。本人決定：寄信中斷「寧可漏寄」、驗收 11 維持原樣、日誌個資三處一起修、本機日誌保留錯誤類型與位置。第二次複核沒有要修（本人 2026-11-17 回覆）。
- 整合時另外修了：取消頁的頁尾「意見回饋」連結會把取消代碼帶進回饋頁網址（本人同意後照分享報告頁的做法修）。
- 沒有操作真實資料。測試都在臨時測試資料庫上。

## 行為

| 項目 | 現在 |
|---|---|
| 帳號設定「email 重測提醒」 | 預設關。本人的用途說明＋「目前：沒有打開」＋外框按鈕「打開提醒」＋會寄到的信箱。打開後 ✓ 已開啟、開啟日、下次篩檢日期、文字連結「關掉提醒」。已到期時「您現在就可以再做一次」：到期日早於打開那天才加「這一次不另外寄信」，到期當天打開寫「已經滿半年」 |
| 補上 email | 只有 email 空白的帳號有：「我的帳號」email 列的「補上」和提醒區的「補上 email」。先確認本人（密碼／Google／LINE，5 分鐘、用一次）→ 補 email 頁。有 email 的照舊寫信改 |
| 結果頁 | 已登入者的 HHIE-S／HHIA-S 結果頁，「建議您下一步」下面一塊：半年後再做一次、下次建議日期、用途說明、外框按鈕。已開啟只顯示 ✓；沒 email 連到帳號設定；THI、IOI-HA、訪客沒有 |
| 寄信排程 `send_retest_reminders` | 每天 09:00（台灣）找出到期、開著提醒的人各寄一封；到期日要在打開那天或之後。每封寄前重新確認（還開著、有 email、沒停用、不是管理員、到期日沒變）。先記「已在寄」再寄（寧可漏寄）。一天最多 60 封（含當天先前幾次），剩下隔天接著寄。每封之間停半秒 |
| 寄不出去 | 那一封記一次失敗、其他照寄，隔天再試、最多 3 天。Resend 說今天或本月額度用完才停下當天、不算失敗；其他 429 或讀不出原因的都算那一封失敗 |
| 提醒信 | 主旨「聽伴 重測提醒」。使用者名稱、本人的內文、大按鈕「再做一次」、信尾本人那句＋取消連結；HTML 與純文字；寄件 `noreply@tingpal.tw`、回覆到聯絡信箱；帶一鍵取消標頭 |
| 取消頁 `/reminder/cancel/<代碼>` | 不用登入。打開只顯示帳號名稱、本人的說明、「取消提醒」；按了才取消，到 ✓ 已取消頁。Gmail 的一鍵取消直接回成功。代碼錯、帳號已刪、舊信（關掉再打開後）都是「這個連結已經不能用了」。不收錄、不快取、不送來源網址 |
| 後台 | 提醒設定、寄送紀錄都只能看，看不到取消代碼。匿名月計數多一欄「寄出提醒信」 |
| 隱私權說明 | 新增「email 重測提醒」一段、「為什麼蒐集」「蒐集哪些資料」各一條、Resend 兩條改寫、備份補「連不上網站主機時可能暫時超過 10 天」。日期 2026/11/17，同意書第 8 版 |
| 日誌 | 寄信失敗時（提醒信、重設密碼信、回饋通知信三處），VPS 的日誌只有固定訊息、錯誤類型、出錯位置，沒有錯誤內容與 email；完整錯誤在 Sentry（已遮個資） |

跟規格或設計圖不一樣、或規格沒寫到的地方（請本人驗收時一起看）：

1. **到期當天打開提醒時寫「上一次是〈日期〉，已經滿半年。」**：代理擬的介面用字，沒給本人看過。
2. **信裡「再做一次」先經過同意頁**（`/consent?next=…`）：沒登入時直接開作答網址會變成訪客版；經過同意頁，沒登入的先登入，登入後直接開那份問卷。
3. **純文字版的取消網址放在「取消提醒」的下一行**（跟「再做一次：」下一行接網址一致）。
4. **後台的寄出時間在寄之前就寫了**：中斷在記錄與寄出之間時，後台顯示已寄、信可能沒寄出，要看 Resend 自己的紀錄。
5. **沒有 email 的帳號不再顯示「要修改請寫信」**：換成「補上」按鈕；那句只跟出生年有關。email 與出生年都填了的帳號照舊不顯示（驗收 11 本人決定維持原樣）。
6. **關掉提醒會清空開啟日**：關掉後「下載我的資料」看不到原本的開啟日。
7. **兩個排程同時跑時，一天上限仍可能多寄幾封**：上限在開跑時算一次；VPS 不會同時跑兩個，沒有加鎖。
8. **排程為每個開著提醒的人重算一次到期日**（交叉審查的維護性觀察，不修）：跟首頁用同一個算法；人數多了再改。
9. **正式環境沒設 `SITE_URL` 網站起不來**：Google 登入本來就用它，VPS 應該已經有；部署前照[排程清單](../deployment/retest-reminder-timer.md)確認。
10. **截圖基準**：隱私權說明多一段，`e2e/screenshots.py` 的隱私權說明截圖可能要重拍。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。測試檔都在 `screening/tests/`，「端對端」＝`e2e/main_flow.py`。

| # | 驗收條件（簡寫） | 驗證 | 證據 |
|---|---|---|---|
| 1–6 | 帳號設定開關：預設關、打開、關掉、已到期、沒 email、不靠 JavaScript | ✅ 自動 | `test_reminder_switch.py`（`ReminderSwitchTests`） |
| 7–11 | 補上 email：先確認本人、存好、格式錯、5 分鐘與用一次、有 email 改不了 | ✅ 自動 | `test_add_email.py` |
| 12–15 | 結果頁：問、已開啟、沒 email、THI／IOI-HA／訪客沒有 | ✅ 自動 | `test_result_reminder.py` |
| 16–26 | 到期當天寄、前一天不寄、不重複、不催、重做後再寄、提前重做、誰不寄、打開前到期不寄、漏跑補寄、60 封、同信箱各一封 | ✅ 自動 | `test_retest_reminder_mail.py`（`WhenItIsSentTests`） |
| 27 | 信的內容、寄件與回覆、一鍵取消標頭、沒有分數分級 | ✅ 自動 | `test_retest_reminder_mail.py`（`TheMailTests`、`TurnedOnAgainTests`、`NoHealthDataTests`） |
| 28 | 「再做一次」：先登入再直接開同一份問卷（HHIE-S、HHIA-S） | ✅ 自動 | `test_retest_reminder_mail.py`（`RetestLinkTests`） |
| 29–30 | 寄失敗、Sentry 不帶 email、本機日誌不帶 email、額度用完、其他 429 | ✅ 自動 | `test_retest_reminder_mail.py`（`FailedSendTests`、`QuotaUsedUpTests`、`FailedSendSentryTests`）；`test_monitoring.py`（重設密碼信、回饋通知信） |
| 31 | 月計數「寄出提醒信」 | ✅ 自動 | `test_retest_reminder_mail.py`（`MonthCountTests`） |
| 32–39 | 取消頁、按鈕、一鍵取消回 200、連結無效、再按、舊代碼（含交錯）、同信箱另一帳號、未同意也能取消、不收錄不快取、頁尾不帶代碼 | ✅ 自動 | `test_reminder_cancel.py` |
| 40 | 手機 200% 不左右捲（帳號設定、取消頁、已取消頁） | ✅ 自動 | 端對端 `test_account_retest_reminder_fits_a_phone_at_double_text_size`、`test_reminder_cancel_pages_fit_a_phone_at_double_text_size` |
| 41–42 | 隱私權說明的段落、6 個月跟程式一致、同意書第 8 版 | ✅ 自動 | `test_reminder_privacy.py` |
| 43–45 | 刪帳號一起刪、下載我的資料、後台只能看（兩筆對多筆查詢次數相同） | ✅ 自動 | `test_reminder_switch.py`（`ReminderDataTests`）；`test_retest_reminder_mail.py`（`DeletedAccountTests`、`SentAdminTests`） |
| — | 首頁「下次篩檢」等於排程的到期日 | ✅ 自動 | `test_retest_reminder_mail.py`（`SameDueDayAsTheHomePageTests`） |
| — | 照設計圖選定的排法、本人的字 | ✅ 本人 | 2026-11-17 本機操作，下面的清單 |
| — | VPS 09:00 排程、正式站實收一封並取消 | ⏳ 本人上線後 | [排程清單](../deployment/retest-reminder-timer.md)，#666 |

## 本人實際操作驗收（本機）

提醒信的樣子：直接打開 `/Users/huangweizhe/HearWell/.claude/retest-reminder-mail-preview.html`（範例資料，沒有寄出）。

畫面：在終端機開 worktree 的網站（`migrate` 會在您本機的資料庫多兩張表、月計數表多一欄，不動既有資料）：

```bash
cd /Users/huangweizhe/HearWell/.claude/worktrees/656-retest-reminder && /Users/huangweizhe/HearWell/py313/bin/python manage.py migrate && /Users/huangweizhe/HearWell/py313/bin/python manage.py runserver 8001
```

打開 http://localhost:8001 ，用一個您自己的測試帳號，手機寬度或字放大 200% 也看一次：

- [x] 帳號設定：「email 重測提醒」一段，打開提醒 → ✓ 已開啟、下次篩檢日期 → 關掉提醒
- [x] 沒有 email 的帳號（例如用 LINE 註冊沒填）：「補上」→ 確認本人 → 補 email 頁，打錯格式一次
- [x] 做一次 HHIE-S 或 HHIA-S：結果頁「建議您下一步」下面那一塊，按「到期時寄 email 提醒我」→ 回到結果頁變成 ✓
- [x] 取消頁：帳號設定打開提醒後，在後台「重測提醒設定」看不到代碼（正常）；取消頁要從信裡的連結進，本機驗收看提醒信預覽即可，取消流程由自動測試證明
- [x] 隱私權說明：「email 重測提醒」一段與其他改動
- [x] 上面「不一樣的地方」第 1 條的用字
