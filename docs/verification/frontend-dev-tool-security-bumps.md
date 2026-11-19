# 前端開發工具的套件升級（vite、undici）

日期：2026-11-19。分支：`chore/frontend-dev-tool-security-bumps`。沒有規格 issue：2026-11-19 資安健檢列出這兩個套件，本人決定另開小 PR，不放進已合併的 #735。

不需要交叉審查：只動前端開發工具（`frontend/package.json`、`frontend/package-lock.json`），沒碰計分、門檻、資料 migration 或權限。

## 升級內容

| 套件 | 舊版 → 新版 | 怎麼進來的 | 影響範圍 |
|---|---|---|---|
| vite | 8.3.2 → 8.3.8 | 直接相依（`devDependencies`） | 已知漏洞都在開發伺服器（`vite dev`）；正式站不跑開發伺服器，部署時 `build.sh` 只用它建置 |
| undici | 8.12.1 → 8.12.4 | jsdom 帶進來（jsdom 要求 `^8.10.2`，`package.json` 不用改） | 只在前端測試（vitest＋jsdom）用到 |

vite 8.3.8 要求較新的 rolldown（打包器）和 postcss，所以這兩個連帶升級：rolldown 1.2.14 → 1.2.19（含各平台的 binding 與 `@oxc-project/types`）、postcss 8.5.30 → 8.5.33。新版 rolldown 多了一個 wasm 平台用的選用套件（`@rolldown/binding-wasm32-wasi` 和它的 `@emnapi/*`、`@napi-rs/wasm-runtime`、`@tybys/wasm-util`、`tslib`），lockfile 標為 optional，Mac 和 Linux 不會安裝。其他套件都沒動。

## 完成條件 → 證據

| 條件 | 證據 |
|---|---|
| `npm audit` 不再列出 vite、undici | 升級前：2 個 high（vite、undici）。升級後 `npm audit --prefix frontend`：`found 0 vulnerabilities` |
| 前端測試全過 | `npm test --prefix frontend`：771 個測試通過 |
| 前端建置成功 | `npm run build --prefix frontend` 成功 |
| 後端測試全過 | `manage.py test --settings=config.test_settings --parallel`：3226 個通過、1 個跳過（Linux 才跑的記憶體上限） |
| e2e 全過 | `manage.py test --settings=config.test_settings e2e.main_flow --parallel 4`：480 個通過（用新版 vite 建置的前端） |

## 建置產出比對

部署會用新版 vite 建置，所以用同一份程式分別以 vite 8.3.2 和 8.3.8 建置一次比對：

- 檔案數相同（871 個）。
- `site.css` 和字型檔完全相同。
- JS 有差異，是新版 rolldown 壓縮程式碼的方式不同（變數命名、排列），總大小 643,610 → 643,578 bytes。畫面行為由 e2e 驗證。

## 合併後要做的

- 主資料夾的 `frontend/node_modules` 還是舊版，合併後在主資料夾跑一次 `npm ci --prefix frontend`。
- 部署照舊：`build.sh` 本來就會 `npm ci`，會自動裝新版。

## 本人驗收

（待本人操作）
