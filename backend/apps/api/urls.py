from django.urls import path

from . import views

STUBS = [
    ("network/", "network"),
]

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("me/", views.MeView.as_view(), name="me"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("stores/", views.StoreListView.as_view(), name="stores"),
    path("stores/<int:store_id>/", views.StoreDetailView.as_view(), name="store-detail"),
    path("stores/<int:store_id>/day/", views.StoreDayView.as_view(), name="store-day"),
    path("stores/<int:store_id>/employees/", views.StoreEmployeesView.as_view(), name="store-employees"),
    path(
        "stores/<int:store_id>/task-templates/",
        views.TaskTemplateListView.as_view(),
        name="store-task-templates",
    ),
    path("stores/<int:store_id>/schedule/", views.ScheduleView.as_view(), name="store-schedule"),
    path(
        "stores/<int:store_id>/schedule/coverage/",
        views.CoverageView.as_view(),
        name="store-schedule-coverage",
    ),
    path(
        "stores/<int:store_id>/schedule/publish/",
        views.PublishView.as_view(),
        name="store-schedule-publish",
    ),
    path("employees/<int:employee_id>/invite/", views.EmployeeInviteView.as_view(), name="employee-invite"),
    path("employees/<int:employee_id>/dismiss/", views.EmployeeDismissView.as_view(), name="employee-dismiss"),
    path("employees/<int:employee_id>/", views.EmployeeDeleteView.as_view(), name="employee-delete"),
    path(
        "task-templates/<int:template_id>/",
        views.TaskTemplateDetailView.as_view(),
        name="task-template-detail",
    ),
    path(
        "completions/<int:completion_id>/photo/",
        views.CompletionPhotoView.as_view(),
        name="completion-photo",
    ),
] + [
    path(route, views.NotImplementedEndpoint.as_view(endpoint=name), name=name)
    for route, name in STUBS
]
