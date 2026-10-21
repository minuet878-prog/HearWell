# #123：讀 CSS 文字的測試改成在瀏覽器裡量

日期：2026-10-21。規格：[#123](https://github.com/minuet878-prog/HearWell/issues/123)（母規格 #119）。基準：`b3471bd`（main）；分支：`test/css-checks-in-browser`；commit：`b514faa`、`fc5f859`。

狀態：2026-10-21 本人回覆「ok」，驗收通過。自動測試與自審（Standards／Spec）已通過。只改測試，不改畫面；沒碰計分、門檻、資料 migration、權限，不需交叉審查。未操作真實資料、沒有啟動開發伺服器。

## 行為

- 一般測試裡 7 處直接讀 `styles.css` 文字的斷言移除（遷移 Tailwind 後 CSS 是建置產物，這些斷言會失效）：本文與次要文字色、分級與錯誤文字色、作答選項大按鈕、結果橫幅四種分級的顏色、作答頁載入時隱藏表單、健康報告有列印規則、自訂 CSS 在 Bootstrap 之後載入。
- 改成 e2e 的 `StyleInBrowserTest`，在真實瀏覽器裡用 `getComputedStyle` 量同樣的數值；模板裡的 HTML 斷言（class、結構）留在一般測試。
- 「自訂 CSS 在 Bootstrap 之後載入」照規格改成驗它要保護的結果：登入按鈕的底色是主色 #1f4e8c。

### 刻意沒有搬的檢查

- `.text-success`（#1e7b55）、`.text-warning`（#8a5a00）、`.text-secondary`（#495057）：模板、React、Python 都沒有用到（自審 Spec 代理另外 grep 確認），瀏覽器裡沒有東西可以量。同樣的綠、橘、灰仍在結果橫幅與本文色的檢查裡被量到。
- `--bs-body-color-rgb`、`--bs-secondary-color` 這類 Bootstrap 變數本身：改量它們實際影響的文字顏色（本文、隱私頁的版本日期）。
- 這三個沒人用的 class 照規則**沒有刪**，只提出來；要不要刪由本人決定（遷移 #125 只會搬用得到的 class，屆時自然消失）。

## 驗收對照

| 驗收條件（#123） | 驗證 | 證據 |
|---|---|---|
| 在現在的 Bootstrap 網站上全部通過，數值相同 | ✅ 自動 | `e2e/main_flow.py` 的 `StyleInBrowserTest`：本文色 :1001、次要文字 :1003、主色按鈕 :1006、錯誤文字 :1012、四種結果橫幅 :1041、:1043、作答選項 :1051–1053、載入中隱藏表單 :1061、:1063、列印 :1078–1087。5 項全過 |
| 一般測試沒有任何測試讀 CSS 檔案文字 | ✅ 自動 | `grep -rn "styles.css\|_rule(\|_css(" screening/tests/` 無結果 |
| 故意改掉結果橫幅的一個顏色，對應檢查失敗 | ✅ 手動試驗 | 暫時把 `.result-banner-normal` 的 `color` 改成 `#000000`，`test_result_banner_colours` 失敗：`AssertionError: 'rgb(0, 0, 0)' != 'rgb(30, 123, 85)'`（level='normal'）；之後還原，`git status` 確認 `styles.css` 沒有殘留改動 |
| 模擬列印時頁首、導覽、頁尾、列印按鈕隱藏，報告內沒有陰影 | ✅ 自動 | :1078（列印前先確認四者看得見，避免元素不存在也算「隱藏」）、:1079（報告區塊存在）、列印後隱藏與 :1087（沒有陰影） |

## 測試與審查

- `manage.py test --settings=config.test_settings`：641 項全過（移除 3 個只讀 CSS 的測試）。
- `e2e.main_flow`（先 `npm run build --prefix frontend`）：33 項全過（新增 5 項）。
- `ruff check .`、`ruff format --check .`：全過。
- 自審（`/mattpocock-skills:code-review`，基準 `origin/main`）：
  - **Spec**：1 項要修——列印檢查用 `to_be_hidden()`，元素不存在也會通過；已改成先確認看得見、再切列印。可考慮：次要文字原本用 Bootstrap 的 `text-body-secondary` 找，遷移後會失效，已改用文字內容找；作答選項「至少 54px 高」驗的是結果而非規則本身（刻意，規格要求驗結果）；手動試驗要留書面證據（見上表）。
  - **Standards**：0 項硬性違規。採納：`3 * 18` 補單位註解、severe 的字色改用同一個常數。不採納：e2e 四個類別各有一份 Playwright 開關與登入 cookie 的程式，抽共用會超出這張票（`CODING_STANDARDS.md` 第 19 條），留給之後。

## 人工驗收

只改測試、畫面不變，不需要操作網站。2026-10-21 本人回覆「ok」，同意「刻意沒有搬的檢查」。
