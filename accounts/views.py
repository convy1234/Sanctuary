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
    org_member_count = (
        org.members.count() if org and hasattr(org, "members") else 0
    )
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
        "my_org_user_count": org_user_count,
        "my_org_member_count": org_member_count,
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


@require_http_methods(["GET"])
def api_docs_view(request):
    """Surface the mobile-facing APIs inside the web dashboard."""

    def absolute(name, **kwargs):
        """Build absolute URLs so they can be used directly in mobile clients."""
        return request.build_absolute_uri(reverse(name, kwargs=kwargs))

    sample_ids = {
        "member": "11111111-1111-1111-1111-111111111111",
        "department": "22222222-2222-2222-2222-222222222222",
        "campus": "33333333-3333-3333-3333-333333333333",
        "family": "44444444-4444-4444-4444-444444444444",
        "voucher": "55555555-5555-5555-5555-555555555555",
        "item": "66666666-6666-6666-6666-666666666666",
        "checkout": "77777777-7777-7777-7777-777777777777",
        "channel": "88888888-8888-8888-8888-888888888888",
        "dm": "99999999-9999-9999-9999-999999999999",
        "message": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    }

    api_sections = [
        {
            "title": "Auth & Invitations",
            "icon": "🔐",
            "description": "JWT auth endpoints shared by mobile and the web dashboard.",
            "endpoints": [
                {
                    "label": "Login (JWT)",
                    "method": "POST",
                    "path": absolute("api_auth_login"),
                    "note": "Exchange email/password for access + refresh tokens.",
                    "sample": '{\n  "email": "you@example.com",\n  "password": "secret"\n}',
                },
                {
                    "label": "Refresh token",
                    "method": "POST",
                    "path": absolute("api_auth_refresh"),
                    "note": "Get a new access token from a refresh token.",
                    "sample": '{ "refresh": "<refresh_token>" }',
                },
                {
                    "label": "Me",
                    "method": "GET",
                    "path": absolute("api_auth_me"),
                    "note": "Return the authenticated user; requires Bearer token.",
                    "sample": None,
                },
                {
                    "label": "Create invite",
                    "method": "POST",
                    "path": absolute("api_invitation_create"),
                    "note": "Invite a user into an organization (admins/owners only).",
                    "sample": '{\n  "email": "invitee@example.com",\n  "organization": "<org_uuid>",\n  "role": "admin"\n}',
                },
                {
                    "label": "Accept invite",
                    "method": "POST",
                    "path": absolute("api_invitation_accept"),
                    "note": "Accept invitation and set a password; returns tokens.",
                    "sample": '{\n  "token": "<invite_token>",\n  "password": "new-password",\n  "first_name": "Ada",\n  "last_name": "Lovelace"\n}',
                },
            ],
        },
        {
            "title": "Members",
            "icon": "👥",
            "description": "Member CRUD with search, filtering, and statistics used by the app roster screens.",
            "endpoints": [
                {
                    "label": "List members",
                    "method": "GET",
                    "path": absolute("api_member_list"),
                    "note": "Supports ?search=&status=&campus=&department=&page=&page_size=.",
                    "sample": None,
                },
                {
                    "label": "Member detail",
                    "method": "GET",
                    "path": absolute("api_member_detail", member_id=sample_ids["member"]),
                    "note": "Full profile payload for a single member.",
                    "sample": None,
                },
                {
                    "label": "Create member",
                    "method": "POST",
                    "path": absolute("api_member_create"),
                    "note": "Create a member record scoped to the caller's organization.",
                    "sample": '{\n  "first_name": "Grace",\n  "last_name": "Hopper",\n  "email": "grace@example.com",\n  "status": "active"\n}',
                },
                {
                    "label": "Update member",
                    "method": "PATCH",
                    "path": absolute("api_member_update", member_id=sample_ids["member"]),
                    "note": "Partial update; accepts the same fields as create.",
                    "sample": '{ "phone": "+15551234" }',
                },
                {
                    "label": "Delete member",
                    "method": "DELETE",
                    "path": absolute("api_member_delete", member_id=sample_ids["member"]),
                    "note": "Soft-delete/removal hook used by mobile.",
                    "sample": None,
                },
                {
                    "label": "Member statistics",
                    "method": "GET",
                    "path": absolute("api_member_statistics"),
                    "note": "Aggregates counts by status, gender, and campus.",
                    "sample": None,
                },
            ],
        },
        {
            "title": "Departments, Campuses, Families",
            "icon": "🗂️",
            "description": "Grouping APIs that power team rosters and household views.",
            "endpoints": [
                {
                    "label": "Departments list",
                    "method": "GET",
                    "path": absolute("api_department_list"),
                    "note": "Supports ?search= and ordering filters.",
                    "sample": None,
                },
                {
                    "label": "Department detail",
                    "method": "GET",
                    "path": absolute("api_department_detail", department_id=sample_ids["department"]),
                    "note": "Includes members and leadership roles.",
                    "sample": None,
                },
                {
                    "label": "Add members to department",
                    "method": "POST",
                    "path": absolute("api_department_add_members", department_id=sample_ids["department"]),
                    "note": "Body: {\"member_ids\": [\"<uuid>\", ...]}",
                    "sample": '{ "member_ids": ["<member_uuid>"] }',
                },
                {
                    "label": "Campuses list",
                    "method": "GET",
                    "path": absolute("api_campus_list"),
                    "note": "List campuses for the organization.",
                    "sample": None,
                },
                {
                    "label": "Campus detail",
                    "method": "GET",
                    "path": absolute("api_campus_detail", campus_id=sample_ids["campus"]),
                    "note": "Includes address metadata and roster size.",
                    "sample": None,
                },
                {
                    "label": "Families list",
                    "method": "GET",
                    "path": absolute("api_family_list"),
                    "note": "Household roster used by pastoral care views.",
                    "sample": None,
                },
                {
                    "label": "Family detail",
                    "method": "GET",
                    "path": absolute("api_family_detail", family_id=sample_ids["family"]),
                    "note": "Members + family role assignments.",
                    "sample": None,
                },
            ],
        },
        {
            "title": "Vouchers & Approvals",
            "icon": "💸",
            "description": "Expense requests, approvals, and notifications consumed by the mobile finance module.",
            "endpoints": [
                {
                    "label": "Voucher dashboard",
                    "method": "GET",
                    "path": absolute("voucher-dashboard"),
                    "note": "High-level counts and summaries for the inbox screens.",
                    "sample": None,
                },
                {
                    "label": "List vouchers",
                    "method": "GET",
                    "path": absolute("voucher-list"),
                    "note": "Supports filters like status, type, and date windows.",
                    "sample": None,
                },
                {
                    "label": "Create voucher",
                    "method": "POST",
                    "path": absolute("voucher-create"),
                    "note": "Submit a new voucher; include amount, category, and attachments.",
                    "sample": '{\n  "title": "Sound equipment",\n  "amount": "250.00",\n  "category": "media"\n}',
                },
                {
                    "label": "Voucher detail",
                    "method": "GET",
                    "path": absolute("voucher-detail", voucher_id=sample_ids["voucher"]),
                    "note": "Full lifecycle data including comments and approvals.",
                    "sample": None,
                },
                {
                    "label": "Approve/Reject",
                    "method": "POST",
                    "path": absolute("voucher-approve", voucher_id=sample_ids["voucher"]),
                    "note": "Use /approve/ or /reject/ with {\"note\": \"...\"}.",
                    "sample": '{ "note": "Looks good" }',
                },
                {
                    "label": "Mark paid",
                    "method": "POST",
                    "path": absolute("voucher-pay", voucher_id=sample_ids["voucher"]),
                    "note": "Record payment info for a voucher.",
                    "sample": '{ "reference": "TRX-1001" }',
                },
                {
                    "label": "Notifications",
                    "method": "GET",
                    "path": absolute("api_vouchers_notifications"),
                    "note": "Unread + recent events for approvers.",
                    "sample": None,
                },
                {
                    "label": "Reports",
                    "method": "GET",
                    "path": absolute("api_voucher_reports"),
                    "note": "Summary analytics plus trend endpoints for expense tracking.",
                    "sample": None,
                },
            ],
        },
        {
            "title": "Inventory",
            "icon": "Inventory",
            "description": "Stock, checkouts, and transaction history that mirror the mobile inventory module.",
            "endpoints": [
                {
                    "label": "Inventory dashboard",
                    "method": "GET",
                    "path": absolute("inventory_api_dashboard"),
                    "note": "Counts, low-stock alerts, and quick stats.",
                    "sample": None,
                },
                {
                    "label": "Items list",
                    "method": "GET",
                    "path": absolute("inventory_api_item_list"),
                    "note": "Query params: search, category, vendor, status, location.",
                    "sample": None,
                },
                {
                    "label": "Item detail",
                    "method": "GET",
                    "path": absolute("inventory_api_item_detail", item_id=sample_ids["item"]),
                    "note": "Full item payload including thresholds and vendor links.",
                    "sample": None,
                },
                {
                    "label": "Create item",
                    "method": "POST",
                    "path": absolute("inventory_api_item_create"),
                    "note": "Create/update also used by the web form.",
                    "sample": '{\n  "name": "Wireless mic",\n  "category": "<category_uuid>",\n  "quantity": 4\n}',
                },
                {
                    "label": "Update item",
                    "method": "PATCH",
                    "path": absolute("inventory_api_item_update", item_id=sample_ids["item"]),
                    "note": "Partial updates supported.",
                    "sample": '{ "status": "in_use" }',
                },
                {
                    "label": "Delete item",
                    "method": "DELETE",
                    "path": absolute("inventory_api_item_delete", item_id=sample_ids["item"]),
                    "note": "Removes an item from the catalog.",
                    "sample": None,
                },
                {
                    "label": "Checkouts",
                    "method": "GET",
                    "path": absolute("inventory_api_checkout_list"),
                    "note": "Recent checkouts with pagination.",
                    "sample": None,
                },
                {
                    "label": "Create checkout",
                    "method": "POST",
                    "path": absolute("inventory_api_checkout_create"),
                    "note": "Reserve an item with due dates and assignees.",
                    "sample": '{\n  "item": "<item_uuid>",\n  "assignee": "<member_uuid>",\n  "due_back": "2025-01-05"\n}',
                },
                {
                    "label": "Transactions",
                    "method": "GET",
                    "path": absolute("inventory_api_transaction_list"),
                    "note": "Audit trail; filter by item_id, transaction_type, date range.",
                    "sample": None,
                },
                {
                    "label": "Stock adjust",
                    "method": "POST",
                    "path": absolute("inventory_api_stock_adjust"),
                    "note": "Atomic adjustments with validation for add/remove/set.",
                    "sample": '{\n  "item_id": "<item_uuid>",\n  "adjustment_type": "add",\n  "quantity": 2,\n  "reason": "Recounted stock"\n}',
                },
            ],
        },
        {
            "title": "Chat",
            "icon": "Chat",
            "description": "Channels and direct messages shared by mobile and the dashboard chat pane (JWT auth).",
            "endpoints": [
                {
                    "label": "Chat home",
                    "method": "GET",
                    "path": absolute("chat_home_api"),
                    "note": "Landing payload: channels, direct messages, org roster, and unread counts.",
                    "sample": None,
                },
                {
                    "label": "Create channel",
                    "method": "POST",
                    "path": absolute("channel_create_api"),
                    "note": "Body: name, description, is_public, is_read_only. Public channels auto-join org members.",
                    "sample": '{\n  "name": "general",\n  "description": "Org-wide chat",\n  "is_public": true\n}',
                },
                {
                    "label": "Channel detail",
                    "method": "GET",
                    "path": absolute("channel_detail_api", channel_id=sample_ids["channel"]),
                    "note": "Returns channel info, membership, and paginated messages.",
                    "sample": None,
                },
                {
                    "label": "Send channel message",
                    "method": "POST",
                    "path": absolute("send_channel_message_api", channel_id=sample_ids["channel"]),
                    "note": "Post a text message to a channel thread.",
                    "sample": '{ "content": "Hello team" }',
                },
                {
                    "label": "Start direct message",
                    "method": "POST",
                    "path": absolute("start_dm_api"),
                    "note": "Body: {\"user_id\": \"<user_uuid>\"} to open or reuse a DM within the organization.",
                    "sample": '{ "user_id": "<user_uuid>" }',
                },
                {
                    "label": "DM detail",
                    "method": "GET",
                    "path": absolute("dm_detail_api", dm_id=sample_ids["dm"]),
                    "note": "Direct message participants and message history.",
                    "sample": None,
                },
                {
                    "label": "Send DM message",
                    "method": "POST",
                    "path": absolute("send_dm_message_api", dm_id=sample_ids["dm"]),
                    "note": "Send a message inside a DM thread.",
                    "sample": '{ "content": "Ping" }',
                },
                {
                    "label": "Mark messages read",
                    "method": "POST",
                    "path": absolute("mark_messages_read_api"),
                    "note": "Body: {\"type\": \"channel|dm\", \"target_id\": \"<uuid>\"} to update unread counts.",
                    "sample": '{ "type": "channel", "target_id": "<channel_uuid>" }',
                },
                {
                    "label": "Delete message",
                    "method": "DELETE",
                    "path": absolute("delete_message_api", message_id=sample_ids["message"]),
                    "note": "Delete a message you own (admins may override).",
                    "sample": None,
                },
                {
                    "label": "Widget summary (session)",
                    "method": "GET",
                    "path": absolute("chat_widget_summary"),
                    "note": "Dashboard sidebar/chat page feed; lists channels, DMs, and people (session cookie).",
                    "sample": None,
                },
                {
                    "label": "Widget messages (session)",
                    "method": "GET",
                    "path": absolute("chat_widget_messages", thread_type="channel", thread_id=sample_ids["channel"]),
                    "note": "Fetch recent messages for a channel or dm using session auth.",
                    "sample": None,
                },
                {
                    "label": "Widget send (session)",
                    "method": "POST",
                    "path": absolute("chat_widget_send"),
                    "note": "Body: thread_type=channel|dm, thread_id, content. Uses CSRF + session cookie.",
                    "sample": "thread_type=channel&thread_id=<channel_uuid>&content=Hello",
                },
                {
                    "label": "Widget start DM (session)",
                    "method": "POST",
                    "path": absolute("chat_widget_start_dm"),
                    "note": "Body: user_id. Starts or reuses a DM for the dashboard chat page.",
                    "sample": "user_id=<user_uuid>",
                },
                {
                    "label": "Widget create channel (session)",
                    "method": "POST",
                    "path": absolute("chat_widget_create_channel"),
                    "note": "Body: name[, description, is_public]. Session-auth helper for the dashboard chat page.",
                    "sample": "name=general&is_public=true",
                },
            ],
        },
    ]

    auth_header = "Authorization: Bearer <access_token>"
    curl_example = (
        "curl -H \"Content-Type: application/json\" "
        f"-H \"{auth_header}\" \"{absolute('api_member_list')}?search=ada\""
    )

    return render(
        request,
        "api_docs.html",
        {
            "api_sections": api_sections,
            "auth_header": auth_header,
            "curl_example": curl_example,
        },
    )
