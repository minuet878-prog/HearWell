# 刪掉重複的 e2e 測試（A 表，小改動，無 issue）

日期：2026-11-17。基準：`origin/main`（`0c6a0251`）；分支：`test/e2e-prune-duplicates`。

狀態：本機核對證據、受影響的類別通過；CI 待跑。只刪 e2e 測試，沒碰產品程式、計分、門檻、資料 migration、權限，
不需交叉審查。未操作真實資料；沒有啟動開發伺服器。

## 為什麼做

本人問 e2e 有沒有舊的測試可以刪（前端改過很多次）。三個子代理分段掃描，結果和分級在
`docs/planning/e2e-pruning-candidates.md`；本人決定只刪 A 表（高信心）。

## 刪之前的核對

A 表 30 條，主代理逐條讀過被刪的測試和「已經測過它」的那一方：

- **後端已有**：
  - 結果頁標題與 `aria-describedby`：`test_accessibility.py:32`。
  - 歷史紀錄卡：`test_accessibility.py:90`。
  - 分享頁按鈕的 `hidden`、加到主畫面的原生 `<details>`：`test_share_page.py:175`、`test_add_to_home.py:72`。
  - 了解頁卡片：`test_learn.py`。
  - 紀錄切換的連結：`test_records_switch.py:57`、`:70`。
  - 語言香蕉圖頁尾：`test_speech_banana.py:384`、`:418`、`:424`。
  - 頁尾複製信箱：`test_layout.py:295` ＋ `site.css` 的 `[hidden]{display:none !important}`。
  - 家人專區網址：`test_family_guide.py:254`。
  - 助聽器頁、適應頁的錨點與指引連結：`test_family_hearing_aids.py:185–204`、`test_family_adjusting.py:114`。
  - 期限試算（伺服器 POST）：`test_family_deadlines.py`。
  - 訪客沒有 JavaScript：`test_guest.py:503`。
  - 意見回饋從頁尾送出、回原頁：`test_feedback.py:82–143`。
- **別的 e2e 已測**：
  - 200% 字級的首頁、家人專區、了解、紀錄、聽力圖、分享設定：WhiteCardRuleTest 的頁面清單（用 CUT_OFF，比只量頁面寬度嚴）、
    SharedLayoutTest :2647、RecordsT465。
  - 家人專區每個入口 ≥44 px：FamilyZoneHomeTest :4331。
  - SlidingPill 的一般速度版本：同類別慢手機版，同兩個切換器各來回 3 次。
  - 遮蔽開關的橘色：MaskingSwitchTest `assert_state`。
  - 卡片列：WhiteCardRuleTest `assert_list_row`。
  - 緊急就醫框和 119：WhiteCardRuleTest 家人專區的測試。
  - SSQ12 最低題的字重：WhiteCardRuleTest :8969。
- **互相引用**：有幾條拿另一條也要刪的測試當證據，例如 FamilyReluctant／FamilyHearingAids 引用 WhiteCard :8294。
  逐一確認刪完每一頁仍有測試守：家人專區 200% 由了解頁清單和 SharedLayout :2647 守，了解頁由了解頁清單和 T469 守。

### 兩條調整

- ColourOnlyFeedbackTest 的「表格不被藍邊蓋住」：子代理說它過時，但它還在驗「摺疊沒有左邊框、表格在摺疊內」。
  表格在摺疊內已由 StyleInBrowserTest :5482 驗得更嚴（寬度等於摺疊內容寬）；只剩的左邊框是 #465 已拿掉的藍邊。照樣刪，
  歸為「重複」。
- WhiteCardRuleTest 的家人專區 200%：「已登入」那一頁只有它用 CUT_OFF 量（SharedLayout 只量頁面寬度），所以把
  `("family guide, signed in", True, "/family")` 加進 `WHITE_CARD_PAGES_LEARN` 再刪，檢查範圍不變。

## 改了什麼

- `e2e/main_flow.py`：
  - 刪 31 個測試（含 LearnPageTest、GuestWithoutJavaScriptTest 整個類別），共少約 430 行。
  - 只被刪掉的測試用到的 `Feedback` import 和 `FeedbackTest.footer_links` 一併清掉。
  - FeedbackTest 的說明改成它現在測的內容。
  - 刪掉的註解逐行看過，都是被刪測試自己的。
- `e2e/durations.json`：拿掉不存在的 LearnPageTest、GuestWithoutJavaScriptTest。
- `docs/planning/e2e-pruning-candidates.md`：候選清單（B、C 表留待以後決定）。

## 驗收對照

| 需求 | 驗證 | 證據 |
|---|---|---|
| 只刪 A 表 | ✅ 比對 | 用 AST 比對前後：501 → 470 項，刪 31、加 0，名單與 A 表一致 |
| 刪的都有別處守 | ✅ 逐條核對 | 上方「刪之前的核對」 |
| 沒留下沒人用的程式 | ✅ 檢查 | Ruff 抓到的 `Feedback` 已清；掃描受影響類別的輔助方法，只有 `footer_links` 沒人用，已清 |
| 三台分組仍正確 | ✅ 本機執行 | 不分組 472 項；1/3＋2/3＋3/3 = 153＋166＋153 = 472 |
| 受影響的類別照樣通過 | ✅ 本機執行 | 改到的 17 個類別（`--parallel 4`）：188 項 164 秒 OK |
| CI 通過 | ⏳ 等 PR 的 CI | |

## 測試與審查

- `ruff check e2e`、`ruff format --check e2e`：全過。
- 自審：看過 diff，沒有要修的項目。
