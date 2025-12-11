# sanctuary/church/urls.py
from django.urls import path
from .import views

urlpatterns = [
        # Auth (already works - your mobile login is here)
    path('auth/login/', views.api_login_view, name='api_login'),  # This exists!
    
    # Expose your existing DRF views:
    path('organizations/apply/', views.OrganizationApplicationView.as_view(), name='api_organizations_apply'),
    path('invites/', views.InviteCreateView.as_view(), name='api_invites'),
    path('invites/accept/', views.AcceptInviteView.as_view(), name='api_accept_invite'),
    path('organizations/create/', views.OrganizationCreateView.as_view(), name='api_organizations_create'),
    path('organizations/<uuid:organization_id>/payment-link/', views.SendPaymentLinkView.as_view(), name='api_payment_link'),
    
    # Add a user profile endpoint
    path('auth/profile/', views.UserProfileView.as_view(), name='api_profile'),
    path("invites/", views.InviteCreateView.as_view(), name="invite-create"),
    path("invites/accept/", views.AcceptInviteView.as_view(), name="invite-accept"),
]
