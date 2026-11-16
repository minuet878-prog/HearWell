"""The county assistive device centres of the form 9 chapter, with their phone numbers.

Reviewed data from 輔具資源入口網, checked on the chapter's date. The owner accepted each
row's wording in the #577 mockup: a number is written (area code)number with the digits the
source gives, an extension 轉 and never dialled (spec #576).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Phone:
    number: str  # as shown, (area code)number
    after: str = ""  # its extension or what it is for, plain words after the link
    before: str = ""  # which number this is, plain words before the link

    @property
    def dial(self):
        # From any phone: +886, then the number without its leading 0. No extension: phones
        # and switchboards differ on taking one, and a wrong call is worse than one more press.
        digits = "".join(c for c in self.number if c.isdigit())
        return f"tel:+886{digits[1:]}"


@dataclass(frozen=True)
class Centre:
    name: str
    phones: tuple[Phone, ...]


# (county, its centres), north to south as the source lists them.
CENTRES = (
    (
        "基隆市",
        (Centre("基隆市輔具資源中心", (Phone("(02)2469-6966", after="轉 211"),)),),
    ),
    (
        "臺北市",
        (
            Centre("臺北市西區輔具中心", (Phone("(02)2523-7902"),)),
            Centre("臺北市南區輔具中心", (Phone("(02)2720-7364"),)),
            Centre("臺北市合宜輔具中心", (Phone("(02)7713-7760"),)),
        ),
    ),
    (
        "新北市",
        (
            Centre("新北市輔具資源中心(蘆洲)", (Phone("(02)8286-7045"),)),
            Centre("新北市輔具資源中心(新店)", (Phone("(02)2912-1911"),)),
        ),
    ),
    (
        "桃園市",
        (
            Centre(
                "桃園市北區輔具資源中心",
                (
                    Phone("(03)368-3040"),
                    Phone("(03)373-2028"),
                ),
            ),
            Centre("桃園市南區輔具資源中心", (Phone("(03)4890298", after="轉 2000～2020"),)),  # noqa: RUF001
        ),
    ),
    (
        "新竹市",
        (Centre("新竹市輔具資源中心", (Phone("(03)562-3707", after="轉 131～142"),)),),  # noqa: RUF001
    ),
    (
        "新竹縣",
        (
            Centre("新竹縣北區輔具資源中心", (Phone("(03)552-7316", after="總機 9、轉 10～16"),)),  # noqa: RUF001
            Centre("新竹縣南區輔具資源中心", (Phone("(03)511-1015"),)),
        ),
    ),
    (
        "苗栗縣",
        (
            Centre(
                "北區輔具資源中心",
                (
                    Phone("(037)268-462"),
                    Phone("(037)268-463"),
                ),
            ),
            Centre("南區輔具資源中心", (Phone("(037)752-642"),)),
        ),
    ),
    (
        "臺中市",
        (
            Centre("臺中市北區輔具資源中心", (Phone("(04)2531-4200"),)),
            Centre("臺中市南區輔具資源中心", (Phone("(04)2471-3589"),)),
            Centre("臺中市海線輔具資源中心", (Phone("(04)2662-7152", after="轉 35～39"),)),  # noqa: RUF001
        ),
    ),
    (
        "彰化縣",
        (
            Centre("彰化縣二林輔具資源中心 總站", (Phone("(04)896-2178"),)),
            Centre("彰化縣二林輔具資源中心 彰化據點", (Phone("(04)722-9767"),)),
            Centre("彰化縣田尾輔具資源中心", (Phone("(04)883-6311"),)),
        ),
    ),
    (
        "南投縣",
        (
            Centre(
                "南投縣第一輔具資源中心",
                (
                    Phone("(049)242-0338"),
                    Phone("(049)242-0390"),
                ),
            ),
            Centre("南投縣第二輔具資源中心", (Phone("(049)222-8086"),)),
        ),
    ),
    (
        "雲林縣",
        (
            Centre("雲林縣輔助器具資源中心", (Phone("(05)533-9620"),)),
            Centre("雲林縣輔助器具資源中心虎尾站", (Phone("(05)633-9620"),)),
        ),
    ),
    (
        "嘉義市",
        (
            Centre("嘉義市輔具資源中心 東區服務處", (Phone("(05)225-6686"),)),
            Centre("嘉義市輔具資源中心 西區服務處", (Phone("(05)285-8212"),)),
        ),
    ),
    (
        "嘉義縣",
        (
            Centre("嘉義縣輔具資源中心 山線服務中心", (Phone("(05)279-3350"),)),
            Centre("嘉義縣輔具資源中心 海線服務據點", (Phone("(05)379-1851"),)),
            Centre("嘉義縣民雄輔具資源中心", (Phone("(05)226-8005"),)),
        ),
    ),
    (
        "臺南市",
        (
            Centre("臺南市輔具資源中心 官田中心", (Phone("(06)579-0636"),)),
            Centre("臺南市輔具資源中心 佳里中心", (Phone("(06)726-6700"),)),
            Centre("臺南市輔具資源中心 永華中心", (Phone("(06)209-8938"),)),
        ),
    ),
    (
        "高雄市",
        (
            Centre(
                "高雄市北區輔具資源中心 總站",
                (Phone("(07)6226730", after="轉 145（輔具租借、諮詢）；轉 112、113（輔具申請）"),),
            ),
            Centre("高雄市北區輔具資源中心 鳳山據點", (Phone("(07)710-0366"),)),
            Centre("高雄市北區輔具資源中心 旗山據點", (Phone("(07)662-5695"),)),
            Centre(
                "高雄市南區輔具資源中心 總站",
                (
                    Phone("(07)841-6336"),
                    Phone("(07)815-1500", after="轉 111"),
                ),
            ),
            Centre("高雄市南區輔具資源中心 楠梓據點", (Phone("(07)366-1130"),)),
        ),
    ),
    (
        "屏東縣",
        (
            Centre("屏東縣屏北區輔具資源中心", (Phone("(08)736-5455"),)),
            Centre("屏東縣屏中區輔具資源中心 總站", (Phone("(08)789-9599"),)),
            Centre("屏東縣屏中區輔具資源中心 屏南工作站", (Phone("(08)8883741"),)),
        ),
    ),
    (
        "臺東縣",
        (Centre("臺東縣輔具資源中心", (Phone("(089)232-263"),)),),
    ),
    (
        "花蓮縣",
        (
            Centre(
                "花蓮縣輔具資源中心",
                (
                    Phone("(03)8225365"),
                    Phone("(03)8241657"),
                    Phone("(03)8241658"),
                ),
            ),
            Centre(
                "花蓮縣南區輔具資源中心",
                (
                    Phone("(03)888-6586"),
                    Phone("(03)888-7992"),
                ),
            ),
        ),
    ),
    (
        "宜蘭縣",
        (
            Centre("宜蘭縣溪北輔具資源中心", (Phone("(03)9320920"),)),
            Centre("宜蘭縣溪南輔具資源中心", (Phone("(03)9544106", after="轉 8114"),)),
        ),
    ),
    (
        "澎湖縣",
        (Centre("澎湖縣輔具資源中心", (Phone("(06)926-2740"),)),),
    ),
    (
        "金門縣",
        (
            Centre(
                "金門縣輔具資源中心",
                (
                    Phone("(082)333629", before="服務電話"),
                    Phone("(082)333269", before="意見專線"),
                ),
            ),
        ),
    ),
    (
        "連江縣",
        (
            Centre(
                "連江縣輔具資源中心",
                (
                    Phone("(0836)25022", after="轉 302"),
                    Phone("(0836)23050", before="或"),
                ),
            ),
        ),
    ),
)
