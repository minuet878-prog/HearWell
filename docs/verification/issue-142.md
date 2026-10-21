# #142 2a 收尾驗證（全站對照、文件、#120 驗收條件）

日期：2026-10-22；分支 `feat/142-finish-2a`（從 `feat/120-warm-shell` 的 `a2cfc7a` 開出）；母分支 `feat/120-warm-shell`。
狀態：自動驗證完成；本人 2026-10-22 回覆「照你建議 push pr」：作答選項加滑過變色，並同意 push、開 PR，視為接受改版後的外觀。子分支合回 `feat/120-warm-shell`，功能分支開 PR 合併回 `main`（合併前仍等本人）。

## 範圍

- [#142](https://github.com/minuet878-prog/HearWell/issues/142)、母規格 [#120](https://github.com/minuet878-prog/HearWell/issues/120)、ADR 0006、0007。
- 全站對照頁與圖表裁切比對：用暫時的 worktree 在 `main`（`a73d9c9`）拍基準，2a 分支再拍，兩邊用同一份截圖工具。拍完已移除 worktree。
- 文件：
  - `CODING_STANDARDS.md` 加第 22、23 條，分別指向 ADR 0006、0007。
  - 無障礙基準文件新增第 6 節（米白底、白色卡片、頁尾、漸層上的對比），第 4 節加一列。
  - roadmap 的目前進度改成「遷移完成、2a 收尾中」，「已完成」表加一列遷移 Tailwind。
- 作答選項：#120 第 11 條「作答選項滑過或按下只變色、不位移」原本沒有斷言，而且滑過完全沒有變化。
  - 補測試 `test_answer_choices_only_change_colour`：試驗讓選項滑過時往上 2px，測試失敗；已還原。
  - 本人選「加滑過變色」：有滑鼠時滑過邊框變藍（和導覽項目一致），手機不套，免得點完停在藍邊框。測試先要求邊框變藍、看它失敗，再加樣式。
  - 改完重拍圖表裁切：仍是同樣 5 張、像素數不變。
- #143（截圖工具）已在 2026-10-21 驗收並合回功能分支，這次沒有再改。

## 全站對照

- 對照頁：`e2e-artifacts/shots/142-diff/gallery.html`（不進版控）。
- 共 422 張，45 張相同，377 張不同。換底色、圓角、漸層的頁面本來就會不同。
- 相同的 45 張：
  - 列印版健康報告與分享報告 4 張：和改版前完全一樣，也是第 15 條的證據。
  - Django admin 6 張，admin 的頁首 6 張：admin 不套網站樣式。
  - 未登入頁面的導覽列 6 張（分享報告、分享封面、分享失效、隱私權、家人溝通、加到主畫面，各只有一種寬度相同；沒有再查原因）。
  - 圖表與徽章裁切 23 張。
- 字型與基礎字級：0 頁不同。

## 圖表裁切（第 13 條）

`compare_shots.py --group parts`：28 張中 23 張相同、5 張不同，結束碼 1。5 張和 #137 時本人接受的偏差完全相同，張數和每張的像素數都沒有變（見 [`issue-137.md`](issue-137.md) 第 4 條的偏差）：

| 截圖 | 不同的像素（#137 → 現在） |
|---|---|
| 聽力圖檢視，1024 寬 | 158 → 158 |
| 聽力圖比較，1024 寬 | 2 → 2 |
| 聽力圖檢視，390 寬 | 1 → 1 |
| IOI-HA 常模圖，1024 寬 | 38 → 38 |
| 聽力圖頁的程度標籤，390 寬 | 7 → 7 |

#138–#141 都沒有讓圖表、徽章多出差異。

## #120 驗收條件對照

| 條件 | 證明 |
|---|---|
| 1. 頁面背景 #faf7f2，卡片、表單、輸入框、圖表外框白底，頁尾淺暖色 | `e2e/main_flow.py:1721` `test_page_is_warm_and_surfaces_are_white` |
| 2. 米白底上的本文、次要、連結、分級、錯誤文字至少 4.5:1 | `:1745` `test_text_on_the_warm_page_keeps_its_contrast`（瀏覽器算出的顏色）；數字記在無障礙基準文件第 6 節，最低 4.89:1 |
| 3. 頁首由上往下藍色漸層、最上緣 #1f4e8c，聲波對螢幕閱讀器隱藏 | `:1877` `test_header_is_a_blue_gradient_with_a_hidden_wave` |
| 4. 新分頁第一頁聲波播、約 4 秒停；同分頁下一頁不播；沒有無限循環 | `:1889` `test_header_wave_plays_on_a_tabs_first_page_only` |
| 5. 關掉 JavaScript 時聲波播並在約 4 秒內停 | `:1907` `test_header_wave_plays_on_every_page_without_javascript` |
| 6. 減少動態效果：沒有動畫或位移，只變色 | `:1915` `test_reduced_motion_keeps_the_header_still`（全頁 0 個動畫）；`:2255` `test_reduced_motion_cards_only_change_colour`（卡片滑過、按下不位移、陰影不變、只變色） |
| 7. 主要按鈕、導覽目前頁、步驟編號、問卷分頁目前頁、問卷圖示是漸層；白字 ≥ 4.5、白色圖示 ≥ 3 | `:1950` `test_primary_button_states_follow_choice_c`（四種狀態）、`:2067` `test_current_place_and_icons_use_the_gradient`（步驟編號只斷言漸層與白字，沒另算對比；顏色和導覽目前頁相同，最低 5.37:1） |
| 8. 手機分頁列：目前頁圖示在漸層膠囊、藍色粗體、沒有上緣線、觸控 ≥ 44px | `:2102` `test_phone_tab_bar_puts_the_current_icon_in_a_pill` |
| 9. 滑鼠滑過可點的卡片浮起、陰影加深、邊框藍、漣漪；不能點的框沒有變化 | `:2168` `test_clickable_cards_lift_on_hover`、`:2286` `test_boxes_that_cannot_be_clicked_stay_still` |
| 10. 觸控按下卡片下沉、放開恢復，不殘留滑過樣子 | `:2205` `test_pressed_cards_sink_on_a_touch_screen`（Chromium 模擬；iPhone Safari 的按下效果見 [`issue-141.md`](issue-141.md) 的已知風險） |
| 11. 按鈕、導覽項目、作答選項只變色不位移；鍵盤焦點落在卡片不位移、看得到焦點框 | 不位移：`:1990` `test_buttons_are_pills_and_only_change_colour`（按鈕）、`:2119` `test_navigation_items_only_change_colour`（導覽）、`:2136` `test_answer_choices_only_change_colour`（作答選項，這次補）。變色：按鈕 `:1310` `test_button_hover_and_press_colours`、`:1950`；導覽 `:2119`；作答選項 `:2136`（滑過邊框變藍）。鍵盤焦點：`:2312` `test_keyboard_focus_keeps_cards_still_with_a_ring`；按鈕焦點框和光暈分得出：`:2040` |
| 12. 大區塊 1.5rem、中元件 0.75rem、按鈕膠囊；圖表、縮圖、分級徽章不變 | `:1787` `test_three_radius_levels`、`:1990`（膠囊） |
| 13. 圖表與徽章裁切和改版前逐像素相同；結果橫幅、趨勢圖色帶、遮蔽開關顏色不變；新增裝飾色是藍色系 | 裁切：**5 張偏差，本人在 #137 已接受**（上一節）。顏色：`:1571` `test_result_banner_colours`、`:1602` `test_level_badge_colours`、`:1842` `test_masking_switch_keeps_its_orange`、`frontend/src/TrendChart.test.jsx` 的色帶斷言。裝飾色：逐一核對 2a 在 `site.css` 新加的顏色值，只有藍色系（漸層、按下的漸層、停用的灰藍、光暈與漣漪）、白色，以及規格指定的米白底、頁尾、暖色邊框與陰影，沒有新的綠、橘、紅（人工核對，沒有自動測試） |
| 14. 四顆刪除類按鈕維持紅色 | `:2020` `test_delete_buttons_stay_red` |
| 15. 健康報告列印模式白底、沒有陰影和漸層 | `:1657` `test_printed_report_has_no_site_chrome_or_shadows`；全站對照裡列印版截圖和改版前完全相同 |
| 16. manifest `background_color` #faf7f2、`theme_color` #1f4e8c | `screening/tests/test_pages.py:742` `test_manifest_fields` |
| 17. 聲波與主要按鈕漸層，本人在比較頁選定，驗證紀錄記錄選擇 | [`issue-136.md`](issue-136.md)：聲波選「F」（C 的音量長條＋E 的柔光掃過，停成平坦一排），按鈕選「C」；#139 時本人把滑過改成柔和光暈（[`issue-139.md`](issue-139.md)） |
| 18. 本人檢視全站對照頁並接受外觀 | `e2e-artifacts/shots/142-diff/gallery.html`；本人 2026-10-22 回覆「照你建議 push pr」 |
| 19. `CODING_STANDARDS.md` 指向 ADR 0006、0007；無障礙基準記錄新對比；roadmap 寫明遷移完成與 2a 進度 | 本分支：`CODING_STANDARDS.md` 第 22、23 條；`docs/accessibility/accessibility_baseline.md` 第 6 節；`docs/roadmap.md` 目前進度 |

## 自動驗證

| 檢查 | 結果 |
|---|---|
| Django 全套 | 646 個通過 |
| 前端 | 190 個通過 |
| e2e `e2e.main_flow` | 66 個通過 |
| `ruff check .`、`ruff format --check .` | 通過 |

## 自審

`/mattpocock-skills:code-review`，基準 `a2cfc7a`。

- 規範軸：沒有硬性違規。
  - 已修：`CODING_STANDARDS.md` 第 23 條補上 ADR 0007 的例外（聽力圖右耳紅、遮蔽開關橘）；第 22 條補上「滑過效果只在有滑鼠的裝置」「不做進場動畫」；這份紀錄補上自審段落。
  - 不改：「滑過、按下、比位置」在按鈕、導覽、作答選項三個測試裡重複。三個測試各自檢查的東西不同（顏色、膠囊、變色），抽成共用函式反而難讀。
- 規格軸：19 條引用的行號都對得上，截圖數字和對比數字重算相同。
  - 已修：無障礙基準原本寫「這些組合都由 e2e 守住」，實際上 e2e 只量米白頁面那一欄和頁尾文字，改成如實寫明；roadmap 原本寫 #136–#143 都已驗收，改成 #142 等本人檢視。
  - 本人決定：作答選項滑過時邊框變藍（下一節）。

## 本人決定（2026-10-22）

- 第 11 條寫「按鈕、導覽項目、作答選項：滑過或按下只有顏色變化」。作答選項原本滑過完全沒有變化，按下（選取）才變藍。
  - 選項：加滑過變色（和導覽項目一致）／不加（把「只變色」解讀成「有變化的話只能是顏色」）。
  - 本人照建議選「加」：有滑鼠時滑過邊框變藍。

不需交叉審查：2a 只改樣式、模板外觀、文件與測試，沒碰計分、分級、門檻、資料 migration 或權限。

## 本人檢視（2026-10-22）

- [x] 打開 `e2e-artifacts/shots/142-diff/gallery.html`，改版前後並排看過，接受改版後的外觀；要調整的地方記在這裡。
