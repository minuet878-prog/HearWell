# 結果頁「接下來建議您」改成卡片

日期：2026-10-23；分支 `style/next-steps-cards`（從 `origin/main` 的 `9d51c0b` 開出）。
狀態：自動驗證完成；**不需交叉審查**（改樣式和步驟上的連結，不碰計分、分級、門檻、資料或權限）；**本人在預覽實際操作過，驗收通過**（2026-10-23）。

## 範圍

小改動，對話中提出，沒有開 issue。本人說這一區「很亂」，原因有四個：大按鈕塞在編號清單裡、「看／印聽力報告」跟頁尾重複、選填問卷夾在兩個下拉框中間而且黏著下拉框、按鈕和下拉框都是同樣的藍框分不出輕重。比較頁列了 A／B／C 三案，本人選 **B（每點一張卡）**。

- `result.html`：每一點的大按鈕改成帶 › 的文字連結，放在一組 `next-steps-links` 裡。「分數細節與作答明細」移到「看完整建議」下面，讓兩個下拉框排在一起；選填 SSQ12-TW 和「比較戴與不戴助聽器」移到兩個下拉框後面。SSQ12-TW 的入口改成白色卡片（`link-card`），「比較」按鈕保留原樣（測試依它的連結文字找它，而且它跟這次的亂沒有關係）。
- `site.css`：`.next-steps` 每一點是白卡，數字放在淡藍圓圈裡（CSS counter），還是 `<ol>`，並加上 `role="list"`，讀螢幕軟體才會報出共幾項。（合併後補記：PR #274 原本漏了 `role="list"`，Safari 的 VoiceOver 看到 `list-style: none` 就不把它當清單；首頁步驟卡、選配指引步驟條早就這樣處理，後續 PR 補上並加測試 `test_the_step_list_keeps_its_list_role`。）文字連結點擊高度 46.8px，底線不畫到箭頭，箭頭也不會被讀出來。字放大時（容器窄於 15rem），數字移到文字上方，不把文字擠成一行三個字。
- 問卷定義：步驟上的「看／印聽力報告」**只留在文字有提到報告或結果的那一點**（本人選的規則），頁尾卡片列本來就有這張卡。
  - 拿掉：HHIE-S 輕度到中度、明顯影響；HHIA-S 明顯影響；THI 重度、極重度。
  - 保留：HHIA-S 輕度到中度（「帶這份結果…討論」）、THI 中度（「可以帶著聽力報告去」）。
  - 步驟文字、「記錄聽力圖」、「看助聽器選配指引」都沒動。

## 驗收條件對照

| 條件 | 證明 |
|---|---|
| 每點是一張卡，連結是文字連結 | 截圖（HHIE-S 明顯影響／輕度到中度、HHIA-S 輕度到中度、THI 重度，手機與桌機）；e2e `step4_result_steps_and_score_bar` 依 `ol.next-steps > li` 找三點 |
| 報告連結只留在有提到的那一點 | `test_result_next_steps.py` `test_each_level_shows_its_finalized_steps_and_action_buttons`（HHIE-S、HHIA-S 各級）；`test_thi.py` `test_each_level_shows_its_steps_ending_with_the_three_month_retake`（THI 各級）；e2e 確認 HHIE-S 輕度到中度那一點沒有報告連結 |
| 選配指引連結還在原本那一點，只出現一次 | `test_guide_result_entry.py` `test_the_check_step_links_to_the_guide_after_its_own_link` |
| 兩個下拉框相鄰，選填問卷在它們後面 | 截圖 |
| 「比較戴與不戴助聽器」仍在頁尾卡片列之前 | `test_result_pages.py` `test_the_page_s_own_comparison_comes_before_the_closing_row` |
| 兩倍字、320px 寬不會橫向捲動，數字移到上方 | 試驗截圖量測：`scrollWidth` 沒有超出視窗；e2e 兩倍字版面檢查通過 |

## 自動驗證

| 檢查 | 結果 |
|---|---|
| `python manage.py test --settings=config.test_settings` | 1128 個全部通過 |
| `npm run build --prefix frontend` | 成功 |
| e2e `e2e.main_flow --parallel 4` | 110 個全部通過（最後一版 CSS 重建後再跑一次，同樣全過） |
| `npm test --prefix frontend` | 217 個全部通過 |
| `ruff check .` | 沒有問題 |

截圖用一支臨時的 Playwright 腳本在測試資料庫產生，截完已刪除，沒有進版控。自動驗證時 8001 埠被另一個 session（auth-pages 工作樹）的預覽佔用，所以先用截圖；之後 8001 空出來，本人從本工作樹啟動伺服器實際操作。

## 自審

對照 `CODING_STANDARDS.md`：字級用 `rem`／`em`（第 16 條）；新樣式是有名字的 class、引用主題值（第 21 條）；步驟卡不能點，沒有滑過或按下效果，文字連結只變色（第 22 條）；只用藍色系（第 23 條）；步驟文字仍只來自問卷定義（第 9 條）。沒有發現。

## 本人驗收

- [x] 在 http://localhost:8001 （從本工作樹啟動）實際操作結果頁，「接下來建議您」整齊了（2026-10-23）
