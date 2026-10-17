feat(pwa): back button and pull to refresh in the home-screen app

## 摘要

從手機主畫面打開（全螢幕模式）時沒有瀏覽器工具列：iPhone 沒有上一頁，兩種手機都不能下拉重新整理。這次補上這兩個動作，一般瀏覽器分頁不受影響。規格：[phase10_pwa_back_refresh.md](docs/specs/phase10_pwa_back_refresh.md)

```
 每一頁載入 pwa-nav.js
+  不是全螢幕 → 什麼都不做
+  上一頁按鈕（首頁沒有，預設 hidden）
+    能退回（navigation.canGoBack，舊瀏覽器看 history.length）→ history.back()
+    不能退回 → 回首頁
+  下拉重整
+    手指碰到螢幕：頁頂、單指、沒放大、<main> 沒有表單欄位 才開始
+    拉的途中：第二根手指加入 → 取消
+    放開：拉超過 80px → 重新載入；不夠 → 提示收回
```

另一個 commit：`.claude/skills/`（`pr`、`retro`）進版控，CLAUDE.md 工作流程加上這兩步。

## 證據

- **新增前：** 沒有這個功能。
  **新增後：**
  - Vitest 158 → 180，全部通過
  - Django 557 → 564，全部通過
  - e2e 13 → 16，全部通過
  - ruff 通過
- **審查後修的 bug（修改前失敗、修改後通過）：**
  - `goes to the previous page`：按上一頁、跑完所有計時器 → 只呼叫 `back()`，沒有被帶去首頁（原本作答頁退回上一題、或伺服器慢時，0.5 秒計時器會誤跳首頁）
  - `ignores a touch that starts with two fingers`、`cancels the pull when a second finger joins`：兩指縮放 → 不重新整理
  - `is off while the page is zoomed in`：畫面放大時 → 不啟動下拉
- 驗收條件：1–14 全部打勾（14 為本人 iPhone、Android 實機）。

## 合併風險

**門：** 雙向門
只加一支前端 script、標題列一顆按鈕和樣式；沒有 migration、沒有改 API 或資料，退版就好。

**影響範圍：** 全站版面
- 每一頁都多載入一支小 script；JS 失敗時按鈕維持隱藏，頁面照常可用。
- 標題列在 200% 字級、320px 寬時的排版（e2e 有守：不撐寬、上一頁跟登出不相鄰）。
- 作答頁的上一頁＝上一題（`pushState`），已改用 `canGoBack`，不會被帶回首頁。
- 舊 iPhone 沒有 Navigation API 時，「切回 app 時頁面被重新載入」之後按上一頁可能沒反應（罕見，導覽列還有首頁）。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
