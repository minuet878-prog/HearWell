# 收尾清單：本人要做的事（規格 #561）

[回部署參考](README.md)

「讓家屬找得到」第 1 項（[拷問決定](../planning/found-by-family/closing-grill-decisions.md)）裡要本人動手的步驟，照順序做。每一步都寫了「做對了會看到什麼」；看到的不一樣就停下來，把畫面或輸出貼給代理。

這份文件在公開的 repo 裡，所以主機位址、帳號都用代稱，真的值在本人不進版控的 `vpsdeploy.md`。

| 代稱 | 是什麼 | 真的值去哪裡查 |
|---|---|---|
| `hearwell-vps` | 在 Mac 的 `~/.ssh/config` 設的 VPS 代稱（第 1 段第 1 步設） | 設好之後 `ssh -G hearwell-vps \| grep -E '^(hostname\|user) '` |
| `<VPS 位址>`、`<VPS 使用者>` | VPS 的 IP 與登入帳號 | `vpsdeploy.md` 開頭的連線方式 |

| 段 | 內容 | 先做完 | 票 |
|---|---|---|---|
| 1 | Mac 自動拉備份 | — | #567 |
| 2 | 刪手動備份 | 1 | #567 |
| 3 | 還原演練 | 1、2 | #568 |
| 4 | 從正式站走一次忘記密碼 | — | #565 |
| 5 | 設定 Sentry 監控 | 運作檢查已部署（#562） | #569 |
| 6 | 兩次停機測試 | 5 | #569 |

---

## 1. Mac 自動拉備份（#567）

做好之後：Mac 每次登入、每天 12:00（睡著就醒來時補）把 VPS 的備份拉回 `~/backups/hearwell-vps`。拉成功、而且最新一份在 2 天內，才刪超過 8 天的 `hearwell-db-日期.dump`；拉不到或都是舊的就跳桌面通知，一份都不刪（[拷問決定](../planning/found-by-family/closing-grill-decisions.md) Q1–Q3）。

### 1-1 確認 FileVault、設 VPS 代稱

隱私權說明寫備份是「加密的」：Mac 上靠 FileVault（整顆硬碟加密）。先確認它開著：

```bash
fdesetup status
```

做對了會看到：`FileVault is On.`。不是的話先停下來，到系統設定 → 隱私權與安全性 → FileVault 打開，再往下做。

打開 Mac 的 `~/.ssh/config`（`open -e ~/.ssh/config`），在檔案**最上面**（`Host *` 之前）加三行，`<VPS 位址>`、`<VPS 使用者>` 換成真的值：

```
Host hearwell-vps
  HostName <VPS 位址>
  User <VPS 使用者>
```

確認：

```bash
ssh -o BatchMode=yes hearwell-vps 'ls ~/backups'
```

做對了會看到：VPS 上的備份檔清單，**沒有問密碼**。`BatchMode=yes` 表示「需要輸入東西就直接失敗」，排程半夜跑時也是這樣；如果這裡失敗，排程也會失敗。

### 1-2 放腳本

整段貼進終端機（從 `mkdir` 到 `EOF` 那一行）：

```bash
mkdir -p ~/bin && cat > ~/bin/hearwell-pull-backups.sh <<'EOF'
#!/bin/bash
# 聽伴：把 VPS 的資料庫備份拉回這台 Mac，拉成功、而且拿到新的，才刪超過 8 天的舊備份。
# launchd 在登入時、每天 12:00 執行它（見 docs/deployment/closing-checklist.md）。
set -u

# 平常不用設環境變數；HEARWELL_BACKUP_* 只在測試時把來源、目的地指到別的地方。
source_dir="${HEARWELL_BACKUP_SOURCE:-hearwell-vps:backups/}"
backup_dir="${HEARWELL_BACKUP_DIR:-$HOME/backups/hearwell-vps}"
log_file="${HEARWELL_BACKUP_LOG:-$HOME/Library/Logs/hearwell-backup-pull.log}"
retry_seconds="${HEARWELL_BACKUP_RETRY_SECONDS:-60}"
keep_days=8
fresh_days=2
attempts=3

log() {
  echo "$(/bin/date '+%Y-%m-%d %H:%M') $1" >> "$log_file"
}

notify() {
  log "$1"
  if [ -n "${HEARWELL_BACKUP_NOTIFY_FILE:-}" ]; then
    echo "$1" >> "$HEARWELL_BACKUP_NOTIFY_FILE"
  else
    /usr/bin/osascript -e "display notification \"$1\" with title \"聽伴備份\""
  fi
}

/bin/mkdir -p "$backup_dir" "$(/usr/bin/dirname "$log_file")"

# 剛登入時網路可能還沒好，失敗就等一下再試，三次都失敗才算拉不到。
pulled=false
for attempt in $(/usr/bin/seq "$attempts"); do
  if /usr/bin/rsync -a --exclude '*.tmp' \
    -e "/usr/bin/ssh -o BatchMode=yes -o ConnectTimeout=20" \
    "$source_dir" "$backup_dir/"; then
    pulled=true
    break
  fi
  if [ "$attempt" -lt "$attempts" ]; then
    /bin/sleep "$retry_seconds"
  fi
done
# rsync -a 會把 VPS 那邊的權限帶過來，拉完一律改回只有自己能讀寫。
/bin/chmod 700 "$backup_dir"
/usr/bin/find "$backup_dir" -maxdepth 1 -name '*.dump' -type f -exec /bin/chmod 600 {} +

if [ "$pulled" != true ]; then
  notify "失敗：連不上 VPS，備份沒有拉回來，舊備份一份都沒刪。"
  exit 1
fi

# 拉得到但都是舊的，代表 VPS 那邊的每日備份可能停了：這時也不刪。
fresh=$(/usr/bin/find "$backup_dir" -maxdepth 1 -name 'hearwell-db-*.dump' -type f \
  -mtime "-${fresh_days}d")
if [ -z "$fresh" ]; then
  notify "失敗：最新的備份超過 ${fresh_days} 天了，VPS 的每日備份可能停了，舊備份一份都沒刪。"
  exit 1
fi

# 只刪檔名是 hearwell-db-日期.dump、超過 8 天的；手動備份和其他檔案不動。
deleted=$(/usr/bin/find "$backup_dir" -maxdepth 1 -name 'hearwell-db-*.dump' -type f \
  -mtime "+${keep_days}d" -print -delete | /usr/bin/wc -l | /usr/bin/tr -d ' ')
newest=$(/bin/ls -t "$backup_dir"/hearwell-db-*.dump | /usr/bin/head -1)
log "成功：最新一份是 $(/usr/bin/basename "$newest")，刪了 ${deleted} 份超過 ${keep_days} 天的。"
EOF
chmod 700 ~/bin/hearwell-pull-backups.sh
```

- `<<'EOF'` 的單引號讓裡面的 `$HOME`、`$1` 原封不動寫進檔案，等腳本執行時才讀。
- 腳本裡的指令都寫完整路徑（`/usr/bin/rsync`）：launchd 執行時的 `PATH` 很短，找不到 Homebrew 裝的東西。
- 這是 Mac 內建的 rsync（openrsync），2026-11-16 代理在暫存資料夾測過四種情況與 8 天的邊界，結果見 [驗證紀錄](../verification/issue-563-564.md)。

### 1-3 用假的舊檔試一次

```bash
mkdir -p ~/backups/hearwell-vps
echo test > ~/backups/hearwell-vps/hearwell-db-20200101-0300.dump
touch -t 202001010300 ~/backups/hearwell-vps/hearwell-db-20200101-0300.dump
bash ~/bin/hearwell-pull-backups.sh; echo "exit=$?"
ls -l ~/backups/hearwell-vps
tail -1 ~/Library/Logs/hearwell-backup-pull.log
```

做對了會看到：

- `exit=0`。
- 清單裡**沒有** `hearwell-db-20200101-0300.dump`，有 VPS 上最新的幾份。
- 11/6 那幾份也不見了：它們已經超過 8 天，這是預期的。
- `hearwell-before-0029.dump` 還在：它不是 `hearwell-db-日期.dump`，腳本不動它（第 2 段由你自己刪）。
- 最後一行是「成功：最新一份是 hearwell-db-…，刪了 N 份超過 8 天的。」

再試一次通知（故意連到不存在的主機，1 秒後重試，大約 5 秒跑完）：

```bash
HEARWELL_BACKUP_SOURCE=nosuchhost.invalid:backups/ HEARWELL_BACKUP_RETRY_SECONDS=1 bash ~/bin/hearwell-pull-backups.sh; echo "exit=$?"
```

做對了會看到：`exit=1`，右上角跳出「聽伴備份：失敗：連不上 VPS…」。

- 第一次 macOS 可能問要不要讓「指令碼編輯程式」發通知：按允許。
- 沒有跳通知的話：系統設定 → 通知 → 指令碼編輯程式 → 打開「允許通知」，再跑一次。
- 這次測試會在紀錄檔多一行「失敗」，是正常的。

### 1-4 排程

整段貼進終端機。這次 `<<EOF` 沒有單引號，`$HOME` 會先換成你的家目錄（launchd 的設定檔不認 `~`）：

```bash
cat > ~/Library/LaunchAgents/hearwell.backup-pull.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>hearwell.backup-pull</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$HOME/bin/hearwell-pull-backups.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>12</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/hearwell-backup-pull.err.log</string>
</dict>
</plist>
EOF
plutil -lint ~/Library/LaunchAgents/hearwell.backup-pull.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/hearwell.backup-pull.plist
```

- `RunAtLoad`：登入時跑一次；`bootstrap` 這一下也算「載入」，所以會馬上跑一次。
- `StartCalendarInterval`：每天 12:00。Mac 在睡眠的話，醒來時補跑（`man launchd.plist`：launchd 跟 cron 不同，會在醒來時補）；關機的那幾天由登入那一次補。
- `StandardErrorPath`：rsync、ssh 的錯誤訊息寫在這裡，失敗時查原因用。
- macOS 可能跳「已加入背景項目」的通知，是正常的。
- 出現 `Bootstrap failed: 5: Input/output error`：排程已經載入過了。要重來（例如改了設定檔）就先 `launchctl bootout gui/$(id -u)/hearwell.backup-pull`，再跑一次 `bootstrap` 那一行。

確認（等 10 秒左右再看）：

```bash
plutil -lint ~/Library/LaunchAgents/hearwell.backup-pull.plist
launchctl print gui/$(id -u)/hearwell.backup-pull | grep -E 'state|last exit code'
tail -1 ~/Library/Logs/hearwell-backup-pull.log
```

做對了會看到：`OK`；`last exit code = 0`；最後一行是剛剛的「成功」。

### 1-5 下次登入時再看一次（#567 驗收）

登出再登入（或重開機），等一分鐘：

```bash
tail -2 ~/Library/Logs/hearwell-backup-pull.log
ls -lt ~/backups/hearwell-vps | head -3
```

做對了會看到：紀錄檔有今天、登入那個時間的「成功」；資料夾最上面是 VPS 最新的那一份。

### 換新 Mac、要停掉排程時

- 換新 Mac：在新的 Mac 上重做 1-1 到 1-4，再把舊 Mac 的 `~/backups/hearwell-vps` 用「清除磁碟」處理掉。
- 暫停排程：`launchctl bootout gui/$(id -u)/hearwell.backup-pull`；恢復：重跑 1-4 的最後一行 `launchctl bootstrap …`。
- 看最近十次的結果：`tail -10 ~/Library/Logs/hearwell-backup-pull.log`。

---

## 2. 刪手動備份（#567）

手動備份＝備份資料夾裡，檔名**不是** `hearwell-db-日期.dump` 的檔案（例如 `hearwell-before-0029.dump`）。它們不會被自動刪，會一直留著超過隱私權說明承諾的 10 天。刪了就救不回來，每個檔名看清楚再按 Enter。

### 2-1 VPS

```bash
ssh hearwell-vps 'ls -l ~/backups | grep -v "hearwell-db-.*\.dump$"'
```

會看到：要刪的手動備份（第一行 `total` 不用管）。每一個照下面刪，`<檔名>` 換成清單上的名字：

```bash
ssh hearwell-vps 'rm ~/backups/<檔名>'
```

再列一次：

```bash
ssh hearwell-vps 'ls ~/backups'
```

做對了會看到：只剩 `hearwell-db-日期.dump`。

### 2-2 Mac

```bash
ls -l ~/backups/hearwell-vps | grep -v 'hearwell-db-.*\.dump$'
```

每一個照下面刪：

```bash
rm ~/backups/hearwell-vps/<檔名>
```

```bash
ls ~/backups/hearwell-vps
```

做對了會看到：只剩 `hearwell-db-日期.dump`。

做完第 1、2 段，把 1-5 和 2-1、2-2 最後一次列出的結果告訴代理，代理寫進驗證紀錄。

---

## 3. 還原演練（#568）

照 [還原文件](restore.md) 的「演練」段做。要先做完第 1、2 段：演練用的是排程拉回來的最新一份。

---

## 4. 從正式站走一次忘記密碼（#565）

確認 2026-11-14 之後改過的 `.env` 沒有弄壞寄信（[拷問決定](../planning/found-by-family/closing-grill-decisions.md) Q9）。約 2 分鐘。

1. 用一般瀏覽器（不用私密視窗也可以）打開 `https://tingpal.tw/login`，按「忘記密碼？」。
2. 輸入自己帳號的信箱，送出。
3. 打開信箱。

做對了會看到：

- 幾分鐘內收到信，寄件人是「聽伴」，在收件匣、不在垃圾信件匣。
- 按信裡的按鈕能設新密碼，設好後直接登入網站。

把結果（幾分鐘收到、在哪個資料夾、能不能設好）告訴代理，代理寫進驗證紀錄。

---

## 5. 設定 Sentry 監控（#569）

運作檢查（#562）合併、部署到正式站之後補上這一段。

## 6. 兩次停機測試（#569）

跟第 5 段一起補上。
