# 0072 每頁送 Content-Security-Policy，內嵌 script 用 nonce

日期：2026-11-19（本人審定，資安健檢後選擇放進同一個 PR）

## 情境

目前沒找到 XSS，但萬一有，瀏覽器會照跑塞進頁面的 script。Django 5.2 沒有內建 CSP。

## 決定

- 每個回應都帶 CSP：script 只能來自本站檔案，或帶有該次回應 nonce 的內嵌 script；不准外掛（object）、不准被別站嵌入、`base` 只能是本站。
- 樣式仍允許內嵌（`style-src 'unsafe-inline'`）：模板和信件大量用 style 屬性，nonce 標不了。
- `test_content_security_policy` 檢查每個模板的內嵌 script 都有 `nonce="{{ request.csp_nonce }}"`；e2e 的 `ContentSecurityPolicyTest` 開主要頁面確認瀏覽器沒有擋到東西。

## 理由

用 nonce 不用改寫現有的內嵌 script，也不用維護 hash 清單。

## 代價

新增內嵌 script 一定要加 nonce，否則不會執行（測試會抓到）。不能用 `eval`：Playwright 的 `wait_for_function` 也因此改成 e2e 的 `wait_until`。內嵌樣式沒有擋，防護不完整。以後要接外部服務（字型、分析），要先改 CSP。
