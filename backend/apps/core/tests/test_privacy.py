from django.test import SimpleTestCase, TestCase

from apps.bot import texts


class PrivacyPageTests(TestCase):
    def test_policy_is_public_and_names_the_contact(self):
        response = self.client.get("/privacy/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        page = response.content.decode()
        self.assertIn("Политика обработки персональных данных", page)
        self.assertIn("anatoliykonovalov2008@gmail.com", page)
        self.assertIn("Российской Федерации", page)

    def test_address_without_slash_leads_to_the_policy(self):
        response = self.client.get("/privacy")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/privacy/")


class PrivacyLinkInBotTests(SimpleTestCase):
    def test_link_is_added_when_the_public_address_is_known(self):
        text = texts.with_privacy("Кто вы?", "Продолжая, вы соглашаетесь", url="https://example.ru/privacy/")
        self.assertEqual(text, "Кто вы?\n\nПродолжая, вы соглашаетесь: https://example.ru/privacy/")

    def test_no_link_without_a_public_address(self):
        self.assertEqual(texts.with_privacy("Кто вы?", "Продолжая", url=""), "Кто вы?")
