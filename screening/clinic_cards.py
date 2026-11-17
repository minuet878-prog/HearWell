"""診間小卡 (spec #677, the #678 mockup's C): what each card says and which 小卡網址 its QR code
holds. The words are the owner's (#679); an empty one leaves its place on the card blank."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Card:
    choice: str  # its button on the print page
    address: str  # the URL name of its 小卡網址 (ADR 0066)
    title: tuple[str, ...]  # its lines
    sees: tuple[str, ...]  # what scanning it shows, its lines
    free: str  # the boxed words: no account, no cost
    camera: str  # the line under its QR code


CARDS = {
    "elder": Card(
        choice="長輩卡", address="clinic_card_elder", title=(), sees=(), free="", camera=""
    ),
    "family": Card(
        choice="家屬卡", address="clinic_card_family", title=(), sees=(), free="", camera=""
    ),
}
