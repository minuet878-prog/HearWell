# 助聽器類型章節改用字

日期：2026-10-27。基準：`59a4c8b`（origin/main）；分支：`refactor/types-and-prices-wording`。沒有規格 issue（本人自己改字）。

狀態：**等本人驗收**。自動測試全過。只改「類型與價格」章節的文字，沒有 migration，沒有操作真實資料。只改字、不碰計分、門檻、資料或權限，依 AGENTS.md 不需要交叉審查。

## 改了什麼

| 位置 | 改前 | 改後 |
|---|---|---|
| 外型清單第二項 | 受話器外置型（耳道接收型） | RIC（迷你耳掛型） |
| 段落標題 | 集音器不是助聽器 | 擴音器／輔聽器不是助聽器 |
| 段落第二點 | 集音器、輔聽器一般不是醫療器材…… | 擴音器、輔聽器一般不是醫療器材…… |

- 本人的 commit 用半形「( )」「/」；2026-10-27 本人決定改成全形，跟網站其他地方一致。
- `GLOSSARY.md`：2026-10-27 本人決定詞條「集音器」改名「擴音器」，「集音器」移到避免混用。

## 驗收對照

| 驗收 | 驗證 | 證據 |
|---|---|---|
| 章節顯示三處新用字 | ✅ 自動（既有斷言改成新字） | `screening/tests/test_guide_types.py` 的 `SENTENCES` |
| 頁面不出現品牌名 | ✅ 自動（既有，允許清單加 RIC） | `test_guide_types.py` 的 `test_the_only_amounts_are_the_four_subsidy_limits_and_no_brand_is_named`：拉丁字母只允許 RIC 和食藥署網址；RIC 是外型縮寫，不是品牌 |
| 實際畫面 | ⏳ 本人驗收 | 打開 `/guide/types-and-prices`，看三處新用字與全形標點 |

## 測試

- 單元測試 `manage.py test --settings=config.test_settings --parallel auto`：1489 項全過。
- Ruff：全過。
- 端對端：沒有跑。`e2e/` 裡沒有這一章的任何文字（`git grep` 查過舊字和新字）。
