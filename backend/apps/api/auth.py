import hashlib
import hmac
import json
import time
from urllib.parse import unquote

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.core.models import MaxAccount, Role

INIT_DATA_HEADER = "HTTP_X_MAX_INIT_DATA"


class InitDataError(Exception):
    pass


def validate_init_data(
    init_data: str, bot_token: str, *, max_age_seconds: int, now: float | None = None
) -> dict:
    """Verify window.WebApp.initData as described in dev.max.ru/docs/webapps/validation and return its fields."""
    pairs = []
    for chunk in init_data.split("&"):
        if chunk:
            key, _, value = chunk.partition("=")
            pairs.append((key, unquote(value)))

    hashes = [value for key, value in pairs if key == "hash"]
    if len(hashes) != 1:
        raise InitDataError("hash must be present exactly once")

    fields = sorted(((k, v) for k, v in pairs if k != "hash"), key=lambda kv: kv[0])
    launch_params = "\n".join(f"{k}={v}" for k, v in fields)

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, launch_params.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, hashes[0]):
        raise InitDataError("signature mismatch")

    data = dict(fields)
    try:
        auth_date = int(data["auth_date"])
    except (KeyError, ValueError):
        raise InitDataError("auth_date is missing or invalid")
    if (now if now is not None else time.time()) - auth_date > max_age_seconds:
        raise InitDataError("init data expired")

    for key in ("user", "chat"):
        if key in data:
            try:
                data[key] = json.loads(data[key])
            except ValueError:
                raise InitDataError(f"{key} is not valid JSON")
    if not isinstance(data.get("user"), dict) or "id" not in data["user"]:
        raise InitDataError("user is missing")
    data["auth_date"] = auth_date
    return data


class MaxInitDataAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "MaxInitData"

    def authenticate(self, request):
        init_data = request.META.get(INIT_DATA_HEADER)
        if not init_data:
            return None
        if not settings.BOT_TOKEN:
            raise AuthenticationFailed("server has no BOT_TOKEN configured")
        try:
            data = validate_init_data(
                init_data,
                settings.BOT_TOKEN,
                max_age_seconds=settings.INIT_DATA_MAX_AGE_SECONDS,
            )
        except InitDataError as error:
            raise AuthenticationFailed(str(error), code="invalid_init_data")

        user = data["user"]
        account, _ = MaxAccount.objects.get_or_create(
            max_user_id=user["id"], defaults={"first_name": user.get("first_name") or ""}
        )
        if account.role != Role.OWNER:
            raise PermissionDenied(
                {"code": "not_owner", "detail": "The mini-app is available to owners only"}
            )
        return account, data
