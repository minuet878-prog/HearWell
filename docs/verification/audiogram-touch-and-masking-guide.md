# 聽力圖一按就標、遮蔽說明、換耳跳回上方

日期：2026-11-14。需求：本人在手機上標聽力圖時發現三件事。第一，#353 改成「按住 0.3 秒才開始標」，但 #465 改版後標記頁已經不太需要捲動，結果變成點了沒反應。第二，按太久會跳出 iPhone 的選字。第三，遮蔽的引導不清楚：不知道遮蔽是什麼、什麼時候要開；右耳標完換左耳時，遮蔽沒有關，畫面也停在下面，沒有跳回標記區。遮蔽說明的擺法從[比較頁](../planning/redesign/mockup-audiogram-masking-compare.html)選 **A**（開關正下方一句說明＋符號對照表）。沒有另開 issue。

基準：`main` `570728f`；分支：`fix/audiogram-touch-masking`。

狀態：自動測試全部通過，等本人用 iPhone 實際操作。只動畫面和觸控，沒碰計分、門檻、migration、權限，**不需要交叉審查**。沒有操作真實資料。

## 原因

- **點了沒反應**：`AudiogramChart.jsx` 的觸控要停 0.3 秒（`HOLD_MS`）才開始標，0.3 秒內放開一律不標（#353 為了讓手指在圖上滑可以捲動頁面）。
- **長按跳出選字**：圖只寫了 `user-select: none`，iPhone Safari 只認 `-webkit-user-select`，長按選單要用 `-webkit-touch-callout: none` 關掉，兩個都沒寫（建置出來的 CSS 也沒有自動補上）。
- **換耳沒跳到上方**：換步驟時只把焦點移到步驟標題，靠瀏覽器順便把它捲進畫面。iPhone 點按鈕不會移動焦點，標題從上一步起就一直有焦點，再 focus 一次瀏覽器什麼都不做。本機預覽重現：步驟標題已有焦點時按「右耳標完了，換左耳」，畫面停在 1122px、標題在畫面外；先讓焦點離開再按，就會捲上去。

## 改了什麼

- 觸控和滑鼠一樣，一按就標：拿掉 0.3 秒等待；圖的 `touch-action` 從 `manipulation` 改成 `none`（手指從圖上開始滑不再捲動頁面，要捲動就從圖外滑）。點一下就標在那裡，點在已有的點上就刪除。
- 圖加上 `-webkit-user-select: none`、`-webkit-touch-callout: none`。
- 換步驟（換耳、到確認頁、從確認頁回去改）時：遮蔽自動關掉；除了移焦點，也把步驟標題捲到畫面最上面。
- 遮蔽開關正下方加說明框：「報告上是這些符號，就打開遮蔽再標：」＋這一耳的對照表（氣導、骨導 × 沒遮蔽、有遮蔽），和一句「遮蔽是檢查時在另一耳放雜音，不讓另一耳幫忙聽，結果比較準。」
- 「怎麼標記」第 2、3 步和讀螢幕的說明拿掉「按住不動一下」。
- 這改掉了第一份聽力圖規格的拷問決定 18（遮蔽開關一直維持、不自動關），現在只在同一步裡維持（`docs/specs/` 是歷史文件，不改原文）。

## 測試結果

- `AudiogramApp.test.jsx`：先改測試看到 6 項失敗，再改程式，55 項全過。
- `npm test --prefix frontend`：557 項通過；`npm run build --prefix frontend` 成功。
- 第一次跑整套 e2e：`test_batch3_pages_fit_a_phone_at_double_text_size` 失敗（320px、200% 字級下頁面寬 337px）。用臨時探測找到是新加的對照表：格子左右留白 0.75rem 跟著字級放大。改成表格滿寬、格子留白 0.25rem 後，探測檔已刪除。
- 修完重跑：整套 e2e（`e2e.main_flow --parallel 4`）427 項通過；`python manage.py test --settings=config.test_settings`（`--parallel 4`）2587 項通過；前端 557 項通過。
- 沒有改到 `.py`，所以不需要跑 Ruff。

390px 畫面（遮蔽打開、標右耳）：符號鈕、遮蔽開關、說明框（對照表的有遮蔽欄是橘色）、橘色虛線圖框，跟比較頁的 A 一致。

## 對照需求

測試檔＝`frontend/src/AudiogramApp.test.jsx`（下稱 `a`）。

| # | 要點 | 驗證 | 證據 |
|---|---|---|---|
| 1 | 手指一碰到圖就出現數值、可以上下拖，拖的時候頁面不捲動 | ✅ 自動 | `a:242` `a finger marks as it lands, and dragging does not scroll the page`（`touchAction` 是 `none`、按下就有放大鏡、`touchmove` 被擋） |
| 2 | 點一下就標；點在點上就刪除 | ✅ 自動 | `a:254` `a tap marks, and a tap on the point deletes it` |
| 3 | 瀏覽器收回觸控時不標 | ✅ 自動 | `a:264` `marks nothing when the browser takes the touch` |
| 4 | 長按不跳出選字和選單 | ⏳ 本人 iPhone | jsdom 不會選字；建置後的 `site.css` 有 `-webkit-user-select: none`、`-webkit-touch-callout: none` |
| 5 | 換下一步時遮蔽自動關掉 | ✅ 自動 | `a:357` `turns off when the next step opens, so the left ear starts unmasked` |
| 6 | 換步驟時跳回最上面的步驟標題 | ✅ 自動＋⏳ 本人 iPhone | `a:456` `brings the step it opens to the top even when its text already has focus`（標題已有焦點時仍呼叫 `scrollIntoView({ block: "start" })`） |
| 7 | 開關下面說明什麼時候開、遮蔽是什麼，符號跟著這一耳 | ✅ 自動 | `a:368` `says under the switch which of this ear's marks need it, and what it is` |
| 8 | 「怎麼標記」的字跟新操作一致 | ✅ 自動 | `a:389` `each step shows only what it needs (#199 acceptance 1)` |

## 本人實際操作（iPhone）

- [ ] 點一下圖就標上，按住上下拖可以改，點在點上可以刪
- [ ] 按久一點不會跳出選字或選單
- [ ] 右耳打開遮蔽，按「右耳標完了，換左耳」：遮蔽變成關，畫面跳回最上面的「第 3 步」
- [ ] 遮蔽說明看得懂；說法對不對（聽力師角度）
