這是一份現職為聽力師想要轉職軟體工程師的人的side project請依照現職人員的要求給我建議
並且最好可以與底層概念相連（比如資料結構/演算法...等）

專案：HearWell — 聽力健康自我照護工具

目前進度：

Django 5.2 + Python 3.13，專案名 config，app 名 screening
資料模型完成並 migrate：User（繼承 AbstractUser + birth_date）、Questionnaire、Question、Submission、Answer
Admin 設好：CustomUserAdmin（含 birth_date）、QuestionAdmin（list_display）、QuestionnaireAdmin（TabularInline）
HHIE-S 題目已輸入 admin
Shell 驗證通過：關聯查詢、aggregate 計分、E/S 分項 filter 都能跑
Ruff 設好（pyproject.toml）、Bootswatch Minty 主題
layout.html 建好（導覽列、container）
正在寫 login view 和 template

接下來要做：

完成登入/登出/註冊（註冊要收 birth_date）
問卷作答頁面
計分邏輯（總分 + E/S 分項）
歷史紀錄頁

## 常用指令
- `python manage.py runserver` — 啟動開發伺服器
- `python manage.py makemigrations screening` — 產生 migration
- `python manage.py migrate` — 套用 migration
- `python manage.py shell` — Django shell
- `python manage.py test` — 跑測試
- `ruff check --fix .` — 檢查並修正格式

## 專案結構
- config/ — Django 專案設定（settings.py, urls.py）
- screening/ — 主要 app（models, views, templates）
- py313/ — 虛擬環境（不進版控）
- pyproject.toml — Ruff 設定

## 資料模型
- User（AbstractUser + birth_date）
- Questionnaire → 多個 Questions（ForeignKey）
- User → 多個 Submissions（ForeignKey）
- Questionnaire → 多個 Submissions（ForeignKey）
- Submission → 多個 Answers（ForeignKey）
- Answer → Question（ForeignKey）
- 每題答案存成一列（正規化），不是欄位
- 計分用 aggregate(Sum) + filter(question__category)

## 設計決策
- 使用者引用用 settings.AUTH_USER_MODEL，不直接寫 User
- birth_date 允許 null（註冊時不強制）
- 總分不另存欄位，每次從 answers 即時計算
- HHIE-S 和 HHIA-S 共用同一組表，靠 questionnaire 欄位區分
- category 欄位區分 emotional / social 分項
- aggregate(Sum) 遇到空 submission 會回傳 None，計分邏輯要處理

## 目標使用者
- 台灣的聽損患者及其家屬
- 年齡層偏高（65+），介面要清楚、字體要大
- 繁體中文介面
- 量表內容基於 HHIE-S（65歲以上）和 HHIA-S（65歲以下）

重要提醒： 用 Plan Mode（Shift+Tab 切換）。Jason 正在學習，要引導不要直接給程式碼。
重要：不要直接寫程式碼給我。用問題引導我思考，讓我自己寫。只在我寫完之後指出錯誤。