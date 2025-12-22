# church/urls.py - CORRECTED VERSION
from django.urls import path
from . import views 
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [

    # ========== API ENDPOINTS (MUST COME FIRST) ==========
    path("api/departments/", views.department_list_api_view, name='api_department_list'),
    path("api/departments/create/", views.department_create_api_view, name='api_department_create'),
    path("api/departments/<uuid:department_id>/update/", views.department_update_api_view, name='api_department_update'),
    path("api/departments/<uuid:department_id>/delete/", views.department_delete_api_view, name='api_department_delete'),
    path('api/departments/<uuid:department_id>/', views.department_detail_api_view, name='api_department_detail'),

    path('api/departments/<uuid:department_id>/members/', views.department_members_api_view, name='api_department_members'),
    path('api/departments/<uuid:department_id>/members/add/', views.department_add_members_api_view, name='api_department_add_members'),
    path('api/departments/<uuid:department_id>/members/remove/', views.department_remove_members_api_view, name='api_department_remove_members'),

    # JWT Token endpoints
    path("api/token/", TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path("api/token/refresh/", TokenRefreshView.as_view(), name='token_refresh'),

    # Campus URLs
    path('api/campuses/', views.campus_list_api_view, name='api_campus_list'),
    path('api/campuses/<uuid:campus_id>/', views.campus_detail_api_view, name='api_campus_detail'),
    path('api/campuses/create/', views.campus_create_api_view, name='api_campus_create'),
    path('api/campuses/<uuid:campus_id>/update/', views.campus_update_api_view, name='api_campus_update'),
    path('api/campuses/<uuid:campus_id>/delete/', views.campus_delete_api_view, name='api_campus_delete'),
    path('api/campuses/<uuid:campus_id>/members/', views.campus_members_api_view, name='api_campus_members'),
    path('api/campuses/<uuid:campus_id>/members/add/', views.campus_add_members_api_view, name='api_campus_add_members'),
    path('api/campuses/<uuid:campus_id>/members/remove/', views.campus_remove_members_api_view, name='api_campus_remove_members'),

    # Family URLs
    path('api/families/', views.family_list_api_view, name='api_family_list'),
    path('api/families/<uuid:family_id>/', views.family_detail_api_view, name='api_family_detail'),
    path('api/families/create/', views.family_create_api_view, name='api_family_create'),
    path('api/families/<uuid:family_id>/update/', views.family_update_api_view, name='api_family_update'),
    path('api/families/<uuid:family_id>/delete/', views.family_delete_api_view, name='api_family_delete'),
    path('api/families/<uuid:family_id>/members/', views.family_members_api_view, name='api_family_members'),
    path('api/families/<uuid:family_id>/members/add/', views.family_add_members_api_view, name='api_family_add_members'),
    path('api/families/<uuid:family_id>/members/remove/', views.family_remove_members_api_view, name='api_family_remove_members'),

    # Add to your church/urls.py

 # ========== ORGANIZATION-SPECIFIC ROUTES ==========
    path("<uuid:organization_id>/invite/", views.send_invite_view, name="send_invite"),
    path("<uuid:organization_id>/", views.organization_dashboard_view, name="organization_dashboard"),
    
    # ========== GENERAL ROUTES ==========
    path("", views.organization_list_view, name="organizations_list"),
    path("apply/", views.organization_apply_view, name="organization_apply"),
    path("invites/accept/", views.accept_invite_view, name="accept_invite"),
    path("admin/create/", views.create_org_owner_view, name="create_org_owner"),
    path("plans/", views.subscription_plan_list_view, name="subscription_plan_list"),
    path("plans/create/", views.subscription_plan_create_view, name="subscription_plan_create"),
    path("plans/<uuid:plan_id>/edit/", views.subscription_plan_update_view, name="subscription_plan_edit"),
    path("plans/<uuid:plan_id>/delete/", views.subscription_plan_delete_view, name="subscription_plan_delete"),
    
    # ========== ORGANIZATION DETAIL BY SLUG (MUST BE LAST) ==========
    path("<slug:slug>/", views.organization_detail_view, name="organization_detail"),

    
]