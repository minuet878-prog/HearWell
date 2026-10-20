# #70–#74：標題、登入欄位用途與鍵盤導覽

日期：2026-10-20。功能分支：`codex/accessibility-70-74`。基準：`da26a11`。

狀態：#70–#73 已實作；#74 經驗證由既有歷史清單滿足，不新增重複資料表。待本人人工驗收，五張票保持開啟。尚未 push 或開 PR。

## 根因與修正

| 票 | 根因／查證 | 最終行為 |
|---|---|---|
| [#70](https://github.com/minuet878-prog/HearWell/issues/70) | HHI 結果等級是 div，標題導覽會略過 | HHIE-S／HHIA-S 結果等級改為 h2，`aria-describedby` 關聯總分；補上結果頁 h1，保留等級配色與字級 |
| [#71](https://github.com/minuet878-prog/HearWell/issues/71) | 登入模板自行寫 input，沒有輸出用途屬性 | 帳號 `autocomplete="username"`、密碼 `autocomplete="current-password"`；修在實際輸出的模板 |
| [#72](https://github.com/minuet878-prog/HearWell/issues/72) | 共用站名是 h1，與首頁及其他頁主標題重複 | 站名改 p 並沿用樣式；「我的紀錄」、作答及 HHI 結果補正主標題，其餘頁沿用既有主標題 |
| [#73](https://github.com/minuet878-prog/HearWell/issues/73) | 共用版型缺少跳轉入口；登入／註冊自動聚焦還會跳過第一個 Tab | body 第一個連結為「跳到主要內容」，聚焦時顯示；原生錨點跳至 `main tabindex="-1"`，不新增 JavaScript。正常進頁不自動聚焦欄位；驗證失敗時保留既有焦點提示 |
| [#74](https://github.com/minuet878-prog/HearWell/issues/74) | 圖表摘要確實只描述最近變化，但下方 HTML 清單已包含本人全部歷史，且對輔助科技可見 | 23 筆 Django 與 3 筆瀏覽器資料均可取得每筆日期、分數與結果連結；圖表 20 筆上限不影響清單。本票驗收條件已由既有行為滿足，只補回歸測試 |

## 測試邊界與證據

本人已確認使用 Django 公開頁面整合測試，加上真實瀏覽器的焦點及無障礙角色查詢；不測私有函式。使用者也確認根因及上述修正範圍。

- `screening.tests.test_accessibility`：HHIE-S／HHIA-S 等級標題及總分關聯、登入 autocomplete、每頁唯一且在 main 內的 h1、第一個跳轉連結與目的地、23 筆完整歷史。
- `e2e.main_flow.SharedLayoutTest` 新增三項：結果等級可由 heading 角色取得；登入前／後的頁面第一個 Tab 選到跳轉連結，Enter 後 main 取得焦點；圖表載入後三筆日期及各自 20／40／0 分仍可由連結的無障礙名稱取得。
- #70–#73 先看到各自失敗，再修正至通過。#73 瀏覽器更定位到 `/login` 與 `/register` 的 autofocus，修正後三項新瀏覽器測試通過（2.893 秒）。
- #74 未先製造不存在的功能錯誤：多筆資料的既有行為測試直接通過，因此保留產品實作。
- 舊測試要求登入 GET 自動聚焦帳號、作答介紹使用 h2，與新規格衝突；已更新這兩項期待，保留登入失敗時的帳號／密碼焦點及介紹在表單外的檢查。
- 第一次歷史瀏覽器測試因日期正規表示式的斜線跳脫失敗，修正測試選擇器後通過；未為測試修改產品邏輯。

## 最終驗證

- 完整 Django：603 項通過（PostgreSQL，30.625 秒）。
- 前端：12 檔、182 項通過；Vite build 通過。專案沒有獨立 typecheck 指令。
- 完整瀏覽器：26 項通過（37.347 秒），包括三項新增的無障礙操作測試。
- 完整 Ruff 與 `git diff --check` 通過。
- Standards：0 項發現，既有測試調整已複核。
- Spec：0 項發現，既有測試調整已複核。
- 查閱官方文件：Django 5.2 的 widget attrs、Bootstrap 5.3 的 `visually-hidden-focusable`、Playwright Python 的角色與焦點斷言。未新增套件。

## Standards

0 項發現。標題、分數描述、登入欄位用途及跳至主要內容採原生 HTML，樣式使用 rem；修改限定本次需求，未改計分、資料隔離或 API。兩處舊測試更新已複核，保留錯誤焦點及介紹在表單外的保護。

## Spec

0 項發現。#70–#73 的標題、欄位用途與跳轉符合需求；取消正常進頁 autofocus 是維持第一個 Tab 順序所需。#74 用 23 筆頁面與三筆瀏覽器資料確認既有清單足夠，符合先驗證再決定是否修改的要求。

審查總計：Standards 0 項、Spec 0 項；無未解決發現。

## 人工驗收

1. 首頁按第一個 Tab：出現「跳到主要內容」；Enter 後焦點移到主內容。用相同方式確認登入、註冊、問卷目錄、我的紀錄與報告頁。
2. 以 VoiceOver／NVDA 的標題導覽確認：首頁只有一個主標題；HHI 結果可讀出判讀等級，總分為其補充描述。
3. 以自己的瀏覽器或密碼管理員確認登入帳密建議；確認錯誤登入仍保留帳號並提示錯誤。
4. 用有三筆以上 HHIE-S 的假資料帳號，逐筆讀取歷史日期、分數與結果連結，包含較早紀錄與 0 分。
5. 320px 與放大字級下確認跳轉連結可見且可操作。實際輔助科技及密碼管理員的行為需本人確認，瀏覽器角色測試不取代這些操作。

## 收尾

本次不改真實資料、計分、API 或資料模型，不需 migration。未啟停本機常駐服務；端對端測試只使用臨時測試網站與假資料庫。

面試筆記（不進版控）：Q158 標題語意與外觀、Q159 skip link 與 autofocus、Q160 驗證既有文字替代；紀錄 `docs/interview/development/phase-10/02-accessibility-70-74.md`。
