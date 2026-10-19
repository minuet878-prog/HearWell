# Phase 5 React 作答頁：實作計畫

規格：[phase5_react_answer.md](../../specs/phase-05/phase5_react_answer.md)（已確認 2026-10-16）

## 整體做法

1. Django 照舊畫出完整的作答表單（JS 失敗時的備用）。
2. 頁面另外載入 `answer.js`。它先呼叫 `GET /api/questionnaires/{id}/` 拿題目；**拿到了才把 Django 表單藏起來、換成 React 版**。API 失敗或 JS 壞掉，使用者看到的就是原本的表單（漸進增強）。
3. React 版一題一頁，送出走 `POST /api/submissions/`（帶收據編號＋CSRF token），成功後 `location.assign("/submission/<id>")` 到現有結果頁。
4. 沒答完的答案存在 `localStorage`（瀏覽器內建的「這個網站專用小儲物櫃」），一份問卷一格。

## 要改／新增的檔案

### 前端（`frontend/`）

| 檔案 | 動作 | 內容 |
|---|---|---|
| `src/draft.js` | 新增 | 讀／存／刪保留的答案：`loadDraft(questionnaireId, userId, questionIds)`（過期、別人的、壞掉的、題目對不上 → 刪掉並回 null）、`saveDraft()`、`clearDraft()`、`clearAllDrafts()`（登出用）。所有存取都包 try/catch：瀏覽器不給存就當作沒有 |
| `src/draft.test.js` | 新增 | 驗收「中途儲存」10 條裡的資料規則（7 天、換帳號、壞資料、無痕模式、HHIE-S／HHIA-S 分開） |
| `src/AnswerApp.jsx` | 新增 | 作答畫面：「要接著答嗎？」→ 助聽器題 → 第 1–N 題。原生 `<input type="radio">` 包在 `<fieldset><legend>`（螢幕閱讀器自動唸「單選、已選取」，鍵盤方向鍵可選）；換頁後焦點移到題目；`history.pushState` 讓上一頁＝上一題；送出中停用按鈕；錯誤訊息見下方 |
| `src/AnswerApp.test.jsx` | 新增 | 驗收「作答與送出」11 條＋「接著答」流程（mock `fetch`、jsdom 的 `localStorage` 和 `history`） |
| `src/answer-main.jsx` | 新增 | 進入點：找到容器 → 讀 data 屬性（問卷 id、使用者 id、CSRF token）→ 掛上 `AnswerApp`；題目載入成功時把 Django 表單設成 `hidden` |
| `src/logout.js` | 新增 | 進入點：登出表單送出時呼叫 `clearAllDrafts()`（約 0.3 KB） |
| `src/bundle.test.js` | 新增 | 用 Vite 在記憶體裡建置一次（不寫檔），檢查：作答頁入口＋它引用的檔案裡沒有 recharts、brotli 加總 ≤ 80 KB |
| `vite.config.js` | 修改 | 單一入口改成三個：`trend-chart`、`answer`、`logout`；輸出檔名 `[name].js`；輸出資料夾改名 `static/screening/frontend/`（B1）。共用的 React 會自動拆成一個共用檔 |

### Django

| 檔案 | 動作 | 內容 |
|---|---|---|
| `screening/templates/screening/screening.html` | 修改 | 問卷名稱、題數、說明搬到 `<form>` 外面（React 版也看得到，文字不變）；非 IOI-HA 才放 React 容器（`data-questionnaire-id`、`data-user-id`）和 `answer.js`；表單加 `id` 讓 JS 找得到 |
| `screening/templates/screening/layout.html` | 修改 | 登出表單加 `id`；登入時載入 `logout.js` |
| `screening/static/screening/styles.css` | 修改 | 作答頁樣式：大選項（≥ 2.75rem 高、整塊可點）、上一題／下一題按鈕、進度；全部 `rem` |
| `screening/tests.py` | 修改 | 新增 `ReactAnswerPageTests`：HHIE-S／HHIA-S 頁有容器、data 屬性、`answer.js`，**Django 表單仍完整存在**；IOI-HA 頁沒有；登入的頁面有 `logout.js`、未登入沒有；vite 設定的入口名稱與 template 一致。既有 `test_chart_js_path_matches_vite_output` 可能要跟著改字串 |

`views.py`、API、model 都**不改**（使用者 id 和 CSRF token template 本來就拿得到）。

## 錯誤訊息對照

| 情況 | 畫面 |
|---|---|
| 網路斷、5xx | 「送出失敗，請再按一次送出」 |
| 400 | 「送出的資料有誤：」＋ API 回的中文訊息 |
| 403 | 「登入已經過期，請重新登入」＋登入按鈕（`/login?next=/questionnaire/<id>`） |
| 409 | 見下方待決 A |
| 載入題目失敗 | 不顯示 React，留著 Django 表單（使用者照常作答） |

## 測試順序（第 5 步）

1. 先寫 `draft.test.js`、`AnswerApp.test.jsx`、`bundle.test.js`、Django `ReactAnswerPageTests` → 跑一次確認**全部失敗**。
2. 再寫實作讓它們通過。
3. 最後 `npm run build`，確認輸出的檔案、bundle 大小，並跑一次全部測試。

## 需要你決定的

> 2026-10-16 本人確認：A1、B1，計畫同意。

- **A. 409（收據編號用過、內容不同）怎麼顯示？** 規格沒寫到。會發生的情況：送出其實成功了、回應沒收到，使用者重新整理、改了一個答案再送。
  - A1（建議）：「這份作答之前已經送出過」＋「到我的紀錄看結果」按鈕，並清掉保留的答案。第一次送出的那份才是真的存下來的。
  - A2：自動換新的收據編號重送。代價：會存成兩筆，違背規格的目標。
- **B. 建置輸出的資料夾名稱**：現在叫 `static/screening/trend/`，之後會放作答頁和登出的 JS。
  - B1（建議）：改名為 `static/screening/frontend/`。要跟著改 `.gitignore`、`my_hearing.html` 一行、兩個既有測試的路徑字串。
  - B2：不改名。代價：資料夾叫 trend，裡面卻有作答頁的檔案。

## 風險

- **共用檔的網址**：Vite 會把 React 拆成共用檔，入口用相對路徑 `import "./xxx.js"` 引用它。whitenoise 的 manifest 只改寫 template 裡的 `{% static %}`，不改 JS 裡的 import；collectstatic 會同時保留原檔名，所以還是載得到。實作時會在 `npm run build` ＋ `collectstatic` 之後實際確認（你那邊人工驗收時也會順帶驗到）。
- **jsdom 的 history**：`history.back()` 觸發 `popstate` 是非同步的，測試要用 `waitFor`。

---

## 審查後修改（2026-10-16，F1–F3 本人交給我，F4、F5 本人同意修）

審查報告：[phase5_react_answer_review.md](phase5_react_answer_review.md)。F1 等本人在真的瀏覽器確認現象後另外提修法。

| # | 根本原因 | 修法（修在源頭） | 動到的檔案 | 回歸測試 |
|---|---|---|---|---|
| F2 | `isUsable` 用 `draft.answers ?? {}`，把「沒有 answers／是 null」當成合法 | `answers` 必須是物件（不是 null、不是陣列）才算可用。同一個原因再檢查其他欄位：`key`、`wearing`、`step` 已經是嚴格檢查，沒有同樣問題 | `draft.js` | `draft.test.js` 的 `it.each` 加「answers 是 null」「沒有 answers」「answers 是陣列」 |
| F3 | 存草稿的 effect 只看「有沒有答案」，不管這份作答是不是**已經結束**（409 或已送出成功）；之後只要 `form` 有變動（例如上一頁）就又存回去 | 加一個「已結束」標記（ref），409 與送出成功時設成 true，存草稿前先檢查。同一個原因的另一處：送出成功、正在跳轉時按上一頁，也會把用過的收據編號存回去，一併擋住 | `AnswerApp.jsx` | 409 → 上一頁 → 草稿仍是 null；成功 → 上一頁 → 草稿仍是 null |
| F4 | 送出中仍可以換頁、改答案，`choose()` 把「送出中」狀態改回 idle，送出鈕又能按 | 送出中把整組選項停用（`<fieldset disabled>`，瀏覽器內建：裡面的選項全部不能點）＋停用「上一題」。這樣就算用瀏覽器上一頁換頁，也改不了答案、送不了第二次 | `AnswerApp.jsx` | 送出中：「上一題」停用、選項停用、POST 只有 1 次 |
| F5 | 第一次載入（沒有草稿）也呼叫 `begin()`，`begin()` 一律把焦點移到題目 | `begin()` 加參數，只有使用者按「接著答」「重新開始」時才移焦點 | `AnswerApp.jsx` | 載入後焦點不在 legend |
| F7 | 測試沒有先把焦點放到按鈕上，焦點本來就在 legend（就是 F5） | 測試在按「下一題」前先 `button.focus()`；上一頁（popstate）也加同樣斷言 | `AnswerApp.test.jsx` | （本身就是測試） |
| F8 | 測試的 `reload()` 保留舊歷史紀錄，誤打誤撞過關 | 跟 F1 一起處理 | — | — |

不改：F6、F9（理由見審查報告最後）。
