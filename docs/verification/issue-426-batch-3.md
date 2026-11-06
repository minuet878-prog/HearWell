# 家人專區第三批（#426，票 #433–#435）

日期：2026-11-06。分支：`feat/426-family-zone-batch-3`。規格：[#426](https://github.com/minuet878-prog/HearWell/issues/426)；拷問決定：[family-zone](../planning/family-zone/grill-decisions.md)；審字清單：[第三批文字](../planning/family-zone/batch-3-wording.md)；線條圖：[第二版](../planning/family-zone/batch-3-drawings.html)。

狀態：自動測試與自審都完成，本人決定略過交叉審查。**本人審字與操作驗收還沒做**，所以驗收條件「文字由本人審過」和「線條圖本人已逐張確認」還不算通過。

## 本人決定

1. 頁面一頁三段（Q20）；線條圖要畫得更像，用第二版；洗耳模照 RNID 的步驟。
2. 共用的點選看說明按上一頁時選項不還原（Q21）。耳內第 4 步寫出完整文字；保養加「勾選不會留下，換外型也會清掉。」；助聽器頁加和長輩頁相同的免責句。
3. 就醫提醒（Q22）：自審指出可能延誤就醫後，沒聲音的選項開頭先寫何時要就醫，嗡嗡聲加「拿下助聽器還是聽得到」，會磨和不想再戴都先提醒耳朵痛或流膿。
4. **交叉審查略過：** 這批改了 `OPEN_PAGES`（多放行一個不含個人資料的頁面），也改了第一批的共用元件，屬於 `AGENTS.md` 要做交叉審查的權限改動，本人決定略過。

## 修掉的 bug

點選看說明：離開再按上一頁，選項還是選中，說明卻是空的，再點同一項也沒反應。`/family`、`/family/reluctant` 已上線，也都重現。

- 根本原因：Chromium 在 `pick-explain.js` 檢查過後才還原單選，也不發 `change`。
- 修法：單選加 `autocomplete="off"`。回來時選項是空的，要重選。
- 證據：`PickExplainBackTest` 修前在三個頁面都失敗（`Locator expected not to be checked`），修後通過。只驗了 Chromium。

## 做了什麼

- 新公開頁 `/family/hearing-aids`：助聽器怪怪的（6 個狀況，要就醫的放第一個）、陪長輩適應（3 個階段）、日常保養（2 種外型，共 9 步，每步有文字、線條圖和勾選框）。
- 專區首頁加入口卡。連到配戴效果問卷時只查問卷，不讀 `request.user`。
- `screening/family_zone.py` 放內容；`Option` 加 `sections`、`urgent`、`links`、`steps`、`steps_note`。線條圖在 `screening/templates/screening/family/care_drawings/`。

## 驗收條件

| 條 | 驗收 | 結果 | 證據 |
|---|---|---|---|
| 30 | 選狀況看到先檢查與該找聽力師，沒有廠牌，提醒各廠牌不同 | 通過 | `test_family_hearing_aids.py`、e2e `FamilyHearingAidsTest` |
| 31 | 耳朵痛、流膿或突然聽不到，請人就醫，連到 `/family#urgent-title`，不列檢查 | 通過 | `test_family_hearing_aids.py` |
| 32 | 選階段看到可以做的事與問卷連結，`/family` 原文不變 | 通過 | `test_family_adjusting.py`、e2e `FamilyAdjustingTest` |
| 33 | 選外型只看到該外型步驟；沒有 JavaScript 兩種都顯示 | 通過 | e2e `FamilyCareTest` |
| 34 | 每步有文字、線條圖、勾選框；圖不分廠牌、不是唯一資訊 | 程式通過，本人確認見第 38 條 | `test_family_care.py`、e2e `FamilyCareTest` |
| 35 | 類型與價格連回選配指引 | 通過 | `test_family_hearing_aids.py` |
| 36 | 手機 200% 不左右捲，44px，1rem | 通過 | 三個 e2e 類別；出處與查核日期照現有規範較小（第 16 條） |
| 37 | 唯一主標題、回專區、分頁標在了解、不用登入 | 通過 | 三個測試檔 |
| 38 | 文字、出處與線條圖由本人審過 | **未完成** | 等本人審字 |

## 自動測試

在 `9431ad4` 上跑，每個都用結束碼確認（這段時間 `main` 沒有新進度）：

- Django：1829 項通過。
- e2e：347 項通過。
- 前端：374 項通過。
- Ruff：`ruff check .`、`ruff format --check .` 都通過。

## 自審

Standards 與 Spec 兩軸各跑一次。修掉：行內連結的觸控高度改成具名 class（第 21 條）、共用腳本的過度宣稱註解；可能延誤就醫的文字由本人決定後修（Q22）。

刻意不修：`Option` 欄位變多、線條圖重複路徑（本人已確認形狀，測試比對）、問卷不存在時隱藏連結（`wearing_follow_ups` 也這樣）。

## 已知限制

- 來源多是英國和美國的資料，就醫一律改寫成耳鼻喉科或聽力師；部分句子來源沒有直接寫，列在審字清單。
- 上一頁的修法只在 Chromium 驗過；實際朗讀沒有自動測試。
- 沒有測試走「先註冊」後是否回到問卷。
- 代理只用 e2e 臨時網站的截圖看過手機畫面。
- 沒有操作真實資料，也沒有新增 migration。
