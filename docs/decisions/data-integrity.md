# 資料模型與資料完整性

← [回到索引](README.md)

---

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
