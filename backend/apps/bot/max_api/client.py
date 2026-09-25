import ssl

import httpx
from django.conf import settings


class MaxApiError(Exception):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"MAX API returned {status_code}: {body[:300]}")
        self.status_code = status_code
        self.body = body


def build_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(settings.MAX_CA_BUNDLE))
    return context


def message_id_of(response: dict) -> str | None:
    return ((response or {}).get("message") or {}).get("body", {}).get("mid")


class MaxClient:
    def __init__(self, token: str | None = None):
        self._context = build_ssl_context()
        self._http = httpx.Client(
            base_url=settings.MAX_API_BASE,
            headers={"Authorization": token or settings.BOT_TOKEN},
            verify=self._context,
            timeout=httpx.Timeout(15.0, read=45.0),
        )

    def _request(self, method: str, path: str, *, params=None, json=None) -> dict:
        response = self._http.request(method, path, params=params, json=json)
        if response.status_code >= 400:
            raise MaxApiError(response.status_code, response.text)
        return response.json() if response.content else {}

    def get_me(self) -> dict:
        return self._request("GET", "/me")

    def get_updates(self, marker: int | None = None, timeout: int = 30, limit: int = 100) -> dict:
        params = {"timeout": timeout, "limit": limit}
        if marker is not None:
            params["marker"] = marker
        return self._request("GET", "/updates", params=params)

    def send_message(
        self,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        text: str,
        buttons: list[list[dict]] | None = None,
        format: str | None = None,
    ) -> dict:
        if (user_id is None) == (chat_id is None):
            raise ValueError("pass exactly one of user_id or chat_id")
        body: dict = {"text": text}
        if buttons:
            body["attachments"] = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]
        if format:
            body["format"] = format
        params = {"user_id": user_id} if user_id is not None else {"chat_id": chat_id}
        return self._request("POST", "/messages", params=params, json=body)

    def edit_message(
        self,
        message_id: str,
        *,
        text: str,
        buttons: list[list[dict]] | None = None,
    ) -> dict:
        attachments = []
        if buttons:
            attachments = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]
        return self._request(
            "PUT",
            "/messages",
            params={"message_id": message_id},
            json={"text": text, "attachments": attachments},
        )

    def answer_callback(
        self,
        callback_id: str,
        *,
        text: str,
        buttons: list[list[dict]] | None = None,
    ) -> dict:
        attachments = []
        if buttons:
            attachments = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]
        return self._request(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json={"message": {"text": text, "attachments": attachments}},
        )

    def download_file(self, url: str) -> bytes:
        response = httpx.get(url, verify=self._context, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return response.content
