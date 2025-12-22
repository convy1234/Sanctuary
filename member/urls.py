# church/urls.py - CORRECTED VERSION
from django.urls import path
from . import views 
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [

    # Member routes
    path("members/", views.member_list_view, name='member_list'),
    path("members/create/", views.member_create_view, name='member_create'),
    path("members/<uuid:member_id>/", views.member_detail_view, name='member_detail'),
    path("members/<uuid:member_id>/edit/", views.member_edit_view, name='member_edit'),
    path('members/<uuid:member_id>/delete/', views.member_delete_view, name='member_delete'),
    path('members/statistics/', views.member_statistics_view, name='member_statistics'),

      # Members API
    path("api/members/", views.member_list_api_view, name='api_member_list'),
    path("api/members/<uuid:member_id>/", views.member_detail_api_view, name='api_member_detail'),
    path("api/members/create/", views.member_create_api_view, name='api_member_create'),
    path("api/members/<uuid:member_id>/update/", views.member_update_api_view, name='api_member_update'),
    path("api/members/<uuid:member_id>/delete/", views.member_delete_api_view, name='api_member_delete'),
    path("api/members/statistics/", views.member_statistics_api_view, name='api_member_statistics'),
    
]