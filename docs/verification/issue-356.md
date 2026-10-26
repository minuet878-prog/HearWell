# HHIE-S 與 HHIA-S 分級名稱寫法統一（#356）

日期：2026-10-26。基準：`bf4381b`（origin/main）；分支：`fix/356-grade-labels`。規格：[#356](https://github.com/minuet878-prog/HearWell/issues/356)。

狀態：2026-10-26 本人回覆「人工驗收三項都通過」。自動測試全過。只改分級名稱的文字；門檻數字、分級代碼、分級顏色都沒動，沒有 migration，沒有操作真實資料。依 AGENTS.md 屬「碰到分級」，需要交叉審查；**2026-10-26 本人決定跳過**。

## 查證

- 林克寰《助聽器選配與驗證》HHIA-S 中譯（書頁 165）與 HHIE-S 中譯（書頁 166）都只有題目和總分，沒有分級名稱。兩組名稱都是專案自己寫的：HHIE-S 從 Phase 3 起，HHIA-S 在 #78。
- 改前的差異（issue 表格寫 HHIA-S 有空格是誤記，實際是全形斜線、沒有空格）：

| | 第一級 | 第二級 | 第三級 |
|---|---|---|---|
| HHIE-S（改前） | 無/極輕微影響（半形斜線） | 輕度到中度影響 | 顯著影響 |
| HHIA-S（改前） | 無／極輕微影響（全形斜線） | 輕至中度影響 | 顯著影響 |
| 兩份（改後） | 無／極輕微影響 | 輕度到中度影響 | 顯著影響 |

## 本人決定

- 2026-10-26：統一成 HHIE-S 的用語（用最久，ADR 0007 和歷份規格都這樣寫），斜線用全形（合中文排版，HHIA-S 原本就是）。

## 為什麼不需要規則版本號

`CODING_STANDARDS.md` 與 AGENTS.md 要求「改門檻前先做規則版本號」，是怕改了數字之後，歷史結果被回溯改成另一個分級。這次門檻數字和分級代碼都沒變，每一筆舊結果的分級不會變；分級名稱只存在問卷定義裡、每次顯示時才套上（`screening/scoring.py` 的 `classify`），資料庫、fixture、匯出檔都沒有存這段文字。所以舊結果會改用新名稱顯示，這正是要的：「我的紀錄」相鄰兩個分頁寫法一致。

## 驗收對照

| 驗收 | 驗證 | 證據 |
|---|---|---|
| 兩份量表三個分級的名稱完全相同 | ✅ 自動（新增） | `screening/tests/test_scoring.py` 的 `test_hhie_s_and_hhia_s_name_their_levels_the_same`：兩份各在 0、10、26 分對照同一組名稱 |
| 門檻邊界不變 | ✅ 自動（既有） | `test_scoring.py` 的 `test_hhie_s_boundaries`；`test_hhia_s.py`、`test_history.py` 的 max 斷言 |
| 結果頁、我的紀錄、報告、匯出顯示新名稱 | ✅ 自動（既有斷言改成新字） | `test_hhia_s.py`（結果、紀錄、匯出）、`test_scoring.py`、`test_history.py`、`test_report.py`、`test_pages.py`、`e2e/main_flow.py` 新使用者流程與白卡規則 |

先寫新測試看它失敗（`'無/極輕微影響' != '無／極輕微影響'`、`'輕至中度影響' != '輕度到中度影響'`），再改定義。

## 測試與審查

- 單元測試 `manage.py test --settings=config.test_settings --parallel 4`：1449 項全過。
- 前端 `npm test --prefix frontend`：363 項全過；建置成功。
- 端對端 `e2e.main_flow --parallel 4`：276 項全過。
- `ruff check .`、`ruff format --check`：通過。
- 自審（Standards／Spec 兩軸，基準 `origin/main`）：沒有要修。採納：前端測試資料的舊字一併換成新字，免得以後搜尋誤會舊字還在用；在這份紀錄寫明為什麼不需要規則版本號。不採納：在新測試再驗門檻邊界（既有測試已涵蓋）。

## 人工驗收

1. 我的紀錄：HHIE-S、HHIA-S 兩個分頁的分級名稱寫法一樣（全形斜線、「輕度到中度」）。
2. 做一份 HHIA-S 得 10–24 分：結果頁寫「輕度到中度影響」。
3. 聽力報告與家人版報告：兩份量表的分級名稱一致。

回覆：2026-10-26 本人確認三項都通過。
