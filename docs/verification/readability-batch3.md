# 可讀性第 3 批：密碼字數、色帶放進結果框、同意書分三組（小改動，無 issue）

日期：2026-11-16。基準：`ac89d53`（origin/main）；分支：`feat/readability-batch3`。依據：[可讀性檢查](../planning/readability-review-2026-11-16.md)「第 3 批選定」、[第 3 批設計圖](../planning/redesign/mockup-readability-batch3.html)。

狀態：本人實際操作驗收通過（2026-11-16）。

- 本人在設計圖選定：密碼規則 B、分數色帶 A、同意書 A（2026-11-16）。換題淡入已經有了，這批不做。
- 開工前本人決定（2026-11-16）：同意書只分組不改字，**不升版**（[ADR 0061](../adr/0061-regrouping-consent-highlights-keeps-the-version.md)）；三個小標「用來做什麼」「登入和寄信時」「存在哪裡、您的權利」照草稿定稿；訪客保存後的大確認框（回饋感 F3）留給回饋感那批；色帶只搬位置，**不需要交叉審查**（沒改計分、分級、門檻，沒有 migration，沒碰權限）。
- 走小改動流程（跳過拷問、規格、拆票）。
- 沒有操作真實資料。測試在臨時測試資料庫上。

## 行為

| 項目 | 現在 |
|---|---|
| 密碼字數（註冊頁、設新密碼頁） | 密碼欄下面、規則上面多一行：打了 5 個字是灰字「已經輸入 5 個字，還差 3 個」，滿 8 個字變綠字「✓ 已經輸入 8 個字」；還沒打或清空時不顯示。四條規則照舊、不打勾（#332）。字數跟伺服器同一種算法（一個表情符號算一個字）。螢幕閱讀器在停止打字 1 秒後唸一次目前字數，不會每按一鍵就唸。沒有 JavaScript 時這一行不出現，頁面跟以前一樣。「密碼確認」欄沒有字數 |
| 分數色帶（HHIE-S、HHIA-S、THI 結果頁） | 從「看完整說明」搬進結果框，放在大字分級名稱下面、「上次……」上面，白底襯著；色帶下面那行分級名稱拿掉，只留 0 和滿分。摺疊裡不再有色帶。色帶不動畫、對螢幕閱讀器隱藏（分數和分級文字照舊唸）。門檻、分級、顏色沒動；「無法判讀」照舊沒有色帶 |
| 同意書重點（同意頁、隱私權說明最上面） | 八條分成三組，每組一個小標：「用來做什麼」（3 條）、「登入和寄信時」（3 條）、「存在哪裡、您的權利」（2 條）。字一個都沒改，只有「結果只是參考，不是醫療診斷。」為了分組移到第一組。全部直接看得到。同意書維持第 8 版，按鈕字不動 |

跟設計圖不一樣的地方：

- 同意書小標的顏色用網站小標的深藍灰（`--color-heading`，ADR 0043 標題規則），設計圖畫成主色藍。
- 程式裡把結果頁色帶下面那行分級名稱的資料（`current_text`）一起拿掉了，因為沒有地方再用到。

## 驗收對照

勾選代表自動驗證，不代替本人操作確認。

| 需求 | 驗證 | 證據 |
|---|---|---|
| 註冊頁、設新密碼頁都有字數那一行，最少字數跟伺服器的規則一致，預設隱藏（沒有 JavaScript 時不出現），有給螢幕閱讀器的狀態區 | ✅ 自動 | `screening/tests/test_accounts.py:711`；`screening/tests/test_password_reset.py:221` |
| 還沒打不顯示；打 5 個字「已經輸入 5 個字，還差 3 個」；8 個字「✓ 已經輸入 8 個字」；清空又不顯示 | ✅ 自動 | `frontend/src/password-count.test.js:37`、`:42`、`:49`、`:63` |
| 跟伺服器一樣算字（表情符號算一個）；瀏覽器自動填入的密碼也會算 | ✅ 自動 | `frontend/src/password-count.test.js:57`、`:77` |
| 螢幕閱讀器停止打字後才唸，不是每按一鍵 | ✅ 自動 | `frontend/src/password-count.test.js:69`；e2e `e2e/main_flow.py:1255` |
| 真的瀏覽器：在欄位下面、規則上面；灰字變綠字；320px、225% 字級不超出 | ✅ 自動 | `e2e/main_flow.py:1255` `test_register_counts_the_passwords_characters` |
| 密碼欄本身仍不打勾（#332） | ✅ 自動 | `screening/tests/test_accounts.py:461`（改寫：密碼欄只有字數的狀態區，沒有打勾的） |
| 色帶在結果框裡、分級名稱下面；只剩兩端；摺疊裡沒有、整頁只有一條 | ✅ 自動 | `screening/tests/test_result_score_bar.py:86`；`screening/tests/test_result_pages_redesign.py:131` |
| 色帶在「上次……」上面 | ✅ 自動 | `screening/tests/test_result_score_bar.py:100` |
| HHIA-S、THI 也在結果框裡 | ✅ 自動 | `screening/tests/test_result_score_bar.py:112`；`screening/tests/test_thi_support.py:30` |
| 白底；第一個畫面看得到色帶，「建議您下一步」的按鈕仍在 390×844 手機的第一個畫面 | ✅ 自動 | `e2e/main_flow.py:13797` |
| 不動畫 | ✅ 自動 | `e2e/main_flow.py:9802`（原有，改成不用先點開摺疊） |
| 螢幕閱讀器照舊唸分數和分級，色帶隱藏 | ✅ 自動 | `screening/tests/test_result_score_bar.py:185`；`screening/tests/test_result_pages_redesign.py`（結果框文字比對時去掉隱藏的色帶） |
| 「無法判讀」沒有色帶；門檻與色段比例不變 | ✅ 自動 | `screening/tests/test_result_score_bar.py:177` 及同檔色段斷言（原有） |
| 結果頁 320px、200% 字級不超出；色帶兩端 1rem、在畫面內 | ✅ 自動 | `e2e/main_flow.py:1425`；`e2e/main_flow.py:10579` |
| 同意頁和隱私權說明：三個小標、每組的字逐字相同、順序照設計圖、不在摺疊裡 | ✅ 自動 | `screening/tests/test_consent.py:154` |
| 重點只寫在一個檔案 | ✅ 自動 | `screening/tests/test_consent.py:177`（原有） |
| 不升版 | ✅ 自動 | `screening/tests/test_consent.py:172` |
| 隱私權說明的提示框照舊；兩頁平面、標題樣式照舊；320px、200% 不超出 | ✅ 自動 | `screening/tests/test_account_redesign.py:150`；`e2e/main_flow.py:8193`、`:8213` |
| 實際走起來 | ✅ 本人 | 見下方「人工驗收」 |

## 測試與審查

- 單元測試 `manage.py test --settings=config.test_settings --parallel 4`：2619 項全過。
- 前端 `npm test --prefix frontend`：571 項全過。
- 端對端（先 `npm run build --prefix frontend`）`e2e.main_flow --parallel 4`：441 項全過。
- `ruff check .`、`ruff format --check .`：全過。
- 第二次完整 e2e 時，新的字數測試在 390px 寬偶爾失敗（量到的位置差 2.5px，單獨重跑 3 次失敗 2 次）。原因：字型載入後網站開啟平滑捲動，Playwright 打字前把欄位捲進畫面，三個元素分三次量，各自量到捲動中的不同位置。改成同一次量三個元素後連跑 5 次都過，整套再跑一次全過。網站本身的行為沒問題。

自審（`/mattpocock-skills:code-review`，基準 `origin/main`，兩個代理分別看規範與規格，只看 diff、規劃文件和設計圖）：

- Standards：沒有硬性違規。改了 2 項判斷題：測試裡 `HIGHLIGHT_GROUPS[1][1][1]` 這種看不出是哪一條的索引，改成用開頭字找（`highlight("用 LINE 登入時")`）；兩個測試重複切出結果框，改成共用 `result_box()`。沒改：`data-min="8"` 寫在模板（兩個測試把它跟伺服器規則綁在一起，要從程式傳進來得多改 view）；白底寫 `#fff`、e2e 顏色寫成 rgb 字串、小標的 `mt-4` 寫兩次（都照檔案裡現有的寫法）。
- Spec：三項都有做到、沒有範圍外的改動。改了：#461 的 e2e 還在斷言「第一個畫面看不到色帶」（第一次完整 e2e 也抓到），改成色帶看得到、按鈕仍在第一個畫面；舊的 `ul.tip-box` 規則因為外面多包一層而套不到，改成對到裡面的清單，隱私權說明的項目符號縮排維持原樣；規劃文件補上本人開工前的四個決定。補了 4 個證據：設新密碼頁的隱藏與狀態區、白底、HHIA-S 和 THI 在結果框裡、重點不在摺疊裡。設新密碼頁沒有另外跑 200% 字級的 e2e：它跟註冊頁用同一個模板片段和程式，註冊頁的 225% 已經驗過。
- 第一次完整 e2e 另外抓到我寫的新測試在開頁面之前就找元素，已改。

改了的既有測試（刻意改變內容或位置，不是行為壞掉）：

- `screening/tests/test_result_score_bar.py`、`test_result_types.py`、`test_result_from_answers.py`、`test_result_pages_redesign.py`、`test_thi_support.py`、`e2e/main_flow.py`（三處）：色帶的位置與拿掉的那行分級名稱。
- `screening/tests/test_consent.py`、`test_account_redesign.py`：重點分三組、順序跟著變。
- `screening/tests/test_accounts.py`、`test_pages.py`：密碼欄多了字數的狀態區與程式。

## 人工驗收

8001 開在這個分支的 worktree（前端已建置；看到舊樣子先按 Cmd＋Shift＋R）：

```bash
cd /Users/huangweizhe/HearWell/.claude/worktrees/readability-batch3 && /Users/huangweizhe/HearWell/py313/bin/python manage.py runserver 8001
```

用手機寬度操作：

1. 登出 → 註冊頁：在「密碼」打 5 個字，下面出現灰字「已經輸入 5 個字，還差 3 個」；打到 8 個字變綠字「✓ 已經輸入 8 個字」；四條規則照舊。（不用真的送出註冊。）
2. 登入有 HHIE-S 紀錄的帳號 → 我的紀錄 → 打開一筆結果：色帶在大字分級下面、白底，下面只有 0 和 40；「看完整說明」裡沒有色帶。「建議您下一步」的按鈕往下移約 70px（設計圖標的代價）：分級沒變時在 390×844 手機第一個畫面看得到（e2e 驗過）；分級有變、多兩行「分級從……變成……」時，375×812 手機上按鈕被分頁列蓋住約 63px，要稍微往下捲（2026-11-16 代理在預覽量到，本人 submission 41）。
3. 隱私權說明最上面「先看重點」：三個小標、八條都在、字跟以前一樣。
4. （同意頁要等同意書升版才會看到；這次不升版，跟隱私權說明是同一塊，看 3 即可。）
5. 字放大到 200% 再看 1、2：不會左右捲動。

結果：2026-11-16 本人在 8001 實際操作，回覆「全部通過」。分級有變時主按鈕要稍微往下捲這一點，本人看過後一併接受，維持設計圖 A。
