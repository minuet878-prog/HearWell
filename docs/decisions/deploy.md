# 部署與環境

← [回到索引](README.md)

---

## 2026-09-24 本機改用 PostgreSQL（Docker）

- 本機一直是 SQLite，正式環境是 PostgreSQL 18。兩邊的型別寬鬆度、大小寫比對、鎖定方式都不同，有些 bug 只會在上線後出現。
- 用 Docker 跑 `postgres:18`，版本跟 Render 一致。port 只綁 `127.0.0.1`，資料存在 named volume。
- 坑：PostgreSQL 18 的映像檔改了資料目錄，volume 要掛 `/var/lib/postgresql`，舊教學的 `/var/lib/postgresql/data` 會出問題。
- 坑：`DATABASE_URL` 的主機寫 `127.0.0.1` 不寫 `localhost`，`localhost` 可能先試 IPv6，容器只綁了 IPv4。

---

## 2026-09-24 拿掉 SQLite 退路，缺 DATABASE_URL 直接報錯

- 原本讀不到 `DATABASE_URL` 會默默退回 SQLite，可能好幾天都沒發現在用錯的資料庫。
- 改用 `parse()` 搭配自己的檢查：環境變數只讀一次，缺少就拋 `ImproperlyConfigured`。
- 坑：`config()` 的參數是環境變數的**名稱**，不是網址本身。傳錯不會報錯，只會安靜回傳空 dict。
- 暫存變數用小寫 `database_url`。大寫會變成 Django 設定，而 `DATABASE_URL` 不在除錯頁的遮蔽名單裡，密碼會被印出來。

---

## 2026-10-01 Render網頁回server error(500)

- 在確認render網頁狀況時回server error請claude發request卻是正常(200)，後來發現是因為瀏覽器帶著session去request但因為資料庫
  已經expired了所以查不到資料回server error
- 解決方法:原本考慮是否要定時重置render提供的postgre資料庫(需定時檢查 容易有問題)或升級付費方案(無真實使用者故無需求)最後決定使用
  其他平台(neon)提供的免費postgre資料庫方案並且伺服器與render同區(ohio)
- 坑：在貼上Neon的DATABASE_URL參數時把引號也寫進去了，但因為render解析時是直接拿整個字串所以報錯，把引號去掉就可以了
- 坑：migrate完成之後發現questionnaire_list頁面沒有東西，發現是因為沒有跑loaddata後來將fixture的json檔放到新建的/screening/fixtures
  資料夾中(讓django自己去讀)並且在build.sh裡面新增`python manage.py loaddata questions_fixture.json`指令即可正常顯示
