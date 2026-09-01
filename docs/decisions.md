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
