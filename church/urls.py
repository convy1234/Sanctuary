from django.urls import path

from . import views 

urlpatterns = [
    # API endpoints
    path("api/", views.organization_list_view, name="organizations_list_api"),
    path("api/<slug:slug>/", views.organization_detail_view, name="organization_detail_api"),

    # frontend views
    path("", views.organization_list_view, name="organizations_list"),
    path("apply/", views.organization_apply_view, name="organization_apply"),
    path("invites/accept/", views.accept_invite_view, name="accept_invite"),
    path("admin/create/", views.create_org_owner_view, name="create_org_owner"),
    path("plans/", views.subscription_plan_list_view, name="subscription_plan_list"),
    path("plans/create/", views.subscription_plan_create_view, name="subscription_plan_create"),
    path("plans/<uuid:plan_id>/edit/", views.subscription_plan_update_view, name="subscription_plan_edit"),
    path("plans/<uuid:plan_id>/delete/", views.subscription_plan_delete_view, name="subscription_plan_delete"),
    path("<uuid:organization_id>/invite/", views.send_invite_view, name="send_invite"),
    path("<uuid:organization_id>/", views.organization_dashboard_view, name="organization_dashboard"),
    path("<slug:slug>/", views.organization_detail_view, name="organization_detail"),
]
