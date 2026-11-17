# 重測提醒信：在 VPS 加每天 09:00 的排程（規格 #656，#663）

打開 email 重測提醒的人，上一筆生活影響問卷滿 6 個月那天早上會收到一封重測提醒信。程式有 `send_retest_reminders` 指令，要 VPS 每天台灣時間 09:00 跑一次才會寄。它不跟 02:30 的清除服務放一起：時間不同，另開一組服務＋timer。

代理看不到 VPS。下面的 `<專案資料夾>`、`<venv 的 python>` 換成你 VPS 筆記（`vpsdeploy.md`「清除 90 天前的提問紀錄」那段）裡 `WorkingDirectory` 和 `ExecStart` 的真的值。

做這一步的時機：

- **部署之前**先做第一段：這次起，正式環境沒設 `SITE_URL` 網站就不會啟動（信裡的連結要用它組完整網址）。
- 第二段以後：重測提醒的程式合併上線、部署完、`migrate` 跑過，而且信的字（#665）已經放進去之後。

---

## 一、部署前：確認 `.env` 有 `SITE_URL`

1. SSH 連上 VPS，到專案資料夾：

   ```bash
   cd <專案資料夾>
   ```

2. 看 `SITE_URL` 那一行：

   ```bash
   grep '^SITE_URL=' .env
   ```

   做對了會看到：`SITE_URL=https://tingpal.tw`（結尾沒有斜線）。Google 登入早就用到它，通常已經有了。什麼都沒印出來：用 `nano .env` 加上這一行再部署。

## 二、加服務檔

服務檔說「要跑什麼」。從 02:30 那個清除服務複製一份來改，使用者、環境變數那幾行就會跟它一樣：

```bash
sudo cp /etc/systemd/system/hearwell-purge-question-log.service /etc/systemd/system/hearwell-retest-reminders.service
```

```bash
sudoedit /etc/systemd/system/hearwell-retest-reminders.service
```

改兩個地方，其他行不要動：

1. `[Unit]` 的 `Description=` 改成：

   ```ini
   Description=聽伴 寄重測提醒信
   ```

2. 原本的 `ExecStart=` 行（`purge_question_log`，加過意見回饋清除的話還有 `purge_feedback`）**全部刪掉**，換成這一行（路徑照原本的抄，只換最後的指令名稱）：

   ```ini
   ExecStart=<venv 的 python> manage.py send_retest_reminders
   ```

存檔離開。

## 三、加 timer 檔

timer 說「什麼時候跑」：

```bash
sudoedit /etc/systemd/system/hearwell-retest-reminders.timer
```

整段貼上：

```ini
[Unit]
Description=聽伴 每天 09:00 寄重測提醒信

[Timer]
OnCalendar=*-*-* 09:00:00 Asia/Taipei
Persistent=true

[Install]
WantedBy=timers.target
```

- `Asia/Taipei`：照台灣時間，不管 VPS 本身設哪個時區。
- `Persistent=true`：VPS 在 09:00 關著的話，開機後馬上補跑一次；那幾天到期、還沒寄的會照寄（驗收 24）。

存檔離開，讓 systemd 讀新檔、打開 timer：

```bash
sudo systemctl daemon-reload
```

```bash
sudo systemctl enable --now hearwell-retest-reminders.timer
```

確認下一次執行的時間：

```bash
systemctl list-timers hearwell-retest-reminders.timer --no-pager
```

做對了會看到：`NEXT` 那欄是下一個早上 09:00（台灣時間；如果顯示的是 UTC，就是 01:00）。出現 `Failed to parse calendar specification`：VPS 的 systemd 太舊、不認得時區寫法，把那行換成 `OnCalendar=*-*-* 01:00:00 UTC`（台灣沒有夏令時間，兩個一樣），再從 `daemon-reload` 做一次。

## 四、馬上跑一次確認

```bash
sudo systemctl start hearwell-retest-reminders.service
```

```bash
journalctl -u hearwell-retest-reminders.service -n 5 --no-pager
```

看到這行就對了（數字可能不是 0）：

```text
python[...]: Sent 0 retest reminder(s).
```

出現 `Unknown command: 'send_retest_reminders'`：程式還沒部署到這台，先部署再跑。出現其他錯誤：整段貼給代理。

同一天多跑幾次沒關係：同一個人同一次到期只會寄一封（驗收 18）。

## 五、隔天再看一次

隔天 09:00 過後看排程自己跑過：

```bash
journalctl -u hearwell-retest-reminders.service --since yesterday --no-pager
```

有 `Sent ... retest reminder(s).`、時間是 09:00 左右，就完成了。把結果告訴代理，寫進驗證紀錄。

實際收一封信、按取消、確認 Gmail 上方有「取消訂閱」是另一步（規格 #656「其他」）：怎麼讓你指定的測試帳號「今天到期」，到驗收時代理先說明做法，不動真實使用者的資料。
