from django.urls import path

from . import views

# Draft API contract for the mini-app. Replace a stub with a real view as each endpoint is implemented.
STUBS = [
    ("network/", "network"),
    ("dashboard/", "dashboard"),
    ("stores/", "stores"),
    ("stores/<int:store_id>/", "store-detail"),
    ("stores/<int:store_id>/day/", "store-day"),
    ("stores/<int:store_id>/employees/", "store-employees"),
    ("stores/<int:store_id>/task-templates/", "store-task-templates"),
    ("stores/<int:store_id>/schedule/", "store-schedule"),
    ("stores/<int:store_id>/schedule/coverage/", "store-schedule-coverage"),
    ("stores/<int:store_id>/schedule/publish/", "store-schedule-publish"),
    ("employees/<int:employee_id>/invite/", "employee-invite"),
    ("employees/<int:employee_id>/dismiss/", "employee-dismiss"),
    ("task-templates/<int:template_id>/", "task-template-detail"),
    ("shifts/<int:shift_id>/", "shift-detail"),
    ("completions/<int:completion_id>/photo/", "completion-photo"),
]

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("me/", views.MeView.as_view(), name="me"),
] + [
    path(route, views.NotImplementedEndpoint.as_view(endpoint=name), name=name)
    for route, name in STUBS
]
