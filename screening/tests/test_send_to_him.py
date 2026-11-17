import re
from html import unescape

from django.test import TestCase

from screening.models import User
from screening.tests.helpers import consented_user

# The owner's words (#671, family-pages-skeleton.md): the one message every 傳給他 sends, and the
# lead above it the owner chose for the reluctant page too (2026-11-17, same as page one).
MESSAGE = (
    "分享你一個聽力自我篩檢，回答幾個問題大約 3 分鐘，不用註冊。"
    "做完會看到結果和建議，有空可以做做看。"
)
HEADING = "先在家做個簡單的篩檢"
LEAD = (
    "篩檢是回答幾個生活中聽的問題，大約 3 分鐘、不用註冊。"
    "它不能取代聽力檢查，但可以幫他看看聽力對生活的影響，結果也會建議下一步。"
)
ADDRESS = "http://testserver/questionnaire_list?via=send"


def block(content):
    """The 傳給他 section of a page."""
    match = re.search(r'<section class="send-to-him"[^>]*>(.*?)</section>', content, re.S)
    return match.group(1) if match else None


def text(html):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


class ReluctantPageSendTests(TestCase):
    """Spec #655 acceptance 17–21 (#674): 長輩不肯去怎麼說 has 傳給他 below its situations, the
    owner's words above the message box the #669 mockup's B drew, its own words unchanged."""

    def setUp(self):
        self.content = self.client.get("/family/reluctant").content.decode()
        self.send = block(self.content)

    def test_the_section_has_the_owners_heading_lead_and_message(self):
        self.assertIsNotNone(self.send)
        self.assertRegex(self.send, rf"<h2[^>]*>{HEADING}</h2>")
        words = text(self.send)
        self.assertIn(LEAD, words)
        self.assertIn(f"會傳出這段話 {MESSAGE} {ADDRESS}", words)

    def test_the_address_is_the_wizards_age_step_with_the_mark_only(self):
        # Acceptance 21: nothing about the family member or the elder, and not the cards' mark.
        addresses = set(re.findall(r"https?://[^\s<\"]+", self.send))
        self.assertEqual(addresses, {ADDRESS})
        self.assertNotIn("from=card", self.send)

    def test_the_address_takes_the_scheme_the_page_was_opened_with(self):
        secure = self.client.get("/family/reluctant", secure=True).content.decode()
        self.assertIn("https://testserver/questionnaire_list?via=send", block(secure))

    def test_the_share_button_sends_the_message_and_the_address_as_one_text(self):
        # Acceptance 18: hidden until share-button.js finds the phone's share sheet.
        button = re.search(r'<button id="share-button"([^>]*)>(.*?)</button>', self.send, re.S)
        self.assertIsNotNone(button)
        attributes, label = button.groups()
        self.assertIn(" hidden", attributes)
        self.assertIn("btn-primary", attributes)
        self.assertEqual(text(label), "傳給他做篩檢")
        self.assertIn(f'data-text="{MESSAGE}\n{ADDRESS}"', unescape(attributes))
        self.assertIn("screening/share-button.js", self.content)

    def test_without_a_share_sheet_the_button_copies_the_same_text(self):
        # Acceptance 19: copy-link.js shows it only where the share sheet is not.
        button = re.search(r'<button id="copy-link"([^>]*)>(.*?)</button>', self.send, re.S)
        self.assertIsNotNone(button)
        attributes, label = button.groups()
        self.assertIn(" hidden", attributes)
        self.assertIn("data-without-share-sheet", attributes)
        self.assertEqual(text(label), "複製訊息")
        self.assertIn(f'data-text="{MESSAGE}\n{ADDRESS}"', unescape(attributes))
        self.assertIn('id="copy-status"', self.send)

    def test_it_comes_after_the_situations_and_before_the_closing_words(self):
        situations = self.content.index("pick-explain")
        closing = self.content.index("這些是一般性的建議，不能取代醫師或聽力師的診斷")
        section = self.content.index('<section class="send-to-him"')
        self.assertLess(situations, section)
        self.assertLess(section, closing)


class SignedInOpensTheSentAddressTests(TestCase):
    """Acceptance 22's second half: someone signed in who opens the sent address reaches the
    questionnaires too. One who has not agreed to the privacy notice yet is asked first, as on
    every such page, and comes back to the address with its mark."""

    def test_a_signed_in_user_who_agreed_reaches_the_questionnaires(self):
        self.client.force_login(consented_user(username="sent_agreed"))
        response = self.client.get("/questionnaire_list?via=send")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "screening/frontend/arrival-count.js")
        # What the screening tab shows them: without a record, the wizard that picks one.
        self.assertContains(response, "幫您找適合的問卷")
        self.assertContains(response, "您最想了解什麼？")

    def test_one_who_has_not_agreed_yet_is_asked_first_and_comes_back(self):
        self.client.force_login(User.objects.create_user(username="sent_not_yet"))
        response = self.client.get("/questionnaire_list?via=send")
        self.assertRedirects(
            response,
            "/consent?next=/questionnaire_list%3Fvia%3Dsend",
            fetch_redirect_response=False,
        )


class WhereSendToHimIsNotTests(TestCase):
    """Acceptance 17 and 9: the family zone home keeps its own 傳給家人, and the simulator, which
    elders use themselves, has no 傳給他."""

    def test_the_family_zone_home_and_the_simulator_have_none(self):
        for address in ("/family", "/learn/simulator"):
            with self.subTest(address=address):
                content = self.client.get(address).content.decode()
                self.assertIsNone(block(content))
                self.assertNotIn("傳給他做篩檢", content)
                self.assertNotIn("via=send", content)
