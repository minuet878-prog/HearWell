# 意見回饋 90 天清除：加進 VPS 的 02:30 排程（規格 #633，#639）

意見回饋只保存 90 天（ADR 0064）。程式有 `purge_feedback` 指令，但要 VPS 每天跑才算兌現。照提問紀錄的做法，加在同一個 02:30 的服務裡，不另開排程。

代理看不到 VPS。下面的 `<專案資料夾>`、`<venv 的 python>` 換成你 VPS 筆記（`vpsdeploy.md`「清除 90 天前的提問紀錄」那段）裡 `WorkingDirectory` 和 `ExecStart` 的真的值。

做這一步的時機：意見回饋的程式合併上線、部署完、`migrate` 跑過之後（規格 #633 的第 10 張票 #643）。

---

## 一、在服務檔加一行

1. SSH 連上 VPS。
2. 打開提問紀錄的清除服務：

   ```bash
   sudoedit /etc/systemd/system/hearwell-purge-question-log.service
   ```

3. 在原本那行 `ExecStart=...purge_question_log` 的**下面**加一行（路徑照上一行抄，只把最後的指令名稱換掉）：

   ```ini
   ExecStart=<venv 的 python> manage.py purge_feedback
   ```

   這個服務是 `Type=oneshot`，可以有好幾行 `ExecStart`，會照順序一行一行跑。`[Unit]` 的 `Description` 不用改。

4. 存檔離開，讓 systemd 重新讀設定：

   ```bash
   sudo systemctl daemon-reload
   ```

timer 檔（`.timer`）不用動，時間還是每天台灣時間 02:30，在 03:00 備份之前。

## 二、馬上跑一次確認

```bash
sudo systemctl start hearwell-purge-question-log.service
```

```bash
journalctl -u hearwell-purge-question-log.service -n 5 --no-pager
```

看到這兩行就對了（數字可能不是 0）：

```text
python[...]: Purged 0 question(s) older than 90 days.
python[...]: Purged 0 feedback older than 90 days.
```

只看到第一行：第 3 步那行沒加到或打錯，回去檢查。出現 `Unknown command: 'purge_feedback'`：程式還沒部署到這台，先部署再跑。

## 三、隔天再看一次

隔天早上看排程自己跑過：

```bash
journalctl -u hearwell-purge-question-log.service --since yesterday --no-pager
```

兩行都在、時間是 02:30 左右，就完成了。把結果告訴代理，寫進驗證紀錄（#643）。
