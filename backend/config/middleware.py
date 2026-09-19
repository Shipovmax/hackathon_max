from django.conf import settings


class FrameAncestorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault(
            "Content-Security-Policy", f"frame-ancestors 'self' {settings.FRAME_ANCESTORS}"
        )
        return response
