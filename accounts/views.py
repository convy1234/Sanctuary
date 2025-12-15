from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from church.models import Invitation, Organization
from church.utils import send_invitation_email
from .serializers import (
    EmailTokenObtainPairSerializer,
    InvitationAcceptSerializer,
    InvitationCreateSerializer,
    UserSerializer,
)


class CanInvitePermission(permissions.BasePermission):
    """Allow only staff/owner/admin-level users to send invites."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_staff
                or getattr(user, "is_owner", False)
                or getattr(user, "is_admin", False)
            )
        )


class EmailTokenObtainPairView(TokenObtainPairView):
    """JWT login for mobile/web clients using email/password."""

    serializer_class = EmailTokenObtainPairSerializer


class InvitationCreateAPIView(generics.CreateAPIView):
    """Create an invitation; only staff/owners/admins are allowed."""

    serializer_class = InvitationCreateSerializer
    permission_classes = [permissions.IsAuthenticated, CanInvitePermission]

    def perform_create(self, serializer):
        invitation = serializer.save()
        send_invitation_email(invitation, self.request)


class InvitationAcceptAPIView(generics.GenericAPIView):
    """Accept an invitation and issue JWT tokens."""

    serializer_class = InvitationAcceptSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "detail": "Invitation accepted.",
                "user": UserSerializer(user).data,
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
            },
            status=status.HTTP_200_OK,
        )


class MeAPIView(generics.GenericAPIView):
    """Return authenticated user details."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(self.get_serializer(request.user).data)


# --- Simple HTML-oriented stubs to keep existing routes working ---


@require_http_methods(["GET", "POST"])
def login_view(request):
    default_next = reverse("dashboard")
    next_url = request.GET.get("next") or request.POST.get("next") or default_next
    context = {"next": next_url}
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, email=email, password=password)
        if user:
            login(request, user)
            return redirect(next_url)
        context.update({"error": "Invalid email or password", "email": email})
        return render(request, "login.html", context, status=400)
    return render(request, "login.html", context)


@require_http_methods(["GET"])
def register_view(request):
    return render(
        request,
        "register_invite_only.html",
        status=403,
    )


@login_required
@require_http_methods(["POST", "GET"])
def logout_view(request):
    logout(request)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"detail": "Logged out"})
    return redirect(reverse("login"))


@login_required
def dashboard_view(request):
    # Render web dashboard; API clients can still call /api/auth/login/ for tokens.
    user = request.user
    org = user.organization
    org_user_count = org.user_set.count() if org else 0
    pending_invites = (
        Invitation.objects.filter(organization=org, accepted_at__isnull=True).count()
        if org
        else 0
    )
    recent_invites = (
        Invitation.objects.filter(organization=org).order_by("-created_at")[:5] if org else []
    )
    recent_users = org.user_set.order_by("-date_joined")[:5] if org else []
    subscription = getattr(org, "subscription", None) if org else None
    analytics = {
        "organizations_total": Organization.objects.count()
        if user.is_superuser or user.is_staff
        else (1 if org else 0),
        "my_org_member_count": org_user_count,
        "my_org_pending_invites": pending_invites,
        "capacity_min": subscription.plan.capacity_min if subscription else None,
        "capacity_max": subscription.plan.capacity_max if subscription else None,
        "subscription_plan": subscription.plan.name if subscription else None,
        "subscription_status": subscription.status if subscription else None,
    }
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "detail": "Dashboard",
                "user": UserSerializer(user).data,
                "analytics": analytics,
                "recent_invites": [invitation.email for invitation in recent_invites],
                "recent_users": [u.email for u in recent_users],
            }
        )
    return render(
        request,
        "dashboard.html",
        {
            "user": user,
            "analytics": analytics,
            "recent_invites": recent_invites,
            "recent_users": recent_users,
        },
    )
