# ruff: noqa
# PROTOTYPE for #373 — throwaway. Generates a static (no-JS) comparison page.
from pathlib import Path

OUT = Path(__file__).with_name("prototype-ask-entry-answer.html")

CSS = """
:root{--p:#1f4e8c;--ph:#173b6a;--body:#495057;--head:#212529;--surface:#f1f3f5;--soft:#eef3fa;
--border:#ced4da;--sev:#8f2a12;--sevbg:#feece7;--mild:#704800;--mildbg:#fff4d6}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--body);font-family:-apple-system,"PingFang TC","Noto Sans TC",sans-serif;font-size:18px;line-height:1.6}
.doc{max-width:1100px;margin:0 auto;padding:16px}
.doc h1{color:var(--head);font-size:1.6em;margin:.4em 0}
.doc h2{color:var(--head);font-size:1.35em;margin:1.6em 0 .3em;border-top:3px solid var(--p);padding-top:.6em}
.doc h3{color:var(--p);font-size:1.15em;margin:1.2em 0 .2em}
.note{background:var(--mildbg);color:var(--mild);border-radius:8px;padding:.6em .9em}
.pair{display:flex;flex-wrap:wrap;gap:20px;align-items:flex-start}
.cap{font-size:.85em;color:var(--head);margin:.3em 0;font-weight:600}
.cost{margin:.4em 0 1em;padding-left:1.2em}
.rec{background:var(--soft);border-left:5px solid var(--p);padding:.6em .9em;border-radius:6px}
/* phone frame: 320 CSS px wide, one screen tall; everything inside sizes in em */
.phone{width:320px;height:640px;border:2px solid #343a40;border-radius:14px;overflow:hidden;position:relative;background:#fff;font-size:18px;line-height:1.5}
.phone.z2{font-size:36px}
.ph-head{background:var(--p);color:#fff;padding:.35em .6em;font-weight:700;font-size:.9em}
.ph-main{padding:.5em .6em 5em}
.ph-main h1{color:var(--head);font-size:1.3em;margin:.2em 0 .3em;line-height:1.3}
.ph-main h2{color:var(--head);font-size:1em;margin:.8em 0 .3em}
.ph-main p{margin:.3em 0}
.lead{font-size:.95em}
.card{display:flex;align-items:center;gap:.4em;border:1px solid var(--border);border-radius:.5em;padding:.5em .6em;margin:.35em 0;color:var(--p);text-decoration:none;font-weight:600;background:#fff}
.card span{flex:1}
.card b{font-size:1.3em;line-height:1}
.qlink{display:block;color:var(--p);padding:.35em 0;border-bottom:1px solid var(--border);text-decoration:underline;font-weight:600}
.urgent{display:block;background:var(--sevbg);color:var(--sev);border:2px solid var(--sev);border-radius:.5em;padding:.45em .6em;font-weight:700;margin:.3em 0 .5em;text-decoration:none}
.field{display:block;border:2px solid #6c757d;border-radius:.4em;padding:.4em .5em;margin:.2em 0;color:var(--head);background:#fff;min-height:2.4em}
.btn{display:block;text-align:center;background:var(--p);color:#fff;border-radius:.4em;padding:.45em;font-weight:700;margin:.3em 0}
.hint{font-size:.85em;color:#6c757d}
.ans{background:var(--surface);border-radius:.5em;padding:.5em .6em;margin:.3em 0}
.src{font-size:.85em;border-top:1px solid var(--border);margin-top:.4em;padding-top:.3em}
.back{color:var(--p);text-decoration:underline;font-size:.9em}
.open{border:2px solid var(--p);border-radius:.5em;padding:.4em .5em;margin:.35em 0}
.open .qq{color:var(--head);font-weight:700}
.closed{border:1px solid var(--border);border-radius:.5em;padding:.4em .5em;margin:.35em 0;color:var(--p);font-weight:600}
.ph-nav{position:absolute;left:0;right:0;bottom:0;display:flex;border-top:1px solid var(--border);background:#fff}
.ph-nav span{flex:1;text-align:center;font-size:.6em;padding:.5em 0 .6em;color:var(--body);overflow:hidden;white-space:nowrap}
.ph-nav span::before{content:"";display:block;width:1.6em;height:1.6em;margin:0 auto .15em;border:2px solid currentColor;border-radius:.4em}
.ph-nav span.on{color:var(--p);font-weight:700;background:var(--soft)}
.fab{position:absolute;right:.4em;bottom:3.6em;background:var(--p);color:#fff;border-radius:2em;padding:.5em .8em;font-weight:700;box-shadow:0 .2em .5em rgba(0,0,0,.35)}
"""

URGENT = '<a class="urgent">突然聽不到、耳朵流血？請盡快就醫 ›</a>'
TOPICS = ["網站怎麼用", "問卷是什麼", "助聽器選配與補助", "聽力保健常識"]


def nav(on, tabs=("首頁", "問卷", "我的聽力", "了解")):
    return (
        '<div class="ph-nav">'
        + "".join(f'<span class="{"on" if t == on else ""}">{t}</span>' for t in tabs)
        + "</div>"
    )


def cards(items):
    return "".join(f'<a class="card"><span>{t}</span><b>›</b></a>' for t in items)


def phone(main, navbar, extra=""):
    return lambda z: (
        f'<div class="phone{" z2" if z else ""}"><div class="ph-head">HearWell</div>'
        f'<div class="ph-main">{main}</div>{extra}{navbar}</div>'
    )


# ---------- Q1: how people ask ----------
ASK_A = phone(
    "<h1>問答小助手</h1>"
    + URGENT
    + '<p class="lead">點一個主題，再點您想問的問題。</p>'
    + cards(TOPICS),
    nav("了解"),
)

ASK_B = phone(
    "<h1>問答小助手</h1>"
    + URGENT
    + '<p class="lead">請輸入您想問的事：</p><span class="field">助聽器補助</span>'
    '<span class="btn">找答案</span>'
    "<h2>找到 3 題可能相關</h2>"
    '<a class="qlink">助聽器補助要怎麼申請？</a><a class="qlink">補助金額大概多少？</a>'
    '<a class="qlink">集音器和助聽器有什麼不同？</a>',
    nav("了解"),
)

ASK_C = phone(
    "<h1>問答小助手</h1>" + URGENT + "<h2>大家常問</h2>"
    '<a class="qlink">助聽器補助要怎麼申請？</a><a class="qlink">問卷做完分數代表什麼？</a>'
    '<a class="qlink">集音器和助聽器有什麼不同？</a>'
    "<h2>依主題找</h2>" + cards(TOPICS) + "<h2>找不到？打字問</h2>"
    '<span class="field"></span><span class="btn">找答案</span>',
    nav("了解"),
)

# ---------- Q2: where the entry lives ----------
ENTRY_1 = phone(
    "<h1>了解</h1><h2>助聽器</h2>"
    + cards(["了解助聽器選配與補助"])
    + "<h2>溝通與照顧</h2>"
    + cards(["給家人看：怎麼跟聽損的家人溝通"])
    + "<h2>有問題想問</h2>"
    + cards(["問答小助手：常見問題一次查"]),
    nav("了解"),
)

HOME = (
    "<h1>早安，王小明</h1><p>上次做問卷是 3 個月前。</p>"
    + cards(["做聽力問卷", "看我的紀錄", "記錄聽力圖"])
    + "<h2>您還可以</h2>"
    + cards(["給家人看：怎麼跟聽損的家人溝通"])
)

ENTRY_2 = phone(HOME, nav("首頁", ("首頁", "問卷", "我的聽力", "問答", "了解")))

ENTRY_3 = phone(HOME, nav("首頁"), extra='<span class="fab">？問問題</span>')

# ---------- Q3: how answers show ----------
ANS_X = phone(
    '<a class="back">‹ 問答小助手</a><h1>助聽器選配與補助</h1>'
    '<div class="open"><div class="qq">▾ 助聽器補助要怎麼申請？</div>'
    '<div class="ans">一般來說，……（示意文字，正式內容由本人撰寫審定）'
    '<div class="src">來源：衛生福利部（示意）<br>查核日期：2026-10-26</div></div></div>'
    '<div class="closed">▸ 補助金額大概多少？</div>'
    '<div class="closed">▸ 集音器和助聽器有什麼不同？</div>'
    '<div class="closed">▸ 要去哪裡做鑑定？</div>',
    nav("了解"),
)

ANS_Y = phone(
    '<a class="back">‹ 回「助聽器選配與補助」</a>'
    "<h1>助聽器補助要怎麼申請？</h1>"
    '<div class="ans">一般來說，……（示意文字，正式內容由本人撰寫審定）'
    '<div class="src">來源：衛生福利部（示意）<br>查核日期：2026-10-26</div></div>'
    '<p class="hint">以上是一般說明，您的情況請以醫師、聽力師為準。</p>'
    "<h2>相關問題</h2>"
    '<a class="qlink">補助金額大概多少？</a><a class="qlink">要去哪裡做鑑定？</a>'
    "<h2>沒回答到您的問題？</h2>"
    '<a class="qlink">回問答小助手首頁</a>',
    nav("了解"),
)

ANS_REF = phone(
    '<a class="back">‹ 回「問卷是什麼」</a>'
    "<h1>我的分數代表什麼？</h1>"
    '<div class="ans">小助手不解讀個人的結果。每次問卷的結果頁都有分級和建議，'
    "也可以把結果頁帶給聽力師看。</div>" + cards(["到「我的紀錄」看結果"]),
    nav("了解"),
)


def block(title, make, cost, note=""):
    return (
        f"<h3>{title}</h3>{note}"
        f'<div class="pair"><div><p class="cap">一般字級</p>{make(False)}</div>'
        f'<div><p class="cap">200% 字級</p>{make(True)}</div></div>'
        f'<ul class="cost">{"".join(f"<li>{c}</li>" for c in cost)}</ul>'
    )


body = f"""
<div class="doc">
<p class="note">原型（#373），用完即丟。每格是 320px 寬手機的<strong>第一個畫面</strong>，
超出畫面的部分被裁掉，代表要往下捲才看得到。答案文字是示意，不是正式內容。</p>
<h1>問答小助手：怎麼問、放哪裡、怎麼回答</h1>

<h2>問題一：長輩怎麼提問</h2>
{
    block(
        "A 只點選（主題 → 題目）",
        ASK_A,
        [
            "優點：不用打字；不會有「打了卻找不到」的挫折；不需要比對程式。",
            "代價：題目多了要點兩三層；問題不在清單上就沒辦法問。",
        ],
    )
}
{
    block(
        "B 只打字（輸入 → 可能相關的題目）",
        ASK_B,
        [
            "優點：畫面最簡單；題目再多也不用分層。",
            "代價：65 歲以上打中文最難（注音、手寫都慢）；比對準不準要先收 30–50 句真實問法當測試集（#374）。",
        ],
    )
}
{
    block(
        "C 兩者都有（常問題目 → 主題 → 最後才打字）",
        ASK_C,
        [
            "優點：點選為主、打字為輔；家人可以幫忙打字；打字的提問以後可以拿來補題（看 #376 怎麼決定）。",
            "代價：最長的一頁，200% 字級時打字框在很下面；要同時做清單和比對兩套。",
        ],
    )
}
<p class="rec"><strong>我的建議：C。</strong>長輩主要用點的，打字留給家人和找不到的時候；
如果第一版想更小，先做 A，打字等收到測試集再加。</p>

<h2>問題二：入口放哪裡</h2>
{
    block(
        "1 「了解」頁加一張卡",
        ENTRY_1,
        [
            "優點：跟 ADR 0019「衛教與資源都放『了解』」一致；不動導覽列、不擋內容；改動最小。",
            "代價：要先想到點「了解」才找得到；卡片在第三組，可能要往下捲。",
        ],
    )
}
{
    block(
        "2 底部導覽加第五個分頁「問答」",
        ENTRY_2,
        [
            "優點：任何頁面一眼看到、一點就到。",
            "代價：五個分頁在 320px、200% 字級時字被擠掉（看右格）；導覽列改動會影響所有頁和 e2e。",
        ],
    )
}
{
    block(
        "3 每頁右下角浮動按鈕",
        ENTRY_3,
        [
            "優點：在哪一頁有疑問都能馬上問。",
            "代價：會蓋住內容和按鈕，200% 字級時蓋得更多；浮動元素對螢幕閱讀器和放大鏡使用者不友善。",
        ],
    )
}
<p class="rec"><strong>我的建議：1。</strong>代價最小、不擋任何東西；若擔心找不到，
可以另外在首頁「您還可以」放一個連結（同樣是一張卡，不是新做法）。</p>

<h2>問題三：答案怎麼呈現</h2>
{
    block(
        "X 同一頁展開（點題目，答案在下面打開）",
        ANS_X,
        [
            "優點：少點一次；同主題的題目一路看下去。",
            "代價：200% 字級時一個答案就占滿畫面，其他題目被推到很下面；答案沒有自己的網址，不能傳給家人；按上一頁會離開整個主題。",
        ],
    )
}
{
    block(
        "Y 每題一頁（題目、答案、來源、相關問題）",
        ANS_Y,
        [
            "優點：每題有自己的網址，可以傳給家人；上一頁行為符合預期；來源、查核日期、「以醫師為準」、相關問題都有位置。",
            "代價：多點一次、多一次換頁；題目多時頁面也多（但都是同一個樣板）。",
        ],
    )
}
<p class="rec"><strong>我的建議：Y。</strong>長輩常用「上一頁」，每題一頁比較不會迷路；能把網址傳給家人也符合「給家人看」的用法。</p>

<h3>附：轉介答案長這樣（X 或 Y 都適用，不用選）</h3>
<div class="pair"><div><p class="cap">一般字級</p>{ANS_REF(False)}</div>
<div><p class="cap">200% 字級</p>{ANS_REF(True)}</div></div>
<p>急症那一題不放在任何主題裡，而是置頂在小助手首頁（每個 A／B／C 格最上面的紅框）。</p>
</div>
"""

OUT.write_text(
    f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
    f'<meta name="viewport" content="width=device-width,initial-scale=1">'
    f"<title>問答小助手原型</title><style>{CSS}</style></head><body>{body}</body></html>",
    encoding="utf-8",
)
print(OUT)
