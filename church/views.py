from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import SubscriptionPlanForm
from .utils import send_invitation_email
from accounts.serializers import InvitationAcceptSerializer, InvitationCreateSerializer
from .models import Invitation, Organization, OrganizationSubscription, SubscriptionPlan


@login_required
def organization_dashboard_view(request, organization_id):
    org = get_object_or_404(Organization, id=organization_id)
    if not user_can_view_org(request.user, org):
        return HttpResponseForbidden("You do not have access to this organization.")
    return render(request, "organization_detail.html", {"organization": org, "subscription": getattr(org, "subscription", None)})


@login_required
@require_http_methods(["GET", "POST"])
def organization_apply_view(request):
    return HttpResponse("Organization applications are handled by an administrator.")


@login_required
@require_http_methods(["GET"])
def organization_list_view(request):
    """List church organizations scoped to the current user (or all for superusers)."""
    user = request.user
    if user.is_superuser or user.is_staff:
        orgs = Organization.objects.all().order_by("name")
    elif user.organization:
        orgs = Organization.objects.filter(id=user.organization_id)
    else:
        orgs = Organization.objects.none()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        data = [
            {"id": str(o.id), "name": o.name, "slug": o.slug}
            for o in orgs
        ]
        return JsonResponse({"organizations": data})
    return render(request, "organizations_list.html", {"organizations": orgs})


@login_required
@require_http_methods(["GET"])
def organization_detail_view(request, slug):
    """Organization detail with subscription info."""
    org = get_object_or_404(Organization, slug=slug)
    if not user_can_view_org(request.user, org):
        return HttpResponseForbidden("You do not have access to this organization.")
    subscription = getattr(org, "subscription", None)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "subscription": {
                    "plan": subscription.plan.name if subscription else None,
                    "capacity_min": subscription.plan.capacity_min if subscription else None,
                    "capacity_max": subscription.plan.capacity_max if subscription else None,
                    "status": subscription.status if subscription else None,
                }
                if subscription
                else None,
            }
        )
    return render(
        request,
        "organization_detail.html",
        {
            "organization": org,
            "subscription": subscription,
        },
    )


@require_http_methods(["GET", "POST"])
def accept_invite_view(request):
    token = request.GET.get("token") or request.POST.get("token")
    context = {"token": token}

    if request.method == "POST":
        serializer = InvitationAcceptSerializer(
            data={
                "token": token,
                "password": request.POST.get("password"),
                "first_name": request.POST.get("first_name", ""),
                "last_name": request.POST.get("last_name", ""),
            }
        )
        if serializer.is_valid():
            user = serializer.save()
            login(request, user)
            return redirect(reverse("dashboard"))
        context.update(
            {
                "errors": serializer.errors,
                "first_name": request.POST.get("first_name", ""),
                "last_name": request.POST.get("last_name", ""),
            }
        )
        return render(request, "accept_invite.html", context, status=400)

    return render(request, "accept_invite.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def send_invite_view(request, organization_id):
    organization = get_object_or_404(Organization, id=organization_id)
    if not (request.user.is_superuser or request.user.organization_id == organization.id):
        return HttpResponseForbidden("You do not have access to this organization.")
    can_invite = (
        request.user.is_staff
        or getattr(request.user, "is_owner", False)
        or getattr(request.user, "is_admin", False)
    )
    if not can_invite:
        return HttpResponseForbidden("Only admins can send invitations.")

    role_choices = Invitation.ROLE_CHOICES
    context = {"organization": organization, "role_choices": role_choices}
    if request.method == "POST":
        serializer = InvitationCreateSerializer(
            data={
                "email": request.POST.get("email"),
                "organization": organization.id,
                "role": request.POST.get("role"),
                "note": request.POST.get("note", ""),
                "as_owner": bool(request.POST.get("as_owner")),
            },
            context={"request": request},
        )
        if serializer.is_valid():
            invitation = serializer.save()
            send_invitation_email(invitation, request)
            context.update({"invitation": invitation, "success": True})
            return render(request, "send_invite.html", context)
        context.update(
            {
                "errors": serializer.errors,
                "email": request.POST.get("email"),
                "role": request.POST.get("role"),
                "as_owner": request.POST.get("as_owner"),
                "note": request.POST.get("note", ""),
            }
        )
        return render(request, "send_invite.html", context, status=400)

    return render(request, "send_invite.html", context)


superuser_required = user_passes_test(lambda u: u.is_superuser)


@login_required
@superuser_required
@require_http_methods(["GET"])
def subscription_plan_list_view(request):
    plans = SubscriptionPlan.objects.all().order_by("name")
    return render(request, "subscription_plan_list.html", {"plans": plans})


@login_required
@superuser_required
@require_http_methods(["GET", "POST"])
def subscription_plan_create_view(request):
    form = SubscriptionPlanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(reverse("subscription_plan_list"))
    return render(request, "subscription_plan_form.html", {"form": form, "is_edit": False})


@login_required
@superuser_required
@require_http_methods(["GET", "POST"])
def subscription_plan_update_view(request, plan_id):
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    form = SubscriptionPlanForm(request.POST or None, instance=plan)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(reverse("subscription_plan_list"))
    return render(
        request,
        "subscription_plan_form.html",
        {"form": form, "plan": plan, "is_edit": True},
    )


@login_required
@superuser_required
@require_http_methods(["POST"])
def subscription_plan_delete_view(request, plan_id):
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    plan.delete()
    return redirect(reverse("subscription_plan_list"))


def user_can_view_org(user, organization: Organization) -> bool:
    """Restrict organization visibility to users of that org or elevated users."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.organization_id == organization.id


@login_required
@require_http_methods(["GET", "POST"])
def create_org_owner_view(request):
    """Superuser creates org, selects plan, and sends owner invite."""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Only superusers can create organizations.")

    plans = SubscriptionPlan.objects.filter(is_active=True)
    context = {"plans": plans}

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        slug = request.POST.get("slug", "").strip()
        owner_email = request.POST.get("owner_email", "").strip().lower()
        plan_id = request.POST.get("plan")
        note = request.POST.get("note", "")

        errors = {}
        if not name:
            errors["name"] = ["Name is required."]
        if not slug:
            errors["slug"] = ["Slug is required."]
        if not owner_email:
            errors["owner_email"] = ["Owner email is required."]
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            plan = None
            errors["plan"] = ["Select a valid plan."]

        if not errors and Organization.objects.filter(slug=slug).exists():
            errors["slug"] = ["Slug already exists."]

        if errors:
            context.update(
                {
                    "errors": errors,
                    "name": name,
                    "slug": slug,
                    "owner_email": owner_email,
                    "note": note,
                    "plan_id": plan_id,
                }
            )
            return render(request, "create_org_owner.html", context, status=400)

        org = Organization.objects.create(
            name=name,
            slug=slug,
            created_by=request.user,
        )
        OrganizationSubscription.objects.create(
            organization=org,
            plan=plan,
        )
        invitation = InvitationCreateSerializer(
            data={
                "email": owner_email,
                "organization": org.id,
                "note": note,
                "as_owner": True,
            },
            context={"request": request},
        )
        if invitation.is_valid():
            invite_obj = invitation.save()
            context.update({"organization": org, "invitation": invite_obj, "success": True})
            return render(request, "create_org_owner.html", context)
        org.delete()
        context.update(
            {
                "errors": invitation.errors,
                "name": name,
                "slug": slug,
                "owner_email": owner_email,
                "note": note,
                "plan_id": plan_id,
            }
        )
        return render(request, "create_org_owner.html", context, status=400)

    return render(request, "create_org_owner.html", context)
