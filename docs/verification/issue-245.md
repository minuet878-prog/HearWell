# #245 IOI-HA 改用 React 作答頁

日期：2026-10-23；分支 `feat/245-ioi-ha-react`（從 `main` 的 `7fb62ef` 開出）。
狀態：自動驗證完成；**本人決定跳過交叉審查**（2026-10-23，自審後回覆「跳過」）；**本人實際操作驗收通過**（2026-10-23）。

## 範圍

- 規格 [#245](https://github.com/minuet878-prog/HearWell/issues/245)；相關 ADR 0002（常模依據在完成作答時固定）。
- API：
  - 問卷單筆 API 不再排除 IOI-HA，逐題回傳選項。
  - 送出 API 收 IOI-HA，多一個選填欄位 `norm_token`，只有 IOI-HA 用，其他問卷忽略。
  - token 驗不過（別人的、竄改的、依據已不在）回 400「常模依據無法確認，請重新開啟問卷。」，什麼都不存。
  - IOI-HA 的「有沒有戴助聽器」一律存成未記錄，跟網頁版一樣。
  - 送出回應的分數、分級、建議為空，跟 SADL、SSQ12 一樣不給總分。
  - 列表、單筆 GET 和趨勢圖照舊排除 IOI-HA。
- 常模依據的取得與 token 驗證從網頁 view 搬到 `screening/ioi_norm.py`，網頁版和 API 共用同一份。
- 作答頁：IOI-HA 也載入 React，容器帶 `data-skip-wearing` 與 `data-norm-token`。網頁表單和裡面的隱藏 token 保留，JS 沒載入時照舊可用；網頁版送出失敗時仍停在網頁表單。
- React：
  - `skipWearing` 時沒有戴助聽器那一步，也不送 `wearing_hearing_aid`；有 `normToken` 就送回去。
  - 沒有沿用 SADL 的 always-aided，因為那會把紀錄存成「有戴」。
- 本人在實作中的決定（2026-10-23）：IOI-HA 第 1 題上方完整顯示問卷說明（含「本次常模依據」），第 2 題起收進「這份問卷在問什麼？」，才符合 ADR 0002「填答前顯示依據」。SADL 不變。已補進 #245 規格與驗收條件。
- OpenAPI schema（`docs/api/schema.yaml`）已重新產生。

## 驗收條件對照

`T` = `screening/tests/test_ioi_ha_api.py`，`A` = `frontend/src/AnswerApp.test.jsx`，`M` = `frontend/src/answer-main.test.jsx`，`E` = `e2e/main_flow.py`。

| 條件 | 證明 |
|---|---|
| 1. GET 單筆 API 回 200，七題各帶網頁表單相同的選項 | `T:61` |
| 2. 有依據、帶 token 送出 → 201，分組與依據同網頁版，戴助聽器為未記錄 | `T:75`（同一個 token 再用網頁版送一次，逐欄比對） |
| 3. 沒有依據、不帶 token → 201，沒有分組與依據 | `T:100`（另外帶 token 也測）；不帶 token 用當下最新依據 `T:93` |
| 4. 別人的 token → 400，什麼都不存 | `T:108` |
| 5. 竄改過的 token → 400，什麼都不存 | `T:116` |
| 6. 開頁時的依據被刪 → 400、訊息正確 | `T:123` |
| 7. 開頁後新增較新的 HHI，依據仍是開頁時那一筆 | `T:75` |
| 8. 七題倒序送出，分數對到正確題目 | `T:131`（也比對各題自己的選項文字） |
| 9. 某題送該題不接受的值 → 400 | `T:145` |
| 10. `wearing_hearing_aid` 為 true、false 或沒送 → 都存成未記錄 | `T:153` |
| 11. 同收據編號、同答案重送 → 200 與第一筆 | `T:169` |
| 12. 其他問卷多帶 `norm_token` → 被忽略 | `T:180` |
| 13. 作答頁有 React 容器（token 與跳過標記）與作答 JS；網頁表單完整、有隱藏 token | `T:207`、`T:222`；`screening/tests/test_answering.py:782` |
| 14. 網頁版漏答 → 不載入 React，保留答案與紅字 | `screening/tests/test_answering.py:791`（既有測試） |
| 15. React 第一步就是第 1 題，不出現戴助聽器 | `A:862`、`M:132` |
| 16. 第 1 題完整顯示說明（含常模依據），第 2 題起收起 | `A:875` |
| 17. 送出 body 帶同一個 `norm_token`；沒有 token 時不帶 | `A:888`、`A:901`、`M:132` |
| 18. 400 時顯示常模依據的訊息 | `A:911` |
| 19. 真瀏覽器：先填未配戴 HHIE-S，再用 React 填完 IOI-HA，結果頁有分組依據與常模比較 | `E:166` |
| 20. 320px、字放大 200% 不左右捲動 | `E:1112`（在 React 第 1 題量測） |

另外：中途離開再回來從第 1 題接著答 `A:920`；schema 有記載 `norm_token` `T:192`；其他問卷不帶 token 與跳過標記 `T:230`。

## 先看到失敗

- API 與頁面：新測試先跑，19 項失敗，實作後通過。
- 舊行為的測試改成新行為：`test_api.py` 的「IOI-HA 回 404／回 400」、`test_answering.py` 的「IOI-HA 不載入 React」「IOI-HA 沒有載入中提示」。
- 前端：5 項先失敗；「第 1 題完整顯示說明」的決定也是先紅燈再改。
- 新測試讓 `answer-main.test.jsx` 一個既有測試失敗。原因是瀏覽器歷史留著上一個測試的步數，不是程式問題；`beforeEach` 加上重設，跟 `AnswerApp.test.jsx` 一樣。
- e2e：`#81` 那條原本在網頁表單上作答，現在改走 React。另外新增一條完整動線。

## 自動檢查結果（2026-10-23）

- Django：`python manage.py test --settings=config.test_settings --parallel auto`，1061 個，OK。
- 前端：`npm test --prefix frontend`，13 個檔、216 個，全部通過（含首屏 JS 體積檢查）。
- e2e：先 `npm run build --prefix frontend`，再跑 `e2e.main_flow` 整套，97 個，OK。
- Ruff：`ruff check`、`ruff format --check`，無問題。

## 自審（`/mattpocock-skills:code-review`，基準 `origin/main`）

- Standards：沒有硬性違規。修了一個過時註解。四個判斷題沒改：
  - 「不問配戴、要常模」改成問卷定義屬性：網頁版現在也是比對問卷代碼，這次維持一致。
  - React 兩個開關合成一個值：會動到 SADL，超出範圍。
  - API 查詢的 `with_ioi_ha` 參數：只用在送出回應，影響小。
  - 網頁版與 API 外層各有一段「BadSignature → 錯誤訊息」：共用函式已抽出，只剩各自的回應格式。
- Spec：沒有缺漏或做錯；每條驗收條件都有斷言。提醒：
  - 送出回應的分數也為空，規格原本只寫分級與建議。
  - 真瀏覽器裡已經沒有測試送 IOI-HA 網頁表單，只剩 Django 測試保護；roadmap 原本就有「e2e 加 JS 關閉時的表單」待辦。
- 交叉審查：本人決定跳過。

## roadmap

- 「目前進度」與「已完成」加上 #245。
- 拿掉「開放 IOI-HA 寫入 API 時補倒序測試」與「React 版 IOI-HA」兩條。
- 「e2e 加動線」拿掉 IOI-HA，改註明 IOI-HA 網頁表單現在只有 Django 測試保護。

## 本人實際操作驗收

請在手機寬度、放大字級下確認：

1. 有一筆未配戴的 HHIE-S 或 HHIA-S 時，打開 IOI-HA：一進去就是第 1 題，上方看得到「本次常模依據：……」那一句和整段說明；沒有「有沒有戴助聽器」。
2. 到第 2 題：說明收進「這份問卷在問什麼？」，按了可以展開。
3. 每題選項跟紙本一樣（例如第 1 題「沒使用／不到一小時……」）。
4. 答到一半離開再回來：問「要接著答嗎？」，可以從原本那題接著答。
5. 送出後到 IOI-HA 結果頁，分組依據和常模比較跟以前網頁版一樣。
6. 沒有未配戴 HHI 的帳號：第 1 題上方寫「目前沒有完整有效的……；仍可填答」，能送出，結果頁不比常模。

結果：本人 2026-10-23 在本分支的預覽（worktree 的 runserver 8002；8001 被另一個 session 的預覽占用，本人同意破例）實際操作，回覆「#245 實際操作驗收通過」。
