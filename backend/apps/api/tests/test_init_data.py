from django.test import SimpleTestCase

from apps.api.auth import InitDataError, validate_init_data

TOKEN = "test-bot-token"
VECTOR = (
    "auth_date=1700000000"
    "&chat=%7B%22id%22%3A12345%2C%22type%22%3A%22DIALOG%22%7D"
    "&query_id=test-query-id"
    "&user=%7B%22id%22%3A67890%2C%22first_name%22%3A%22Max%22%2C%22last_name%22%3A%22User%22"
    "%2C%22username%22%3Anull%2C%22language_code%22%3A%22ru%22%2C%22photo_url%22%3Anull%7D"
    "&hash=5a984b5493450b0da3314a7ab719c041bdcf10536d039f1f0b45b3543ded664c"
)
NOW = 1700000100


class ValidateInitDataTests(SimpleTestCase):
    def test_reference_vector_is_accepted(self):
        data = validate_init_data(VECTOR, TOKEN, max_age_seconds=3600, now=NOW)
        self.assertEqual(data["user"]["id"], 67890)
        self.assertEqual(data["chat"]["type"], "DIALOG")
        self.assertEqual(data["auth_date"], 1700000000)

    def test_wrong_token_is_rejected(self):
        with self.assertRaises(InitDataError):
            validate_init_data(VECTOR, "other-token", max_age_seconds=3600, now=NOW)

    def test_tampered_payload_is_rejected(self):
        tampered = VECTOR.replace("12345", "99999")
        with self.assertRaises(InitDataError):
            validate_init_data(tampered, TOKEN, max_age_seconds=3600, now=NOW)

    def test_expired_data_is_rejected(self):
        with self.assertRaises(InitDataError):
            validate_init_data(VECTOR, TOKEN, max_age_seconds=3600, now=NOW + 7200)

    def test_missing_hash_is_rejected(self):
        without_hash = VECTOR.rsplit("&hash=", 1)[0]
        with self.assertRaises(InitDataError):
            validate_init_data(without_hash, TOKEN, max_age_seconds=3600, now=NOW)

    def test_duplicated_hash_is_rejected(self):
        with self.assertRaises(InitDataError):
            validate_init_data(VECTOR + "&hash=abc", TOKEN, max_age_seconds=3600, now=NOW)
