# 0056 Google、LINE 登入自己寫，不用套件

日期：2026-11-13（本人審定，[登入拷問決定](../planning/open-access/login-grill-decisions.md) Q1）

## 情境

要加 Google、LINE 登入。可以用 django-allauth、Authlib，或自己照 OpenID Connect 流程寫（比較見[登入研究](../planning/open-access/login-research.md)第 1 節）。

## 決定

自己寫一個很薄的用戶端，只服務 Google、LINE 兩家，只用 Python 內建的函式庫，不加套件。多一張「登入方式」表，存是哪一家和對方給的代號。

## 理由

- 我們的規則（只存代號、同 email 不合併、先同意書、訪客結果保存、新增／移除登入方式）不管用哪個套件都要自己寫。allauth 最大的價值就在帳號邏輯，偏偏是要改掉的部分。
- 兩家官方文件讓協定這段很小：Google 從 token 端點直接拿到的身分證明可以不驗簽章，LINE 有驗證端點替我們驗。
- LINE 只拿代號，allauth 做不到；Authlib 很可能驗不過 LINE 的身分證明。

## 代價

- 協定層的錯誤沒有套件替我們擋：state、nonce、PKCE、回呼網址、身分證明的每一條檢查都要有「被竄改就失敗」的測試，並交叉審查。
- 兩家改規則時要自己追。
- 以後要加第三家，得照同樣的方式再寫一家，或回頭換套件。
