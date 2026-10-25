# 頁尾中間的小拱門＋波浪 W（小改動，無 issue）

日期：2026-10-25。基準：`076c584`（origin/main）；分支：`feat/footer-arch`。

狀態：等本人驗收。自動測試全過。只改頁尾樣式（`frontend/src/site.css`），沒碰計分、分級、門檻、migration、權限，所以不需要交叉審查。沒有操作真實資料。品牌色照 ADR 0012，不另寫 ADR。

## 怎麼選的

本人在另一個 session 看了七種頁尾形狀的比較頁（暫存資料夾，沒進版控；把真正的 `site.css` 套在新訪客首頁截圖上），選**選項 5**：上緣維持直線，只在正中間凸起一個跟頁尾同色的小拱門，裡面是 Logo 的波浪 W。不做全面改版、不換品牌色。

## 改了什麼

`frontend/src/site.css`：

- `.site-footer`（第 1029 行）：加 `position: relative`；上方間距 3rem → 5.5rem，留位置給拱門，拱門上緣離內容約 2.25rem。
- `.site-footer::before`（第 1041 行）：拱門，6.5rem 寬、上方圓角，顏色 `var(--color-footer-bg)`。
- `.site-footer::after`（第 1053 行）：波浪 W，2.6rem 見方，`var(--color-primary)` 填色，用 `var(--logo-glyph)` 遮罩（`-webkit-mask` 和 `mask` 都寫，跟 `.btn-start::before` 一樣）。
- 手機版和「回到頂端」那幾條 `padding-bottom` 規則沒動。

## 驗收對照

「預覽量測」是用暫存資料夾的 Playwright 腳本，在 worktree 的 runserver（埠 8001）上、未登入，量首頁、`/privacy`、`/login` 三頁；沒寫成 e2e 測試。

| 需求 | 驗證 | 證據 |
|---|---|---|
| 從 `main` 開新分支，用 worktree | ✅ | `.claude/worktrees/footer-arch`，從 `origin/main`（`076c584`）分出 |
| 上緣維持直線，正中間凸起小拱門 | ✅ 預覽量測＋截圖 | 拱門水平置中於頁尾；桌機 1440、手機 390、手機 390＋200% 字級三種寬度都有 |
| 拱門跟頁尾同色 | ✅ 預覽量測 | 頁尾與拱門的底色都是 `rgb(243, 237, 227)`（#f3ede3） |
| 拱門裡是藍色波浪 W | ✅ 預覽量測＋截圖 | W 填色 `rgb(31, 78, 140)`（#1f4e8c），遮罩是 `--logo-glyph` |
| 用現有 token、照 `.btn-start::before` 的遮罩寫法、附英文註解 | ✅ | `frontend/src/site.css:1029`–`:1064` |
| 純裝飾、不被讀出 | ✅ | 偽元素沒有 `content` 文字（`content: ""`），螢幕閱讀器不會唸；HTML 沒改 |
| W 和拱門不蓋到任何連結或文字 | ✅ 預覽量測 | 三種寬度 × 三頁，拱門範圍和 `main` 裡所有元素、頁尾的連結與文字都沒有重疊；拱門上緣距內容最下面 30–40px（200% 字級時 81px） |
| 手機版頁尾底部讓開固定分頁列，原本的 `padding-bottom` 不動 | ✅ 自動（既有）＋預覽量測 | `e2e/main_flow.py:1875`（320px 捲到底，頁尾最後一行在分頁列上方）通過；量到的 `padding-bottom` 桌機 94.5px、手機 162px、手機 200% 323px，都是原本規則算出來的值 |
| 頁尾其他內容、顏色不變 | ✅ 自動（既有） | `e2e/main_flow.py:5271`（頁尾底色）、`:5327`（頁尾文字對比 ≥ 4.5）、`:1854`（頁尾滿版寬）都通過 |
| 重建前端 | ✅ | `npm run build --prefix frontend`，建置輸出含 `.site-footer::before`、`::after` |
| 單元測試全過 | ✅ | 1389 個，OK |
| 整套 e2e 全過，沒有截圖基準或頁尾位置的測試失敗 | ✅ | `e2e.main_flow --parallel 4`：236 個，OK；沒有需要更新的基準 |
| 實際看起來好不好、W 大小合不合適 | ⚠️ 要人工 | 請本人實際操作 |

## 截圖

在共用筆記資料夾（沒進版控）：`footer-arch-shots/`，九張，`desktop-1440-*`、`phone-390-*`、`phone-390-200pct-*` × 首頁／隱私權／登入。截圖時把開發用的 debug toolbar 藏起來，不影響頁面本身。

## 測試指令

```
npm run build --prefix frontend
python manage.py test --settings=config.test_settings --parallel 4   # Ran 1389 tests, OK
python manage.py test --settings=config.test_settings e2e.main_flow --parallel 4   # Ran 236 tests, OK
```
