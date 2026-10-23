# 給家人頁的「出處」改成卡片

日期：2026-10-23；分支 `style/family-sources-card`（從 `main` 的 `c381287` 開出）。
狀態：自動驗證完成；**不需交叉審查**（只改樣式，不碰計分、分級、門檻、資料或權限）；**本人在預覽實際看過，驗收通過**（2026-10-23）。

## 範圍

小改動，對話中提出，沒有開 issue：給家人的溝通與陪伴頁（`/family`）最下面的「出處」，改成跟上面「傳給家人」一樣的卡片。

`screening/templates/screening/family_guide.html`：

- 「出處」區塊加上其他卡片同一組 class（`card card-body mb-4`）：白底、圓角、陰影都一樣。原本的 `mt-6` 拿掉，跟上一張卡片的間距改成和其他卡片相同。
- 卡片裡最後一組清單加 `mb-0`，卡片底部的留白才跟其他卡片一樣。

## 驗收條件對照

| 條件 | 證明 |
|---|---|
| 「出處」是卡片，外觀跟「傳給家人」一樣 | 預覽量計算後的樣式：白底、圓角 27px、陰影都和其他卡片相同；最後一組清單下方留白 0；本人看過 |
| 出處內容、順序、連結不變 | `test_family_guide.py` `test_topics_in_order_with_sources_grouped_at_the_end` |

## 自動驗證

| 檢查 | 結果 |
|---|---|
| `python manage.py test --settings=config.test_settings` | 1128 個全部通過 |
| e2e `NewUserScreeningTest.test_family_guide_without_share_sheet`（家人頁唯一的 e2e） | 通過 |

只改模板的 class，沒有改 CSS 或 JavaScript，所以沒有重建前端、沒有跑前端測試與整套 e2e。

## 自審

diff 只有兩行 class，`CODING_STANDARDS.md` 沒有模板相關規則，沒有發現。

## 本人驗收

- [x] 在 http://localhost:8001/family 看過，「出處」跟上面卡片一致（2026-10-23）
