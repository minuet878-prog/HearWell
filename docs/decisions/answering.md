# 作答與驗證

← [回到索引](README.md)

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

## 2026-10-01 修復空的Submission

- 開發初期用來測試的Submission當時的問卷以及題目都未設計好(無題目)在formset的驗證邏輯時因為(set() == set())會通過
- 目前處理是用一個guard clause(直接擋掉)但預計未來會加入填答到一半的狀態
- 如果不加default=0的話沒有任何 answer 的 Submission會讓None 傳進 classify() 後，None < 0 會丟 TypeError，頁面直接 500。
  現在確定不會有沒有題目的問卷的話default=0就不會將傳進去的None偽裝成0分
- 原本的空白資料因為我之前遷移資料庫到postgres所以不需要再清

---

## 2026-10-05 Screening驗證邏輯搬到forms
- Why? 原本用的set comprehension會把重複的題目吃掉,如果使用者11題的submission過來(第11題重複第1題)程式不會報錯,而是順利進入到
  `transaction.atomic()`那邊然後Answer會撞到一題對應一個答案的unique constraint而報錯->500->Submission因為Answer失敗消失
  ,之後要進行DRF的重構,怕view要寫兩次所以搬到form層
- 坑:在寫BaseAnswerFormSet的時候覆寫`clean()`時原本想用raise自訂exception但會報錯->500,一定要用`forms.ValidationError`
- `screening view`裡面POST分支的`question_form`只有在AnswerFormSet驗證失敗時才會用到(用來顯示畫面),如果設定`strict=True`的話
  `zip()`如果兩邊長短不相等時會直接報錯->500 改用`strict=False`少了重複的那題不影響使用者體驗
