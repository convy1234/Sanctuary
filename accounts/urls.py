from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from django.views.generic import TemplateView

from .views import (
    EmailTokenObtainPairView,
    InvitationAcceptAPIView,
    InvitationCreateAPIView,
    MeAPIView,
    login_view,
    register_view,
    logout_view,
)

urlpatterns = [
    # API endpoints
    path("api/auth/login/", EmailTokenObtainPairView.as_view(), name="api_auth_login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="api_auth_refresh"),
    path("api/auth/me/", MeAPIView.as_view(), name="api_auth_me"),
    path(
        "api/auth/invitations/",
        InvitationCreateAPIView.as_view(),
        name="api_invitation_create",
    ),
    path(
        "api/auth/invitations/accept/",
        InvitationAcceptAPIView.as_view(),
        name="api_invitation_accept",
    ),
    
    
    # Frontend pages
    path("login/", login_view, name="login"),
    path("api/docs/", TemplateView.as_view(template_name="api_docs.html"), name="api_docs"),
    path("register/", register_view, name="register"),
    path("logout/", logout_view, name="logout"),
    
]
