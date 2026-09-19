from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class MeView(APIView):
    def get(self, request):
        account = request.user
        network = getattr(account, "network", None)
        return Response(
            {
                "max_user_id": account.max_user_id,
                "first_name": account.first_name,
                "role": account.role,
                "network": {"id": network.id, "name": network.name} if network else None,
            }
        )


class NotImplementedEndpoint(APIView):
    endpoint = ""

    def _respond(self, request, *args, **kwargs):
        return Response(
            {"detail": "not implemented", "endpoint": self.endpoint},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    get = post = put = patch = delete = _respond
