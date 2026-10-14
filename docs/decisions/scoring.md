# 計分與分級

← [回到索引](README.md)

---

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

---

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

---

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

---

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

## 2026-10-14 classify() 改門檻表
- Why? 40 分寫死在 if/elif 裡，加第二份問卷分數一超過就 500，歷史頁整頁打不開
- 門檻表放 `scoring.py` 的 `THRESHOLDS`，用 `Questionnaire.code`（新欄位）當 key，不用顯示名稱，免得 admin 改名分級就壞掉。不放資料庫，臨床規則不該在 admin 被隨手改
- 滿分＝最後一級的上限，不另外存 40
- 分數超出範圍或問卷沒有門檻表 → 顯示「無法判讀」＋寫 error log，不 500
- 結果頁改走 `submission.classified`，跟歷史頁同一條路
- 這次只放 HHIE-S，HHIA-S 等真的加題目再補
- 坑：已經有資料的表不能直接加「必填＋唯一」的欄位，migration 拆成兩個檔（先加可空欄位補資料、再收緊）。放同一個檔在 PostgreSQL 可能撞 pending trigger events
- 坑：歷史頁模板呼叫兩次 `submission.classified`（顏色一次、文字一次），log 寫兩次，用 `{% with %}` 改成算一次
- 坑：舊測試建問卷沒給 code，預設是空字串，測試照過但其實走到「無法判讀」，補上 code

---

## 2026-10-14 歷史頁 N+1、分數收成一條路
- Why? 歷史頁總分用 `with_scores()` 的 annotation，分級卻走 `total_answer_score` 每筆各查一次，N 筆就多 N 次查詢（1 筆 4 次、5 筆 8 次），而且同一頁的分數算了兩種方法
- 三個 Sum（總分／情緒／社交）抽成 `_score_expressions()`，全專案只有這一份。列表用 annotate、單筆用 aggregate，`_calculate_scores()` 看到已經 annotate 過就直接用
- 測試比「1 筆跟 5 筆查詢數一樣」，不寫死次數；同時斷言真的列出 5 筆，不然列表壞掉什麼都沒查也會假通過
- 坑：`with_scores()` 不能跟篩 answers 的 filter 串在一起用，Django 會多 JOIN 一次或先篩掉答案，分數會錯（審查時重現過 26 變 20 或 130）

---

## 2026-10-14 快照決策（1-5）
- 先查清楚：總分其實不會漂移，因為每題分數存在 `Answer.score`。會漂的是題目文字、分類（→ 情緒／社交分項）、門檻和建議文字（→ 歷史分級）
- 題目作答過就不能改，要改就出新版問卷（新 pk、新 code）。HHIE-S 是標準化量表，措辭本來就不該變。admin 用 `get_readonly_fields` 鎖住；問卷有作答紀錄後 `code` 也鎖，名稱可以改
- 門檻或建議文字將來要改：用規則版本號（Submission 記當時用哪一版），總分照樣不存。現在只有一版，等第一次真的要改再做
- `completed_at` 現在不加：1-1 已經擋住空作答，「未完成」要等 D2 中途儲存才會出現
- 審查時發現 Submission／Answer 用預設 admin，可以直接改作答的問卷或分數，等於改寫健康紀錄 → 改成 admin 只能看（不能新增、修改、刪除）
- 已上線的問卷不能加題，靠規則不靠程式（只有我會在 admin 加題）
- 之後做「使用者刪除自己的資料」（個資法）要另外寫流程，不能靠 admin，admin 現在刪不了作答紀錄
- 坑：`build.sh` 每次部署都 `loaddata`，`loaddata` 不經過 admin 也不經過 `save()`，所以 fixture 裡上線過的題目不能改，靠規則不靠程式
