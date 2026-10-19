# IOI-HA 審查結果（2026-10-15）

規格：[phase4_ioi_ha.md](../../specs/phase-04/phase4_ioi_ha.md)。審查者：沒參與實作的 subagent（唯讀，另用測試資料庫跑探測測試）；以下每項由主流程查證後分類。

審查時全套測試 180 個通過，`makemigrations --check` 無變更。

## 要修

### 1. `norm_basis` 用 PROTECT，同一位使用者的紀錄無法一起刪除（中）→ 已修
- 位置：`screening/models.py`（`Submission.norm_basis`）
- 查證：審查者用測試資料庫實測，`Submission.objects.filter(user=u).delete()` 會丟 `ProtectedError`。這符合 Django 文件：PROTECT 連「引用者也在同一批刪除」都擋；RESTRICT（Django 3.1 起）才允許這種情況。
- 理由：已知陷阱寫著「之後必須處理使用者刪除自己的健康資料」。PROTECT 會讓那件事多一道障礙；RESTRICT 仍然擋「只刪 HHIE-S、留下 IOI-HA」，但允許整批刪除。
- 做法：改成 `on_delete=models.RESTRICT`；0017 還沒上線，直接重新產生。補一個測試：同一位使用者的全部紀錄可以一起刪除，只刪 HHIE-S 則被擋。

### 2. 結果頁的 `<h1>` 沒寫是哪個量表（低，無障礙）→ 已修
- 位置：`screening/templates/screening/result_ioi_ha.html`
- 查證：h1 是「常模組別：…」，量表名稱只在 `<title>`。用標題跳讀的報讀器使用者聽不到這是 IOI-HA 結果。
- 做法：h1 改「IOI-HA 結果」，「常模組別：…」改成下一行的段落（文字不變，既有測試照樣通過）。

## 補測試

### 3. 結果頁只驗了「輕度至中度」組（低）→ 已補
- 查證：兩組的三種比較在 `compare_to_norm` 的單元測試都有；頁面測試只有輕度至中度組。
- 做法：加一個「中重度以上」組的結果頁測試，確認頁面用的是該組常模（同一個答案在兩組會得到不同標示）。

## 不改

### 4. fixture 固定 pk 2、11–17（中）
- 本人已在正式站 admin 確認只有 HHIE-S（pk 1）和 10 題（2026-10-15，計畫 Q4）。

### 5. 常模表沒有版本號（低）
- 規格第 3 節的原則是「第一次修改之前」先做版本號，現在不需要。列入收尾的 decisions 素材，建議跟 `THRESHOLDS` 一起寫進已知陷阱。

### 6. IOI-HA 分數若是 0，結果頁會顯示最後一個選項（低）
- 只有繞過表單才會發生；admin 不能新增或修改 Answer。加防呆屬於「不需要的程式碼」。

### 7. 判斷「是不是 IOI-HA」的依據不一致（低）
- 作答頁看 `questionnaire.code`，結果與歷史頁看 `norm_group`。IOI-HA 送出時一定會存組別（`ioi_ha_group()` 不會回傳空字串），HHIE-S 一定是空字串，兩者目前等價。

### 8. 作答頁說明比規格多一句、「兩週」與「兩周」（低）
- 說明文字是本人在計畫 Q3 同意的。題目照書逐字用「兩周」；說明文字用台灣常用的「兩週」。本人決定不統一（2026-10-15）。

### 9. 比較標示放在括號裡、不夠突出（低）
- 規格只要求文字標示（不只靠顏色），已做到；視覺強化等本人看過畫面再決定。

### 10. 其他低風險觀察
- 歷史頁排序只有 `-created_at`（既有寫法），驗收 17 的測試靠兩次送出的時間差，實務上不會同一微秒。
- 驗收 22 的首頁按鈕與導覽列由既有測試涵蓋；驗收 20 的分級與建議由既有測試涵蓋。

## 審查者確認沒問題的部分
- 第 8 條（只查 `request.user`）、第 9、10 條（規則式、單一計分路徑）、第 11 條（0 分屬輕度至中度、「未分組」獨立值），都有測試。
- 題目順序打亂、把 HHIE-S 題目送到 IOI-HA 網址、HHIE-S 送 1／3／5、同時建立的紀錄：都不會存錯或 500。
- migration 對既有正式資料安全；沒有違反「不做」清單。

## 修改後（2026-10-15）
- 測試：`test_user_records_delete_together_but_basis_not_alone`（試驗確認改回 PROTECT 時會失敗）、`test_result_page_uses_moderately_severe_norms`（含 h1）。
- Django 182 個、前端 27 個全部通過；`makemigrations --check` 無變更；ruff 通過。
