# 從備份還原資料庫

[回部署參考](README.md)

兩段：

- **演練**：每年做一次，確認備份救得回來。2026-11 第一次照這份文件做（#568），之後每年 10 月、Postgres 升大版本或換 Mac 之後再做（roadmap「時間型待辦」）。
- **真的出事時**：VPS 整台救不回來時的順序。**這一段沒有演練過**，只列順序，細節指向 VPS 筆記。

決定見[收尾拷問決定](../planning/found-by-family/closing-grill-decisions.md) Q4–Q8；備份怎麼來的見[收尾清單](closing-checklist.md)第 1 段與 ADR 0042。

## 代稱

這份文件在公開的 repo 裡，主機位址、帳號都用代稱。照做前先把真的值查好，指令裡的 `<…>` 換掉。

| 代稱 | 是什麼 | 真的值去哪裡查 |
|---|---|---|
| `hearwell-vps` | Mac 的 `~/.ssh/config` 裡的 VPS 代稱 | [收尾清單](closing-checklist.md)開頭的代稱表與 1-1 |
| `<網站資料夾>` | VPS 上的程式碼資料夾 | `vpsdeploy.md`「Gunicorn 與 systemd」的 `WorkingDirectory` |
| `<正式資料庫名稱>`、`<正式資料庫使用者>` | VPS 上 PostgreSQL 的資料庫與使用者 | `ssh hearwell-vps 'cut -d: -f3,4 ~/.pgpass'`，印出「名稱:使用者」（不印密碼） |
| `<容器名稱>` | Mac 上跑 PostgreSQL 的 Docker 容器 | `docker ps --format '{{.Names}}  {{.Image}}'`，IMAGE 是 `postgres:…` 的那一個 |
| `<本機資料庫使用者>` | 容器裡的資料庫使用者 | `docker exec <容器名稱> printenv POSTGRES_USER`（只印這一個，不用 `env`，免得印出密碼） |
| `<本機 DATABASE_URL>` | 本機網站平常連的資料庫網址 | repo 主資料夾 `.env` 的 `DATABASE_URL=` 那一行 |

---

## 演練

模擬「VPS 整台壞掉，只剩 Mac 上的備份」：拿排程拉回來的最新一份，還原到 Mac Docker 裡**另建**的測試資料庫 `hearwell_restore_test`，比對數字，讓本機網站暫時接上它登入看一次，最後刪掉。約 30 分鐘。

**絕對不還原到開發資料庫或正式資料庫。** 整個演練只有第 4 步會連到正式資料庫，而且只讀（`SELECT`）。

### 0. 準備

1. 打開 Docker Desktop，確認容器在跑：`docker ps` 看得到 `<容器名稱>`。
2. 正式站跑的程式要跟本機 `main` 同一版，第 5 步登入時畫面才對得上。在 repo 主資料夾：

   ```bash
   git fetch origin && git log -1 --format='%h %s' origin/main
   ssh hearwell-vps 'git -C <網站資料夾> log -1 --format="%h %s"'
   ```

   做對了會看到：兩行的 commit 編號（前 7 碼）一樣。不一樣的話，先照平常的方式把正式站部署到最新 `main`，或等下次部署後再演練。

3. 主資料夾切到最新 `main`：`git switch main && git pull`。
4. 關掉平常在跑的本機開發伺服器（第 5 步會用 8002 埠，避開平常的 8000 和預覽用的 8001）。

### 1. 選備份

```bash
ls -lt ~/backups/hearwell-vps | head -3
```

做對了會看到：最上面是 `hearwell-db-日期-時間.dump`，日期是今天或昨天。

記下它的檔名，和檔名裡的時間，例如 `hearwell-db-20261117-0300.dump` → `2026-11-17 03:00`。下面的 `<備份檔>`、`<備份時間>` 換成這兩個。檔名裡的時間是台灣時間：VPS 的備份腳本用 `TZ=Asia/Taipei` 產生檔名，整台主機仍是 UTC（`vpsdeploy.md`「備份腳本」的「檔名用台灣時間」）。

### 2. 建測試資料庫

```bash
docker exec <容器名稱> createdb -U <本機資料庫使用者> hearwell_restore_test
docker exec <容器名稱> psql -U <本機資料庫使用者> -l
```

做對了會看到：清單裡多了 `hearwell_restore_test`。原本的開發資料庫還在，沒被動到。

### 3. 還原

```bash
docker exec -i <容器名稱> pg_restore -U <本機資料庫使用者> -d hearwell_restore_test --no-owner --no-privileges < ~/backups/hearwell-vps/<備份檔>
echo "exit=$?"
```

做對了會看到：沒有 `error` 開頭的訊息，接著 `exit=0`。

- `-i` 讓容器收得到 `<` 灌進去的檔案；用 `<` 而不是 `docker cp`，容器裡不會多留一份健康資料。
- `--no-owner`、`--no-privileges`：備份裡記的擁有者是正式站的資料庫使用者，Mac 上沒有這個角色；不加會一直出現 `role "…" does not exist`。
- 出現 `unsupported version` 之類的訊息：Mac 容器的 PostgreSQL 版本比 VPS 舊。`docker ps` 看 IMAGE，要跟 VPS 同一個大版本（目前都是 18）。

### 4. 比對數字

先把要比的四個數字寫成一個檔。貼進終端機之前，先把 `<備份時間>`（兩處）換成第 1 步記下的時間，例如 `2026-11-17 03:00`：

```bash
cat > /tmp/hearwell-compare.sql <<'EOF'
SELECT
  (SELECT COUNT(*) FROM screening_questionnaire) AS questionnaires,
  (SELECT name FROM django_migrations WHERE app = 'screening' ORDER BY id DESC LIMIT 1) AS latest_migration,
  (SELECT COUNT(*) FROM screening_user WHERE date_joined < '<備份時間>+08') AS users,
  (SELECT COUNT(*) FROM screening_submission WHERE created_at < '<備份時間>+08') AS submissions;
EOF
```

同一個檔各跑一次，一次在還原的資料庫、一次在正式資料庫：

```bash
docker exec -i <容器名稱> psql -U <本機資料庫使用者> -d hearwell_restore_test -At < /tmp/hearwell-compare.sql
ssh hearwell-vps psql -h localhost -U <正式資料庫使用者> -d <正式資料庫名稱> -At < /tmp/hearwell-compare.sql
```

做對了會看到：兩行一模一樣，格式是 `問卷數|最新 migration|使用者數|作答筆數`，例如 `6|0035_signinmethod_line|…|…`。

- 使用者數、作答筆數只算**備份時間以前**建立的，所以備份之後有人註冊、作答，兩邊照樣一樣。
- 正式站比較少：備份之後有人刪了帳號（刪帳號會連作答一起刪）。照時間算，差的應該就是那幾個。
- 最新 migration 不一樣：備份之後部署過新的 migration。回到第 0 步，等下一份備份再做。
- `+08` 是台灣時區；少了它，資料庫會把時間當成 UTC，差 8 小時。
- 正式資料庫那一行靠 VPS 上的 `~/.pgpass` 不用輸密碼；這一行只有 `SELECT`，不會改到任何東西。

### 5. 讓本機網站暫時接上還原的資料庫

在 repo 主資料夾。把 `<本機 DATABASE_URL>` 最後一段的資料庫名稱換成 `hearwell_restore_test`，其他照抄：

```bash
DATABASE_URL=postgres://…/hearwell_restore_test py313/bin/python manage.py runserver 8002
```

- 環境變數寫在指令前面，只對這一次執行有效；`.env` 不會被改，網站讀環境變數時以指令前面這個為準（`load_dotenv` 不蓋掉已經有的）。
- 啟動訊息出現 `You have N unapplied migration(s)`：本機程式比備份新。不要跑 `migrate`，回到第 0 步確認兩邊是同一版。

打開 `http://localhost:8002/login`，用**自己在正式站的帳號密碼**登入（本機沒有 Google、LINE 的金鑰，只能用帳號密碼），打開「紀錄」。

做對了會看到：登入成功；紀錄裡的問卷、聽力圖跟正式站上看到的一樣（備份時間以後做的不會有）。

- 頁面沒有樣式：主資料夾的前端沒建置過，先 `npm run build --prefix frontend` 再重開。
- 被帶到同意頁：本機程式的同意書版本比正式站新，代表兩邊不是同一版，回到第 0 步。

看完在終端機按 Ctrl+C 關掉。

### 6. 刪測試資料庫

```bash
docker exec <容器名稱> dropdb -U <本機資料庫使用者> hearwell_restore_test
docker exec <容器名稱> psql -U <本機資料庫使用者> -l
rm /tmp/hearwell-compare.sql
grep -c hearwell_restore_test .env
```

做對了會看到：

- 清單裡沒有 `hearwell_restore_test` 了，開發資料庫還在。
- 最後一行是 `0`：`.env` 裡沒有 `hearwell_restore_test`，平常的設定沒被改（這樣查不會把資料庫密碼印在畫面上）。

`dropdb` 不會再問、刪了救不回來，按 Enter 前再看一次名稱是 `hearwell_restore_test`。出現 `is being accessed by other users`：第 5 步的網站還沒關。

### 7. 記錄

把第 1 步的檔名、第 3 步的 `exit=`、第 4 步的兩行、第 5 步看到的畫面告訴代理，寫進 `docs/verification/`。

---

## 真的出事時（沒有演練過）

只在 VPS **整台救不回來**時走這一段。網站或資料庫只是停了，重新啟動就好（[收尾清單](closing-checklist.md)第 6 段停機測試的恢復步驟）。

資料只能回到最新一份備份的時間：每天 03:00 一份，最多少掉約 1 天的資料（RPO，最多能接受遺失多少資料）。

| 順序 | 做什麼 | 細節在哪裡 |
|---|---|---|
| 1 | 確認是整台壞了：Vultr 後台看主機狀態，試 `ssh hearwell-vps` | — |
| 2 | 在 Vultr 開一台新主機（同樣東京機房，隱私權說明寫的是日本東京） | `vpsdeploy.md`「總覽」 |
| 3 | 照部署筆記重做：SSH 金鑰、主機安全、PostgreSQL（建同名的資料庫與使用者）、程式碼與 Python、Gunicorn 與 systemd、Nginx | `vpsdeploy.md` 同名各段 |
| 4 | 重建 `.env`：`.env` 沒有備份，金鑰到各家後台重新取得（Google、LINE、Resend、Sentry）；`SECRET_KEY` 換新的，所有人要重新登入 | `docs/deployment/README.md`、`vpsdeploy.md`「密鑰輪替」 |
| 5 | 把 Mac 上最新一份備份傳上去，還原到正式資料庫（`pg_restore`，帶 `--no-owner`），再跑 `migrate`、`createcachetable`、`check --deploy` | 本文件「演練」第 3 步、`vpsdeploy.md`「build、collectstatic、migration」 |
| 6 | Gandi 的 DNS 改指新主機的 IP，等生效後重新申請 HTTPS 憑證 | `vpsdeploy.md`「DNS（Gandi LiveDNS）」「HTTPS（certbot）」 |
| 7 | 重建每日備份、每日清除提問紀錄的排程；Mac 的 `~/.ssh/config` 改新 IP | `vpsdeploy.md`「每日備份」「每日清除 90 天前的提問紀錄」 |
| 8 | 確認：Sentry 監控恢復、自己登入看得到紀錄、Mac 下一次拉備份成功 | [收尾清單](closing-checklist.md) |

- 第 4 步那些金鑰、第 6 步的 DNS 都在本人的帳號裡，代理做不到。
- 備份之後、出事之前的作答與註冊會不見，要不要、怎麼告訴使用者，到時由本人決定。
