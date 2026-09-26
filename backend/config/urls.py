from django.contrib import admin
from django.urls import include, path, re_path

from .views import privacy, spa_index

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.api.urls")),
    path("privacy/", privacy, name="privacy"),
    re_path(r"^(?!api/|admin/|static/|privacy/?$).*$", spa_index, name="spa"),
]
