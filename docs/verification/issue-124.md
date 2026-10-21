# #124 Tailwind 建置、主題與共用版型驗證

日期：2026-10-21；分支 `feat/124-tailwind-foundation`；母分支 `feat/tailwind-migration`。
狀態：自動驗證完成；本人實際驗收待完成。沒有 push、開 PR 或合併。

## 範圍與參考

- [#124](https://github.com/minuet878-prog/HearWell/issues/124)、ADR 0008。
- 只保證共用頁首、導覽、頁尾與 skip link；其餘元件與頁面由 #125–#130 接續。
- 舊 `styles.css` 依規格保留到 #126；無 Bootstrap CDN、JS 或套件引用。
- 依 Tailwind v4.3 官方文件核對 [theme](https://tailwindcss.com/docs/theme) 與 [source](https://tailwindcss.com/docs/detecting-classes-in-source-files)；Context7 本次沒有找到官方資料，改查官方文件及已安裝 4.3.3 外掛型別。

## 自動驗證

| 檢查 | 結果 |
|---|---|
| Django 全套 `py313/bin/python manage.py test --settings=config.test_settings --noinput` | 644 個通過 |
| 前端 `npm test --prefix frontend` | 12 檔、187 個通過 |
| `npm run build --prefix frontend` | 產生 `site.css`，無 `site.js` |
| Ruff、`git diff --check` | 通過 |
| 主題數值、skip link 焦點、手機放大字級返回鍵、手機登出排列、桌機長帳號頁首 | 5 個瀏覽器測試通過 |
| CSS brotli | `site.css` 3,395 ＋ `styles.css` 5,489 ＝ **8,884 bytes**，上限 28,459 bytes |

字級檢查新增掃描 `frontend/src/*.css`。Django 頁面測試涵蓋公用、帳號、同意、問卷、結果、紀錄、聽力圖、報告與分享頁（含失效連結），檢查載入 `site.css` 且沒有 Bootstrap 引用。

主題測試：`e2e.main_flow.StyleInBrowserTest.test_tailwind_theme_preserves_original_design_values`（`e2e/main_flow.py:997`）。以遷移前 CSS 的獨立數值驗證 32 個主題值，並量實際根字級 18px、內容上限 720px。壓縮器會把 rgba 的 0.5 改成 128/255，因此關閉 Tailwind optimize 與 Vite CSS minify；brotli 傳輸壓縮仍保留，大小測試仍計入新舊 CSS。

## 畫面證據與限制

- 原始基準：`e2e-artifacts/shots/main`（272 張，未覆寫）。
- 第一輪：`e2e-artifacts/shots/124`；用 `e2e/compare_shots.py --group chrome` 比對：161 張相同、111 張不同，字型／根字級沒有不同。頁首全部相同。
- 原始工具裁切頁尾時會保留其整頁小數座標，內容高度改變會影響像素與裁切高度；固定手機導覽也可能混入背後內容。此票允許內容區待後續票恢復，因此另做共用區域隔離對照，不放寬像素或顏色容差。
- 隔離方式：維持區域原寬度與所有樣式，把相同區域移到 (0, 0)，暫時隱藏其他元素，停用測試中 Tab／Enter 觸發的平滑捲動；截圖後還原。另在每個頁面按 Tab 驗證第一站是 skip link，拍聚焦圖，再按 Enter 驗證 main 得到焦點。
- 參考版使用母分支 `c229719` 的 layout，與目前 `origin/main` 的 layout/styles.css 完全相同；其餘模板及原始 styles.css 沒有改動。Bootstrap 5.3.8 官方 CSS 只存 `/tmp` 並由測試攔截回傳。
- 原始截圖埠 8765 被占用，所以只為臨時測試改埠，未停止使用者服務。

最終隔離對照：`main-isolated-v2` → `124-isolated-v2`，**362／362 張完全相同、零像素差異、零字型／根字級差異**。包含 272 張共用區域與 90 張聚焦 skip link。

報告：`e2e-artifacts/shots/124-isolated-v2-diff/report.md`；兩次截圖測試皆通過，每頁 Tab 第一站／Enter 後焦點斷言皆通過。第一次隔離對照仍有 63 張差異，原因是附加的 Enter 焦點測試觸發平滑捲動；v2 在兩邊都暫停平滑捲動並回到頂端後裁切，才排除這項測試干擾。所有原圖與中間結果均保留。

注意：原始 272 張裁切比對沒有變成全通過；本票的畫面一致證據來自上述隔離區域對照。整頁版面一致仍由 #131 驗收。

## 自審

依 code-review 技能，以 main 為基準，Standards 與 Spec 分別審查。發現完整 CSS 體積、主題數值與 skip link 外觀證據三項缺口並補齊；Standards 複核 0 項要修，Spec 複核含最終零差異報告也確認原三項均修復，0 項待修。

不需交叉審查：沒有修改計分、分級、門檻、資料 migration 或權限。

### 驗收證據對照

| 條件 | 自動斷言／產物 |
|---|---|
| CSS 建置與載入 | `frontend/src/bundle.test.js:55`；`screening/tests/test_pages.py:877`、`:915`、`:920` |
| 共用區域畫面 | 原始與隔離 `compare_shots.py` 報告（如下）；保持零像素容差 |
| Tab／Enter 與聚焦外觀 | 既有 `e2e/main_flow.py` skip link測試；附錄腳本每個頁面 `to_be_focused`／`to_be_visible`，加 90 張聚焦圖 |
| CSS 上限 | `frontend/src/bundle.test.js:59` 新舊 CSS 合計 |
| 數值不改 | `e2e/main_flow.py:997` 的32項 token對照與根字級／寬度斷言 |

聚焦截圖比較元素邊界內的文字、padding、border、背景；元素外側的瀏覽器焦點框不在裁切範圍，該外框規則未修改，本次不宣稱另外量到它。

## 驗收條件

- [x] 建置產生網站 CSS，版型載入且沒有 Bootstrap 引用。
- [x] 共用區域與原始畫面一致：隔離對照 272 張零差異；原始工具有上述裁切差異。
- [x] 任一頁 Tab 第一站是 skip link 且元素內聚焦外觀一致：每頁焦點斷言通過，90 張聚焦圖零差異。
- [x] CSS brotli 不超過 28,459 bytes。
- [x] 設計主題數值維持原值。
- [ ] 本人實際操作驗收。

## 重現隔離對照

以下腳本只做驗證，不在網站執行。先把本節附錄存成 `/tmp/hearwell-124-capture.py`，再執行：

```sh
mkdir -p /tmp/hearwell-124-reference/screening
git show c229719:screening/templates/screening/layout.html > /tmp/hearwell-124-reference/screening/layout.html
curl -fsSL https://raw.githubusercontent.com/twbs/bootstrap/v5.3.8/dist/css/bootstrap.min.css -o /tmp/hearwell-bootstrap.css
SHOTS_DIR=e2e-artifacts/shots/main-isolated-v2 SHOTS_GROUPS=chrome REFERENCE=1 DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. py313/bin/python /tmp/hearwell-124-capture.py
SHOTS_DIR=e2e-artifacts/shots/124-isolated-v2 SHOTS_GROUPS=chrome CAPTURE_PORT=8773 DJANGO_SETTINGS_MODULE=config.test_settings PYTHONPATH=. py313/bin/python /tmp/hearwell-124-capture.py
py313/bin/python e2e/compare_shots.py e2e-artifacts/shots/main-isolated-v2 e2e-artifacts/shots/124-isolated-v2 --group chrome
```

請用新的輸出目錄重跑，避免覆寫驗證圖片。兩次測試需依序執行，使用的都是 Django 隔離測試資料庫。

### 驗證腳本

```python
"""Isolate shared regions at integer coordinates, preserving the original captures."""
import inspect
import os
import re
import textwrap
from pathlib import Path
import django
from django.conf import settings
from django.core.management import call_command
if os.environ.get('REFERENCE'):
    settings.TEMPLATES[0]['DIRS'] = ['/tmp/hearwell-124-reference']
django.setup()
from e2e import screenshots as shots
from playwright.sync_api import expect

# Use the same pinned official CSS as the original main capture, served locally.
source = textwrap.dedent(inspect.getsource(shots.Screenshots.open))
source = source.replace('page = context.new_page()', """context.route(re.compile(r"https://cdnjs.cloudflare.com/ajax/libs/bootstrap/.*"),
        lambda route: route.fulfill(path="/tmp/hearwell-bootstrap.css", content_type="text/css"))
    page = context.new_page()""")
exec(source, shots.__dict__)
shots.Screenshots.open = shots.open
shots.Screenshots.port = int(os.environ.get("CAPTURE_PORT", "8770"))
if os.environ.get('DEBUG_SHOT'):
    original_shots = shots.Screenshots.shots
    shots.Screenshots.shots = lambda self: [s for s in original_shots(self) if s.name == 'answer-hhie-s' and not s.javascript]

def isolated(self, page, path, locator=None):
    page.evaluate("document.documentElement.style.scrollBehavior = 'auto'")
    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    if locator is None:
        raise AssertionError('only chrome captures are supported')
    # Body migration changes footer Y and the content behind the fixed navigation. Give
    # each region the same pixel origin and opaque surroundings to compare its own styles.
    saved = locator.get_attribute('style')
    width = locator.bounding_box()['width']
    locator.evaluate('''(el, width) => {
      el.setAttribute('data-isolated', '');
      Object.assign(el.style, {position:'fixed', top:'0px', left:'0px', right:'auto',
        bottom:'auto', margin:'0', width:width+'px', zIndex:'99999'});
    }''', width)
    sheet = page.evaluate_handle("css => { const s = document.createElement('style'); s.textContent = css; document.head.append(s); return s; }", 'body * { visibility: hidden !important; } [data-isolated], [data-isolated] * { visibility: visible !important; }')
    locator.screenshot(path=self.out / path, animations='disabled', caret='hide')
    sheet.evaluate('(el) => el.remove()')
    locator.evaluate("el => el.removeAttribute('data-isolated')")
    if saved is None:
        locator.evaluate("el => el.removeAttribute('style')")
    else:
        locator.evaluate('(el, value) => el.setAttribute("style", value)', saved)
    if path.startswith('chrome--header--') and '-app--' not in path:
        page.keyboard.press('Tab')
        skip = page.get_by_role('link', name='跳到主要內容', exact=True)
        expect(skip).to_be_focused()
        expect(skip).to_be_visible()
        # Preserve its original fixed offsets, padding, border and focus outline.
        saved_skip = skip.get_attribute('style')
        skip.evaluate("el => el.style.position = 'fixed'")
        skip.screenshot(path=self.out / path.replace('--header--','--skip--'), animations='disabled')
        if saved_skip is None:
            skip.evaluate("el => el.removeAttribute('style')")
        else:
            skip.evaluate('(el, value) => el.setAttribute("style", value)', saved_skip)
        page.keyboard.press('Enter')
        expect(page.get_by_role('main')).to_be_focused()
shots.Screenshots.capture = isolated
call_command('test', 'e2e.screenshots', interactive=False)
```
