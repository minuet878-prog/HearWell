"""診間小卡 (spec #677, the #678 mockup's C): what each card says and which 小卡網址 its QR code
holds. The words are the owner's (#679)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Card:
    choice: str  # its button on the print page
    address: str  # the URL name of its 小卡網址 (ADR 0066)
    title: tuple[str, ...]  # its lines
    sees: tuple[str, ...]  # what scanning it shows, its lines
    free: str  # the boxed words: no account, no cost
    camera: str  # the line under its QR code


# The owner's words, as written on #679 (2026-11-17); change them only with the owner.
CARDS = {
    "elder": Card(
        choice="長輩卡",
        address="clinic_card_elder",
        title=("花 3 分鐘，看看", "聽力對生活的影響"),
        sees=("回答 10 題，", "馬上看到結果和建議"),
        free="不用註冊・免費",
        camera="用手機相機掃",
    ),
    "family": Card(
        choice="家屬卡",
        address="clinic_card_family",
        title=("陪家人一起", "面對聽力問題"),
        sees=("怎麼跟他說話、陪他看診、", "助聽器怎麼照顧"),
        free="不用註冊・免費",
        camera="用手機相機掃",
    ),
}
