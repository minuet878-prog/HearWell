# 第 5 項研究：LINE 內建瀏覽器的訪客流程、「傳給他」預帶文字（2026-11-16）

規劃第 5 項「先研究再提案」的兩題。查不到的寫查不到，要實機測的列在最後。

## 1. 在 LINE 內建瀏覽器做完篩檢，之後想保存走不走得通

**結論**：走得通。在 LINE 裡用 LINE 保存、或用帳號密碼註冊登入，整條路都在同一個分頁；程式裡沒有會自己跳出 LINE 的步驟。iPhone 已實機走通（`docs/verification/issue-506.md` 第 28 條），Android 還沒測。

- 訪客結果存在 localStorage（瀏覽器內建的小儲存區），鍵名 `hearwell:guest-result:<問卷代碼>`，7 天到期（`frontend/src/guest-results.js`）。按保存卡時另在 sessionStorage 記「要保存」，只在同一分頁有效。
- 保存卡全是一般連結，沒有開新分頁；在 LINE 裡顯示 LINE 按鈕、不顯示 Google（`screening/views/common.py`）。
- LINE 保存：`line_save_card` → `oidc.begin()` → LINE 授權（在 LINE 裡會自動登入）→ 回呼 → `/guest_save`。帳號密碼：註冊 → 同意書 → 回原處，沒有 email 驗證。
- 只有兩種情況會離開 LINE，訪客結果都帶不過去：使用者自己按登入頁、註冊頁下方的「用 Safari／Chrome 打開」（`openExternalBrowser=1`，提示框已寫明結果不會跟過去）；從 email 點忘記密碼連結。
- #608 關掉 LINE 自動登入的修正只在 iPhone 主畫面 app 生效，LINE 內建瀏覽器不受影響。

**關掉 LINE、隔天再點同一個連結，結果還在嗎**：查不到官方答案。
- LINE 沒公開內建瀏覽器的資料留多久：<https://help.line.me/line?contentId=20005079>
- iOS 14 起內嵌網頁（WKWebView）預設開 ITP：<https://webkit.org/blog/10882/app-bound-domains/>；「7 天沒互動刪 localStorage」官方只講 Safari 與主畫面網頁：<https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/>。就算適用，也是從最後一次互動起算，不會比我們自己的 7 天更早。
- Android 的 LINE 有沒有另外清，查不到。

## 2. 「傳給他」能不能預先帶好文字

**結論**：LINE 官方分享網址可以帶文字；手機分享選單（Web Share API，`navigator.share`）分享到 LINE 會不會留下文字，查不到，要實機測。

- `https://line.me/R/share?text={文字}`：打開 LINE 的「分享給」畫面，文字要編碼，網址直接寫在文字裡：<https://developers.line.biz/en/docs/line-login/using-line-url-scheme/>
- `https://social-plugins.line.me/lineit/share?url=…&text=…`：自訂圖示的分享鈕可同時帶網址和文字：<https://developers.line.biz/en/docs/line-social-plugins/install-guide/using-line-share-buttons/>
- iOS 上有人回報同時給 text 和 url 時，部分 App 只收到網址：<https://developer.apple.com/forums/thread/662629>。常見繞法是把網址併進 text。
- 在 LINE 內建瀏覽器裡：Android WebView 不支援 `navigator.share`（MDN 相容資料），分享按鈕不會出現；iOS WKWebView 12.2 起支援。
- 現有做法：`share-button.js` 只送 `{title, url}`，有分享選單才出現；沒有時 `copy-link.js` 的「複製網址」補上。家人專區「傳給家人」與分享報告頁都用它。

## 要實機測（寫進驗收）

- iPhone、Android：在 LINE 裡做完篩檢，完全關掉 LINE，隔天點同一個連結，首頁還有沒有結果。
- Android：在 LINE 裡用 LINE 保存（#506 只測了 iPhone）。
- iPhone Safari、Android Chrome：分享選單只給網址、給文字加網址、網址併進文字，三種各傳到 LINE，看聊天室收到什麼；`line.me/R/share?text=` 能不能帶出中文。
- iPhone 的 LINE 內建瀏覽器裡有沒有分享按鈕。
