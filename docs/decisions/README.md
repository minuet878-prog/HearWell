# 技術決策紀錄（索引）

紀錄開發過程中「想清楚但容易忘記」的技術決定

照主題分檔，每個檔內照時間排。新條目放進最相關的主題檔，並在下面的時間清單補一行。

## 主題

- [計分與分級](scoring.md)（7 則）
- [作答與驗證](answering.md)（3 則）
- [資料模型與資料完整性](data-integrity.md)（2 則）
- [帳號與安全](security.md)（4 則）
- [部署與環境](deploy.md)（3 則）
- [開發工具與流程](tooling.md)（4 則）
- [畫面與產品內容](product-ui.md)（4 則）
- [架構方向](architecture.md)（0 則）

## 依時間

- 2026-08-31 用 Django Formset 取代手動 POST 驗證迴圈 → [作答與驗證](answering.md)
- 2026-08-31 密碼相似度驗證器悄悄失效 → [帳號與安全](security.md)
- 2026-08-31 Python 巢狀 class 的作用域陷阱 → [開發工具與流程](tooling.md)
- 2026-09-01 models CheckConstraints 及 on_delete參數 → [資料模型與資料完整性](data-integrity.md)
- 2026-09-01 SECRET_KEY 從「安靜使用不安全預設值」改成「正式環境缺少就報錯 → [帳號與安全](security.md)
- 2026-09-01 計分邏輯收斂到 Submission model → [計分與分級](scoring.md)
- 2026-09-02 [待定] 問卷適用條件的通用設計（年齡限制等） → [畫面與產品內容](product-ui.md)
- 2026-09-02 login/register 改成繼承 layout → [畫面與產品內容](product-ui.md)
- 2026-09-02 register 表單沒有必填檢查，空 username 直接 500（順手測到的 bug） → [帳號與安全](security.md)
- 2026-09-02 classify() 拆掉呈現層，加 template filter 轉顏色 → [計分與分級](scoring.md)
- 2026-09-02 三次分數查詢合併成一次 conditional aggregation → [計分與分級](scoring.md)
- 2026-09-07 加上行動建議 → [畫面與產品內容](product-ui.md)
- 2026-09-09 default=0 的坑第三次，改用 filter= → [計分與分級](scoring.md)
- 2026-09-21 清掉 shell 外洩到正式 DB 的測試資料 → [資料模型與資料完整性](data-integrity.md)
- 2026-09-23 ruff 排除 migrations → [開發工具與流程](tooling.md)
- 2026-09-23 Git 流程：main 分岔 → [開發工具與流程](tooling.md)
- 2026-09-23 ruff 擴充規則集（B / DJ / TID / RUF） → [開發工具與流程](tooling.md)
- 2026-09-24 本機改用 PostgreSQL（Docker） → [部署與環境](deploy.md)
- 2026-09-24 拿掉 SQLite 退路，缺 DATABASE_URL 直接報錯 → [部署與環境](deploy.md)
- 2026-09-24 DEBUG 預設改成 False → [帳號與安全](security.md)
- 2026-10-01 修復空的Submission → [作答與驗證](answering.md)
- 2026-10-01 Render網頁回server error(500) → [部署與環境](deploy.md)
- 2026-10-05 Screening驗證邏輯搬到forms → [作答與驗證](answering.md)
- 2026-10-14 classify() 改門檻表 → [計分與分級](scoring.md)
- 2026-10-14 歷史頁 N+1、分數收成一條路 → [計分與分級](scoring.md)
- 2026-10-14 快照決策（1-5） → [計分與分級](scoring.md)
- 2026-10-14 取消 A3 分項解讀，結果頁改成註明 → [畫面與產品內容](product-ui.md)
