import mimetypes

from django.http import FileResponse
from rest_framework.views import APIView

from apps.core.models import Completion

from ..scoping import not_found, owner_network


class CompletionPhotoView(APIView):
    def get(self, request, completion_id):
        try:
            completion = Completion.objects.get(
                pk=completion_id, instance__template__store__network=owner_network(request)
            )
        except Completion.DoesNotExist:
            raise not_found("Фото не найдено")
        if not completion.photo:
            raise not_found("Фото не найдено")

        content_type = mimetypes.guess_type(completion.photo.name)[0] or "image/jpeg"
        return FileResponse(completion.photo.open("rb"), content_type=content_type)
