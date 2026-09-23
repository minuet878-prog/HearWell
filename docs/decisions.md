# 技術決策紀錄

紀錄開發過程中「想清楚但容易忘記」的技術決定

---

## 2026-08-31 用 Django Formset 取代手動 POST 驗證迴圈

**情境**
`screening` view 的 POST 邏輯，原本用手動 `for` 迴圈驗證每題分數（型別轉換、值域檢查），
三個 `return render(...)` 幾乎重複，而且沒有處理「使用者少答某幾題」這種情況。

**選項**
1. 繼續手動驗證，補齊漏掉的檢查
2. 用單一 Django `Form`，逐題呼叫驗證
3. 用 `formset_factory` 動態產生對應題數的 Form

**決定**
選 3。`AnswerForm`（`score` 用 `TypedChoiceField` + `coerce=int`；`question_id` 用
`ModelChoiceField` + `HiddenInput`），搭配 `formset_factory(AnswerForm, extra=0)`。

**理由**
題數不是固定的（不同問卷題數不同），`formset` 是 Django 官方為「同一種 Form 要重複
驗證 N 份」設計的工具。比起手動迴圈，型別轉換、choices 驗證都是免費的，錯誤收集也
統一用 `.errors`，不用自己判斷要 return 哪個訊息。

**代價 / 取捨**
- `formset_factory` 的 `extra` 參數預設值是 **1**，不是 0——不知道這件事會導致每次
  formset 都多出一份空白 form（`total_forms` 對不上題數），這是個容易忽略的陷阱。
- `formset.is_valid()` 只驗證「每一份 form 各自的欄位合不合法」，**不會**檢查「送來
  的份數是否等於這份問卷實際的題數」——所以額外加了一層 `set` 比對（`questions` 的
  id 集合 vs `formset` 裡每份 `cleaned_data["question_id"]` 的 id 集合），防止竄改
  `TOTAL_FORMS` 或漏答的情況繞過驗證。
- `zip(questions, formset)` 只能被迭代一次（Python 的 iterator 特性），一定要用
  `list()` 包起來才能安全放進 `render()` 的 context，否則 template 可能因為重複存取
  而拿到空結果。

---

## 2026-08-31 密碼相似度驗證器悄悄失效

**情境**
Code review 指出 `validate_password(password)` 沒有傳入 `user` 參數。設定檔裡列了
四個密碼驗證器，但 `UserAttributeSimilarityValidator`（檢查密碼跟使用者名稱像不像）
的實作，沒收到 `user` 就直接 `return`，等於形同虛設。

**驗證過程**
用 `createsuperuser`（Django 內建指令，內部一定會正確傳 `user`）測試同樣的帳密組合，
確認「密碼跟使用者名稱太像」的檢查確實會被觸發；但走自己寫的 `register` view，同樣
組合完全不會被擋——證實了問題真實存在，不是理論推測。

**決定**
在呼叫 `validate_password` 之前，先用 `User(username=username)` 建構一個「尚未存入
資料庫」的 `User` 物件（只建構 Python 物件，不 `.save()`），把這個物件傳給
`validate_password(password, user=user)`。

**理由**
`UserAttributeSimilarityValidator` 需要一個帶有 `username` 等屬性的 `User` 實例才能
比對，但驗證發生在「使用者真正被建立之前」（要驗證通過才會 `create_user`）。Django
的 `Model(...)` 建構子跟 `.save()` 是分開的兩步，可以先建構出物件、取得需要的屬性，
不用真的寫進資料庫。

**代價 / 取捨**
- 這種「看起來完全正常」的 bug 最危險——設定檔上四個驗證器好好列著，沒有任何錯誤或
  警告，只有讀懂 `UserAttributeSimilarityValidator` 原始碼的邏輯（沒收到 user 就直接
  放行）才會發現。之後任何用到 `validate_password` 的地方，都要記得一併檢查有沒有
  傳 `user`。

---

## 2026-08-31 Python 巢狀 class 的作用域陷阱

**情境**
把 `Question.category` 從自由字串改成 `TextChoices` + `CheckConstraint` 時，把
`Category` 這個 `TextChoices` 定義在 `Question` 內部（跟 `category` 欄位同一層），
結果 `Meta.constraints` 裡引用 `Category.values` 時噴 `NameError`。

**除錯過程**
一開始以為只是 linter 誤判（`makemigrations` 曾經一度沒報錯，但後來確認是沒有真的
存檔跑到新版本）。改成 `Question.Category.values` 之後，又噴另一個 `NameError`——
這次是 `Question` 這個名字本身在自己的 class body 內部還不存在（class 定義要整段
body 執行完，才會把結果綁定到 class 名稱上）。

**決定**
把 `Category` 搬到檔案最頂層（跟 `Question` 平行，不再巢狀在裡面）。

**理由**
Python 的 class body 是「由上到下依序執行」的程式碼區塊，巢狀 class 之間互不相通
（不會像函式閉包那樣自動借用外層變數），只有「模組層級（檔案最上層）」的名字，才能
被任何巢狀深度的程式碼直接看到。`Category` 本身不對應任何資料庫結構（只是 Python
層面定義選項的工具），搬動它的位置不影響 migration，`makemigrations` 也證實了這點
（搬動後沒有產生新的 schema 變化）。

**代價 / 取捨**
- 無明顯代價，純粹是程式碼組織方式的調整。附帶好處：`Category` 放在模組頂層後，
  之後如果 `forms.py` 或別的檔案需要用到這個選項定義，可以直接 import，不用透過
  `Question.Category` 這種比較繞的路徑。

## 2026-09-01 models CheckConstraints 及 on_delete參數

**情境**
發現Answer model的分數設定並未擋住來自前端以外的資料庫寫入，以及思考on_delete的參
數設定為models.CASCADE是否得宜。

**除錯過程**
使用shell手動創建一個Answer的資料並且發現資料庫並未擋住這樣的寫入，on_delete的參數
設定則是在閱讀官方文件以及與claude討論之後發現使用CASCADE會讓相關資料全部被刪掉。

**決定**
- 把Answer的CheckConstraints加入限制寫入的分數一定要為0/2/4其中之一
- 將on_delete改成PROTECT

**理由**
- 透過shell的驗證得知choices只能擋住表單驗證及在admin的下拉式選單生效，並不能擋住來
  自直接呼叫shell寫入
- `on_delete=CASCADE`的問題是會導致一些無形的問題，比如說若我刪除其中一個question
  對應的answer score也會一並被刪除，譬如總分以及結果之類的也會隨之改變，`SET_NULL`
  會造成沒用的資料產生(沒有對應問卷的回答)因此選擇使用`PROTECT`

**代價 / 取捨**
針對`PROTECT`的部分只能夠擋住誤刪的風險，以後仍需新增軟刪除(ex:is_active)欄位

## 2026-09-01 SECRET_KEY 從「安靜使用不安全預設值」改成「正式環境缺少就報錯

**情境**
`SECRET_KEY` 的 fallback 值已經在 git 歷史裡公開過。正式環境若忘記設定環境變數，
程式不會報錯，會安靜用這把已外洩的 key 簽 session/CSRF，任何人都能偽造 session。

**決定**
`DEBUG=True` 維持原本 fallback；`DEBUG=False` 改成不給預設值，拿到 falsy 值就
`raise ImproperlyConfigured`。同時加上 `SECURE_SSL_REDIRECT`、`SESSION_COOKIE_SECURE`、
`CSRF_COOKIE_SECURE`，一樣用 `if not DEBUG:` 包住。

**除錯過程**
用 `DEBUG=False SECRET_KEY=xxx python manage.py check` 模擬正式環境測試：
- `SECRET_KEY=None` 沒觸發——shell 環境變數永遠是字串，讀到的是字串 `"None"`，
  不是 Python 的 `None`
- `SECRET_KEY=""` 也沒觸發——原判斷式只寫 `is None`，沒涵蓋空字串
- 改成 `if not SECRET_KEY:`（利用 truthy/falsy）才一次涵蓋兩種情況

**代價 / 取捨**
`SECURE_HSTS_SECONDS` 刻意沒加——一旦被瀏覽器記住會強制拒絕降級回 HTTP，若 HTTPS
之後出問題會直接卡死使用者，且無法從伺服器端即時補救。等部署環境穩定後再加。

## 2026-09-01 計分邏輯收斂到 Submission model

**情境**
`my_hearing` 用 `annotate` 一次算多筆總分，`submission_result` 用三次 `aggregate` 算
單筆的總分/情緒/社交分數，同一件事寫兩種寫法。`my_hearing` 還會迴圈動態塞
`submission.classified` 到 model instance 上，model 檔案裡完全看不出來有這個屬性。

**決定**
- 一次算多筆：`SubmissionQuerySet.with_scores()`，掛成 `Submission.objects`
- 單筆分數：`total_answer_score`、`emotional_score`、`social_score` 三個 property，
  情緒/社交共用 `_score_by_category` 輔助方法，不再各寫一次 filter+aggregate
- `classified` 也做成 property，內部呼叫 `classify()`，view 裡的猴子補丁迴圈整個刪掉

**踩到的坑**
- `with_scores()` 用了 `annotate(Sum(...))` 之後，發現 `Meta.ordering` 被蓋掉了，
  查了文件後嘗試加 `.order_by()` 解決，結果一開始沒傳參數（空的），反而讓排序
  完全消失。查證後才發現空的 `order_by()` 在 Django 裡是「清除排序」的意思，不是
  「維持原樣」，要明確傳 `"-created_at"` 才對。
- `@property total_score` 跟 `annotate(total_score=...)` 撞名——annotate 想把算好的
  值寫進物件屬性，但 property 是唯讀的沒有 setter，直接噴 `AttributeError`。後來把
  property 改名成 `total_answer_score` 才解決（因為它只在一個地方被用，改名影響小）。

**代價 / 取捨**
無明顯代價，這次是單純的整理，行為完全沒變，template 也完全不用改（因為
`classified` property 回傳的型別跟原本猴子補丁塞的一樣）。

## 2026-09-02 [待定] 問卷適用條件的通用設計（年齡限制等）

**背景**
HHIE-S 有年齡適用範圍，User model 已經有 birth_date 欄位但目前沒用到。之後預計
會新增其他中文版問卷，可能會有各自不同的適用條件（不一定只是年齡）。

**還沒決定的事**
- 要不要先簡單做：Questionnaire 加一個 min_age 欄位，年齡不符合就擋或警告
- 還是等真的知道第二份問卷需要哪些條件之後，再一起設計更通用的機制

**下次要做這件事時，先確認**
第二份問卷實際需要哪些條件，再回頭決定要不要現在就做成通用機制，還是先用簡單的
方式應付得過去就好。

## 2026-09-02 login/register 改成繼承 layout

**情境**
`login.html`、`register.html` 沒用 `extends`，整個 `<head>`（Bootstrap CDN、
static 引入）重複打了一份，只是因為想拿掉導覽列、要置中顯示。

**決定**
`layout.html` 加三個新 block：`extra_head`（給子頁面塞專屬 CSS）、`body_class`
（讓子頁面能控制 `<body>` 的 class）、`nav`（導覽列本身，包起來讓子頁面可以蓋成空的）。
`login.html`/`register.html` 改成 `extends`，`nav` 蓋空、`body_class` 填 `text-center`。

**踩到的坑**
一開始改完還留著 `<!DOCTYPE html>`、`<body>` 這些標籤——但 `extends` 生效後,
block 以外的內容全部不會輸出,這些留著的標籤是無效的,要整個拿掉,只留 block。

**代價 / 取捨**
無明顯代價，純粹是拆重複，畫面效果跟改之前完全一樣。

---

## 2026-09-02 register 表單沒有必填檢查，空 username 直接 500（順手測到的 bug）

**情境**
測試的時候，順手把 register 表單空白送出，結果整個網站噴 500，不是正常的
錯誤訊息。原因是 `<input>` 沒寫 `required`，view 也完全沒檢查欄位是不是空的，
`username` 是空字串一路傳到 Django 內建的 `create_user()`，才在那裡 `raise ValueError`，
但 view 的 `try/except` 沒接住這個例外。

**決定**
view 裡在建立 User 之前，先檢查 `username`/`email`/`password`/`confirmation`
四個欄位是不是空的（用 `not username` 這種寫法，同時涵蓋 `None` 和空字串），
不合格就 render 錯誤訊息。同時在 `<input>` 上補 `required`，讓正常使用者在前端
就會被擋下來，不用等到送出才知道漏填。

**代價 / 取捨**
`required` 只是體驗優化，擋不住繞過前端的請求（curl、改 HTML），真正的防線
還是 view 裡的檢查——這跟前面處理過的好幾個安全性問題是同一個道理：前端擋
使用者體驗，後端擋真正的資料完整性。

## 2026-09-02 classify() 拆掉呈現層，加 template filter 轉顏色

**情境**
`classify()` 原本回傳的 dict 裡直接帶 Bootstrap 顏色（`"color": "success"`），
把「算分級」跟「畫面要顯示什麼顏色」混在同一個 function 裡。而且超出範圍的分數
（<0 或 >40）也是回傳一個看起來正常的 dict（`{"text": "不合規的分數", ...}`），
呼叫端很容易忘記檢查，直接把異常狀況當正常結果用。

**決定**
- `classify()` 只回傳 `text` 跟 `level`（`normal`/`mild_to_moderate`/`severe`），
  完全不含任何顏色字串
- 分數超出範圍改成 `raise ValueError(f"{total_score}是不合規的分數")`，不再假裝
  是正常結果
- 顏色轉換獨立成 `level_to_color(level)`，跟 `classify()` 分開，各自負責一件事
- `my_hearing.html` 需要在 template 裡呼叫 `level_to_color`，改寫成 Django 自訂
  template filter（`templatetags/custom_filters.py`），`views.py` 跟 template
  共用同一份轉換邏輯，不重複定義

**踩到的坑**
- template filter 的 function 一開始想跟 import 進來的 `level_to_color` 同名，
  會造成無限遞迴（——用 `import ... as get_color` 改名解決
- filter 語法一開始寫成 `{{ level_to_color:xxx }}`（冒號），正確應該是
  `{{ xxx|level_to_color }}`（值在前、filter 在後）
- 新增 `templatetags/` 這個 package 之後，`runserver` 沒有自動偵測到，噴
  `TemplateSyntaxError: not a registered tag library`，要手動重啟才抓到

**代價 / 取捨**
  總分上限寫死成 40（HHIE-S 專用）還沒動，先記錄下來，等真的要加第二份問卷、知道實際需要 
  哪些條件時再一起設計

## 2026-09-02 三次分數查詢合併成一次 conditional aggregation

**情境**
`total_answer_score`、`emotional_score`、`social_score` 三個 property 各自獨立
呼叫一次 `aggregate()`，一筆 submission_result 要顯示三個分數，變成 3 次查詢。

**決定**
新增 `_calculate_scores()`，用 `Case`/`When`/`F` 做 conditional aggregation，
一次查詢同時算出 total/emotional/social 三個值，結果存進 `self._scores_cache`。三
個 property 改成從這個 dict 裡各自取值，`_score_by_category` 這個舊的輔助方法整個刪掉。

**踩到的坑**
- `Sum("score")` 沒加 `default=0`，同一個坑踩了第二次——第一次是完全不知道
  Sum 對空集合會回傳 None，這次是改寫時漏抄了舊版本裡已經有的 default=0，
  導致 `classify(None)` 直接 TypeError。這次是自己肉眼發現的，不用再靠報錯提示。

**代價 / 取捨**
練習conditional aggregation 跟物件層級快取這兩個技巧。

## 2026-09-07 加上行動建議

**情境**
classify() 只回傳分級文字，使用者拿到分數之後不知道該怎麼辦，這是 MVP 一直
缺的一段。

**決定**
新增 get_advice(level)，跟 level_to_color() 用同一套「查表」模式，回傳對應
分級的臨床建議文字。三段內容自己寫（normal 建議定期篩檢、mild_to_moderate
建議耳鼻喉科檢查、severe 建議立即就醫並考慮助聽器），每段都附具體情境舉例。
view 裡呼叫 get_advice()，傳到 result.html，用一張獨立卡片呈現，跟上面的
分數區塊做視覺區隔。

**踩到的坑（大多是環境問題，不是程式碼邏輯錯）**
- 換到 Windows 電腦跑測試，兩個用到 static 檔案的測試直接炸掉，錯誤是
  「Missing staticfiles manifest entry」。原因是這台電腦還沒跑過
  `python manage.py collectstatic`——用了 CompressedManifestStaticFilesStorage
  的話，staticfiles 資料夾跟 manifest 清單不會自動產生，每次到新環境都要
  記得先跑一次。
- Windows 上 ruff 存檔不會自動修正，原因是 `.vscode/settings.json` 檔名
  打成 `setting.json`（少一個 s），VS Code 完全不認得，等於沒有這個設定檔。
- 卡片底部邊框「看起來消失」，來回排查了好一陣子，最後用開發工具的元素選取
  框線確認卡片本身完全正常（四邊都有邊框）——純粹是螢幕沒捲到底、或工作列
  自動隱藏造成的視覺誤判，不是 CSS 或程式碼的問題。

**代價 / 取捨**
無明顯代價。這次主要學到的是「跨電腦開發要注意的環境差異」，跟排版問題要
先用開發工具驗證再下結論，不要憑肉眼截圖猜。

## 2026-09-09 default=0 的坑第三次，改用 filter=

**情境**
`total` 有 `default=0`，但 `emotional` 和 `social` 沒有。空的 submission 會回
`{'total': 0, 'emotional': None, 'social': None}`，result 頁面直接印出「情緒分數: None」。

**為什麼會這樣**
`Sum(Case(When(...), default=0))` 這個 default 是 `Case` 的，不是 `Sum` 的。兩個
作用在不同層級：
- `Case` 的 default 管**每一列**（不符合條件就算 0）
- `Sum` 的 default 管**整份聚合的結果**（算完是 NULL 才換成 0）

沒有任何 answer 的時候是 0 列，`CASE` 根本不會被執行，所以 `ELSE 0` 救不了。

但 `ELSE 0` 也不是沒用，它防的是另一種空：「有列，但沒有一列符合條件」。
兩種空各要一個機制，我只裝了一半。

**決定**
三個都改成 `Sum("score", filter=models.Q(...), default=0)`，`Case`/`When`/`F` 拿掉。

**理由**
`filter=` 是把不符合的列**排除掉**，所以兩種空變成同一種，一個 `default=0` 就全包。
要記得的事從 2 件變 1 件，而且三行長得一模一樣，少裝一個一眼就看得出來。

**踩到的坑**
- `_scores_cache` 在測試的時候會造成誤判。在 shell 裡先算過一次分數（結果被快取），再新增一筆
  answer，第二次算還是拿到舊的 0，差點以為改壞了。**要重新從 DB 拿一個新物件。**
  在 web request 裡不會發生（每次都是新物件），但 shell 和測試裡一定會。
- lookup 打成 `question__answer`（想寫 `category`）。這個會直接噴 `FieldError`
  還列出正確選項——打錯欄位名 Django 攔得住，打錯值攔不住。

**還沒做**
測試還沒補（E 滿分 / S 滿分 / 混合 / 完全沒 answer 四個案例），所以現在算是
「改了但沒驗證」。

---

## 2026-09-21 清掉 shell 外洩到正式 DB 的測試資料

**情境**
`db.sqlite3` 裡出現「測試」「測試問卷」兩份問卷、兩個假 user（其中一個 username 是空字串）、
兩筆 submission。是 09-09 那天在 shell 裡驗證計分時建的，直接就落盤成正式資料了。

**為什麼會這樣**
`manage.py shell` 是 autocommit，每個 `.save()` 就是一次獨立的 `BEGIN → INSERT → COMMIT`，
沒有人 rollback。`manage.py test` 完全不同：它另外建一個 `test_` 開頭的資料庫，
而且 `TestCase` 把每個測試方法包在 `atomic()` 裡、跑完 `ROLLBACK`。兩層保護 shell 一層都沒有。

同一段 code 貼進 shell 跑會污染，寫進 `tests.py` 跑不會——差別就在這裡。

**決定**
寫一次性腳本刪掉，但**先跑 dry run**：整段包在 `atomic()` 裡，最後 `raise` 一個自訂例外
強迫 rollback。確認五個 `delete()` 都只動 2 筆，才把 `raise` 拿掉真的執行。

**踩到的坑**
- `try:` 要包在 `atomic()` **外面**。反過來的話，DB 出錯後交易被標成 `needs_rollback`，
  在 `except` 裡再下任何 query 都會噴 `TransactionManagementError`。
- rollback 只還原 DB，不還原 Python 物件。`delete()` 會把 instance 的 pk 設成 `None`，
  rollback 之後它還是 `None`。跟 `_scores_cache` 那次是同一類問題。
- `PROTECT` 擋的是「還有沒有**列**指向我要刪的這一筆」，不是「這張表還有沒有資料」。
  所以 queryset 一定要帶 filter，`.all().delete()` 會把 HHIE-S 的 120 筆 answer 一起帶走。
- 刪除順序是反向拓撲序：Answer → Submission → Question → Questionnaire → User。
  `ProtectedError` 就是在說「這個節點入度還不是 0」。
- `delete()` 回傳 `(總數, {model: 數量})`，要印**整個 tuple**。只印 `[0]` 看不出有沒有
  意外的連鎖刪除——`admin.LogEntry` 對 User 是 `CASCADE`，不是 PROTECT。
- 驗證的預期值一開始寫成 `Answer != 123`，那是把**最大 id 當成筆數**。id 是識別不是序號，
  中間有空號，實際是 122。
- 自訂例外從帶 `__init__` 簡化成 `pass` 之後，忘了改 `raise` 那一行的關鍵字參數，
  結果丟出來的是 `TypeError` 不是自訂例外。改定義要同步改呼叫端，Python 不會提醒。
- `manage.py shell < 檔案` 是把整個檔案一次 `exec`（`commands/shell.py:257`），
  未接住的例外會讓後面全部不執行——驗證區塊就這樣被跳過了三次。

**用過的腳本**（跑完已刪，用 `manage.py shell < 檔名` 餵進去）

dry run 版比這份多兩段：`class DryRunPass(Exception): pass`、區塊最後 `raise DryRunPass`
和對應的 `except`；下面五個預期值則是未刪除的 `3 / 12 / 18 / 6 / 122`。

```python
from django.db import transaction
from django.db.models.deletion import ProtectedError

from screening.models import Answer, Question, Questionnaire, Submission, User

unexpected_answer = Answer.objects.filter(submission__questionnaire_id__in=[2, 3])
unexpected_submission = Submission.objects.filter(questionnaire__id__in=[2, 3])
unexpected_question = Question.objects.filter(questionnaire__id__in=[2, 3])
unexpected_questionnaire = Questionnaire.objects.filter(pk__in=[2, 3])
unexpected_user = User.objects.filter(pk__in=[5, 6])

try:
    with transaction.atomic():
        a = unexpected_answer.delete()
        print(a)
        b = unexpected_submission.delete()
        print(b)
        c = unexpected_question.delete()
        print(c)
        d = unexpected_questionnaire.delete()
        print(d)
        e = unexpected_user.delete()
        print(e)
except ProtectedError:
    print("無法刪除:ProtectedError")

number1 = Questionnaire.objects.count()
number2 = Question.objects.count()
number3 = Submission.objects.count()
number4 = User.objects.count()
number5 = Answer.objects.count()
if number1 != 1 or number2 != 10 or number3 != 16 or number4 != 4 or number5 != 120:
    print("delete異常")
else:
    print("delete正常")
```

**驗證**
刪完跑 `manage.py test`，11 個測試全綠，而且 `db.sqlite3` 的 sha256 前後完全一樣。

**下次**
在 shell 做任何破壞性操作，一律 `atomic()` + 最後 `raise`。真的要驗證行為就寫進 `tests.py`。

## 2026-09-23 ruff 排除 migrations

- migrations 是 Django 自動產生的，31 個 E501 全在裡面，真正的錯誤會被淹沒，linter 等於沒在用。
- 用 `extend-exclude` 不用 `exclude`：`exclude` 會蓋掉 ruff 內建的排除清單（`.venv`、`.git` 那些），`extend-exclude` 是往上加。
- 驗證要做兩個方向：migration 的錯誤不見了，**而且**在 screening 故意加一行沒用到的 import 還抓得到。只驗證前者的話，把全部都排除掉也會「通過」。

## 2026-09-23 Git 流程：main 分岔

- 在本機 main 直接 commit 了 CLAUDE.md 沒 push，同時 PR 在 GitHub 上合併，`git pull` 就分岔了。
- 用 `git pull --rebase` 解決：commit 還沒 push 過，rebase 是安全的。已經 push 的 commit 不要 rebase。
- 設了 `pull.ff only`：main 只該透過 PR 前進，一旦分岔就是流程出錯，要讓 Git 擋下來。
- 教訓：連改文件都要開分支。

## 2026-09-23 ruff 擴充規則集（B / DJ / TID / RUF）

- 一次加一組規則、每組跑一次 check，才分得出哪個錯是哪組抓的。DJ、TID 沒抓到東西，B 抓 2 個、RUF 抓 22 個。
- **RUF001 用白名單不用全域忽略**：中文文案的全形「，」「？」是刻意的，但全域忽略會連西里爾字母、零寬字元這些真正危險的一起放過。`allowed-confusables` 只放行這兩個，以後用到新的全形符號再加。
- **RUF012 list 改 tuple，接受多一個 migration**：`ordering` 從 list 改 tuple，Django 會判定成設定變更，生出 0011。`sqlmigrate` 確認是 no-op。選擇接受它，不用 `noqa`，因為 `noqa` 會在程式碼裡留下越積越多的例外。
- **B905 GET 和 POST 分開處理**：GET 的長度由 `questions` 決定，`strict=True` 是保險。POST 的長度來自使用者，而且 zip 在驗證之前跑，加 `strict` 會讓竄改的送出變成 500。POST 先 `noqa` ＋ `TODO(phase1-7)`，等驗證搬到 form 層再改。
- 坑：`# noqa` 要寫在出錯那一行的行尾，寫在上一行沒效。