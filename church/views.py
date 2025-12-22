from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from httpcore import request

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


def get_user_organization(user):
    if hasattr(user, 'organization') and user.organization:
        return user.organization
    
    # fallback if user belongs via profile or membership
    if hasattr(user, 'profile') and hasattr(user.profile, 'organization'):
        return user.profile.organization
    
    return None


# church/views.py - ADD THESE IMPORTS AT THE TOP
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets, filters
from rest_framework_simplejwt.authentication import JWTAuthentication
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import MemberSerializer, DepartmentSerializer, FamilySerializer, CampusSerializer

# Keep your existing web views, but add these API views:

# ----- API VIEWS FOR MOBILE APP -----


# church/views.py - Add this helper function and update the create view

def format_date_for_model(date_value):
    """Helper to convert various date formats to YYYY-MM-DD."""
    if not date_value:
        return None
    
    from datetime import datetime
    
    if isinstance(date_value, str):
        # Try different date formats
        formats = [
            '%Y-%m-%d',  # 2024-01-15
            '%d/%m/%Y',  # 15/01/2024
            '%m/%d/%Y',  # 01/15/2024
            '%Y-%m-%dT%H:%M:%S.%fZ',  # ISO format with time
            '%Y-%m-%dT%H:%M:%S',      # ISO format without milliseconds
        ]
        
        for fmt in formats:
            try:
                date_obj = datetime.strptime(date_value, fmt)
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                continue
    
    # If it's already a date object
    if isinstance(date_value, datetime):
        return date_value.strftime('%Y-%m-%d')
    
    return None

# church/views.py - Add this helper function and update the create view

def format_date_for_model(date_value):
    """Helper to convert various date formats to YYYY-MM-DD."""
    if not date_value:
        return None
    
    from datetime import datetime
    
    if isinstance(date_value, str):
        # Try different date formats
        formats = [
            '%Y-%m-%d',  # 2024-01-15
            '%d/%m/%Y',  # 15/01/2024
            '%m/%d/%Y',  # 01/15/2024
            '%Y-%m-%dT%H:%M:%S.%fZ',  # ISO format with time
            '%Y-%m-%dT%H:%M:%S',      # ISO format without milliseconds
        ]
        
        for fmt in formats:
            try:
                date_obj = datetime.strptime(date_value, fmt)
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                continue
    
    # If it's already a date object
    if isinstance(date_value, datetime):
        return date_value.strftime('%Y-%m-%d')
    
    return None

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def department_list_api_view(request):
    """API endpoint for listing departments."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    departments = Department.objects.filter(organization=organization)
    serializer = DepartmentSerializer(departments, many=True, context={'request': request})
    return Response({'departments': serializer.data})

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def family_list_api_view(request):
    """API endpoint for listing families."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    families = Family.objects.filter(organization=organization)
    serializer = FamilySerializer(families, many=True, context={'request': request})
    return Response({'families': serializer.data})

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campus_list_api_view(request):
    """API endpoint for listing campuses."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    campuses = Campus.objects.filter(organization=organization)
    serializer = CampusSerializer(campuses, many=True, context={'request': request})
    return Response({'campuses': serializer.data})


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def department_list_api_view(request):
    """API endpoint for listing departments."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    departments = Department.objects.filter(organization=organization)
    serializer = DepartmentSerializer(departments, many=True, context={'request': request})
    
    return Response({
        'success': True,
        'departments': serializer.data,
        'count': departments.count()
    })

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campus_list_api_view(request):
    """API endpoint for listing campuses."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    campuses = Campus.objects.filter(organization=organization)
    serializer = CampusSerializer(campuses, many=True, context={'request': request})
    
    return Response({
        'success': True,
        'campuses': serializer.data,
        'count': campuses.count()
    })

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def family_list_api_view(request):
    """API endpoint for listing families."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    families = Family.objects.filter(organization=organization)
    serializer = FamilySerializer(families, many=True, context={'request': request})
    
    return Response({
        'success': True,
        'families': serializer.data,
        'count': families.count()
    })

# ✅ Department create view - CORRECT
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def department_create_api_view(request):
    """API endpoint for creating a department."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check permissions
    user = request.user
    can_create = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False)
    )
    
    if not can_create:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Create a mutable copy of the data
    data = request.data.copy()
    
    serializer = DepartmentSerializer(data=data, context={'request': request})
    
    if serializer.is_valid():
        # ✅ Pass organization when saving
        department = serializer.save(organization=organization)
        return Response(
            {
                'success': True,
                'message': 'Department created successfully',
                'department_id': str(department.id),
                'department': DepartmentSerializer(department, context={'request': request}).data
            },
            status=status.HTTP_201_CREATED
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ✅ Department update view - CORRECT
@api_view(['PUT', 'PATCH'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def department_update_api_view(request, department_id):
    """API endpoint for updating a department."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check permissions
    user = request.user
    can_update = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False)
    )
    
    if not can_update:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Get department and ensure it belongs to user's organization
        department = Department.objects.get(
            id=department_id,
            organization=organization
        )
    except Department.DoesNotExist:
        return Response(
            {'error': 'Department not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # For PUT requests, validate all required fields
    # For PATCH requests, allow partial updates
    if request.method == 'PATCH':
        serializer = DepartmentSerializer(
            department, 
            data=request.data, 
            partial=True,
            context={'request': request}
        )
    else:  # PUT
        serializer = DepartmentSerializer(
            department, 
            data=request.data, 
            context={'request': request}
        )
    
    if serializer.is_valid():
        department = serializer.save()
        return Response(
            {
                'success': True,
                'message': 'Department updated successfully',
                'department_id': str(department.id),
                'department': DepartmentSerializer(department, context={'request': request}).data
            },
            status=status.HTTP_200_OK
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def department_detail_api_view(request, department_id):
    """API endpoint for getting a single department."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        department = Department.objects.get(
            id=department_id,
            organization=organization
        )
        serializer = DepartmentSerializer(department, context={'request': request})
        return Response(serializer.data)
    except Department.DoesNotExist:
        return Response(
            {'error': 'Department not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )




@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def department_add_members_api_view(request, department_id):
    """Add members to a department."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        department = Department.objects.get(
            id=department_id,
            organization=organization
        )
    except Department.DoesNotExist:
        return Response(
            {'error': 'Department not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    member_ids = request.data.get('member_ids', [])
    if not isinstance(member_ids, list):
        return Response(
            {'error': 'member_ids must be a list'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get members that belong to the same organization
    members = Member.objects.filter(
        id__in=member_ids,
        organization=organization
    )
    
    # Add department to each member
    for member in members:
        member.departments.add(department)
    
    return Response({
        'success': True,
        'message': f'Added {len(members)} members to {department.name}',
        'added_count': len(members),
        'department': DepartmentSerializer(department, context={'request': request}).data
    })



@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def department_remove_members_api_view(request, department_id):
    """Remove members from a department."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        department = Department.objects.get(
            id=department_id,
            organization=organization
        )
    except Department.DoesNotExist:
        return Response(
            {'error': 'Department not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    member_ids = request.data.get('member_ids', [])
    if not isinstance(member_ids, list):
        return Response(
            {'error': 'member_ids must be a list'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get members that belong to the same organization
    members = Member.objects.filter(
        id__in=member_ids,
        organization=organization
    )
    
    # Remove department from each member
    for member in members:
        member.departments.remove(department)
    
    return Response({
        'success': True,
        'message': f'Removed {len(members)} members from {department.name}',
        'removed_count': len(members),
        'department': DepartmentSerializer(department, context={'request': request}).data
    })




@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def department_members_api_view(request, department_id):
    """Get all members in a department."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        department = Department.objects.get(
            id=department_id,
            organization=organization
        )
    except Department.DoesNotExist:
        return Response(
            {'error': 'Department not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    members = department.members.all()
    serializer = MemberSerializer(members, many=True, context={'request': request})
    
    return Response({
        'success': True,
        'department': DepartmentSerializer(department, context={'request': request}).data,
        'members': serializer.data,
        'count': members.count()
    })


# ✅ Department delete view - CORRECT
@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def department_delete_api_view(request, department_id):
    """API endpoint for deleting a department."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check permissions
    user = request.user
    can_delete = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False)
    )
    
    if not can_delete:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Get department and ensure it belongs to user's organization
        department = Department.objects.get(
            id=department_id,
            organization=organization
        )
    except Department.DoesNotExist:
        return Response(
            {'error': 'Department not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    department.delete()
    
    return Response(
        {
            'success': True,
            'message': 'Department deleted successfully',
            'department_id': str(department.id)
        },
        status=status.HTTP_200_OK
    )
# 🔧 FIXED Campus create view
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campus_create_api_view(request):
    """API endpoint for creating a campus."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check permissions
    user = request.user
    can_create = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False)
    )
    
    if not can_create:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    data = request.data.copy()
    # ❌ REMOVE THIS LINE - Don't set organization in data
    # data['organization'] = str(organization.id)
    
    serializer = CampusSerializer(data=data, context={'request': request})
    
    if serializer.is_valid():
        # ✅ Pass organization when saving
        campus = serializer.save(organization=organization)
        return Response(
            {
                'success': True,
                'message': 'Campus created successfully',
                'campus_id': str(campus.id),
                'campus': CampusSerializer(campus, context={'request': request}).data
            },
            status=status.HTTP_201_CREATED
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



# In church/views.py

# Campus member management views
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campus_members_api_view(request, campus_id):
    """Get all members in a campus."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        campus = Campus.objects.get(
            id=campus_id,
            organization=organization
        )
    except Campus.DoesNotExist:
        return Response(
            {'error': 'Campus not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    members = campus.members.all()
    serializer = MemberSerializer(members, many=True, context={'request': request})
    
    return Response({
        'success': True,
        'campus': CampusSerializer(campus, context={'request': request}).data,
        'members': serializer.data,
        'count': members.count()
    })

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campus_add_members_api_view(request, campus_id):
    """Add members to a campus."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        campus = Campus.objects.get(
            id=campus_id,
            organization=organization
        )
    except Campus.DoesNotExist:
        return Response(
            {'error': 'Campus not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    member_ids = request.data.get('member_ids', [])
    if not isinstance(member_ids, list):
        return Response(
            {'error': 'member_ids must be a list'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get members that belong to the same organization
    members = Member.objects.filter(
        id__in=member_ids,
        organization=organization
    )
    
    # Add campus to each member
    for member in members:
        member.campus = campus
        member.save()
    
    return Response({
        'success': True,
        'message': f'Added {len(members)} members to {campus.name}',
        'added_count': len(members),
        'campus': CampusSerializer(campus, context={'request': request}).data
    })


# 🔧 FIXED Family create view
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def family_create_api_view(request):
    """API endpoint for creating a family."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check permissions
    user = request.user
    can_create = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False)
    )
    
    if not can_create:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    data = request.data.copy()
    # ❌ REMOVE THIS LINE - Don't set organization in data
    # data['organization'] = str(organization.id)
    
    serializer = FamilySerializer(data=data, context={'request': request})
    
    if serializer.is_valid():
        # ✅ Pass organization when saving
        family = serializer.save(organization=organization)
        return Response(
            {
                'success': True,
                'message': 'Family created successfully',
                'family_id': str(family.id),
                'family': FamilySerializer(family, context={'request': request}).data
            },
            status=status.HTTP_201_CREATED
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ✅ Add these for completeness

@api_view(['PUT', 'PATCH'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campus_update_api_view(request, campus_id):
    """API endpoint for updating a campus."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check permissions
    user = request.user
    can_update = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False)
    )
    
    if not can_update:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        campus = Campus.objects.get(id=campus_id, organization=organization)
    except Campus.DoesNotExist:
        return Response(
            {'error': 'Campus not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    partial = request.method == 'PATCH'
    serializer = CampusSerializer(
        campus, 
        data=request.data, 
        partial=partial,
        context={'request': request}
    )
    
    if serializer.is_valid():
        campus = serializer.save()
        return Response(
            {
                'success': True,
                'message': 'Campus updated successfully',
                'campus_id': str(campus.id),
                'campus': CampusSerializer(campus, context={'request': request}).data
            },
            status=status.HTTP_200_OK
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campus_delete_api_view(request, campus_id):
    """API endpoint for deleting a campus."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check permissions
    user = request.user
    can_delete = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False)
    )
    
    if not can_delete:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        campus = Campus.objects.get(id=campus_id, organization=organization)
    except Campus.DoesNotExist:
        return Response(
            {'error': 'Campus not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    campus.delete()
    
    return Response(
        {
            'success': True,
            'message': 'Campus deleted successfully',
            'campus_id': str(campus.id)
        },
        status=status.HTTP_200_OK
    )

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campus_detail_api_view(request, campus_id):
    """API endpoint for getting a single campus."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        campus = Campus.objects.get(
            id=campus_id,
            organization=organization
        )
        serializer = CampusSerializer(campus, context={'request': request})
        return Response(serializer.data)
    except Campus.DoesNotExist:
        return Response(
            {'error': 'Campus not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['PUT', 'PATCH'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def family_update_api_view(request, family_id):
    """API endpoint for updating a family."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check permissions
    user = request.user
    can_update = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False)
    )
    
    if not can_update:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        family = Family.objects.get(id=family_id, organization=organization)
    except Family.DoesNotExist:
        return Response(
            {'error': 'Family not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    partial = request.method == 'PATCH'
    serializer = FamilySerializer(
        family, 
        data=request.data, 
        partial=partial,
        context={'request': request}
    )
    
    if serializer.is_valid():
        family = serializer.save()
        return Response(
            {
                'success': True,
                'message': 'Family updated successfully',
                'family_id': str(family.id),
                'family': FamilySerializer(family, context={'request': request}).data
            },
            status=status.HTTP_200_OK
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campus_remove_members_api_view(request, campus_id):
    """Remove members from a campus."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        campus = Campus.objects.get(
            id=campus_id,
            organization=organization
        )
    except Campus.DoesNotExist:
        return Response(
            {'error': 'Campus not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    member_ids = request.data.get('member_ids', [])
    if not isinstance(member_ids, list):
        return Response(
            {'error': 'member_ids must be a list'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get members that belong to the same organization
    members = Member.objects.filter(
        id__in=member_ids,
        organization=organization,
        campus=campus
    )
    
    # Remove campus from each member
    for member in members:
        member.campus = None
        member.save()
    
    return Response({
        'success': True,
        'message': f'Removed {len(members)} members from {campus.name}',
        'removed_count': len(members),
        'campus': CampusSerializer(campus, context={'request': request}).data
    })

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def family_delete_api_view(request, family_id):
    """API endpoint for deleting a family."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check permissions
    user = request.user
    can_delete = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False)
    )
    
    if not can_delete:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        family = Family.objects.get(id=family_id, organization=organization)
    except Family.DoesNotExist:
        return Response(
            {'error': 'Family not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    family.delete()
    
    return Response(
        {
            'success': True,
            'message': 'Family deleted successfully',
            'family_id': str(family.id)
        },
        status=status.HTTP_200_OK
    )

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def family_detail_api_view(request, family_id):
    """API endpoint for getting a single family."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        family = Family.objects.get(
            id=family_id,
            organization=organization
        )
        serializer = FamilySerializer(family, context={'request': request})
        return Response(serializer.data)
    except Family.DoesNotExist:
        return Response(
            {'error': 'Family not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def family_members_api_view(request, family_id):
    """Get all members in a family."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        family = Family.objects.get(
            id=family_id,
            organization=organization
        )
    except Family.DoesNotExist:
        return Response(
            {'error': 'Family not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    members = family.members.all()
    serializer = MemberSerializer(members, many=True, context={'request': request})
    
    return Response({
        'success': True,
        'family': FamilySerializer(family, context={'request': request}).data,
        'members': serializer.data,
        'count': members.count()
    })



@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def family_add_members_api_view(request, family_id):
    """Add members to a family."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        family = Family.objects.get(
            id=family_id,
            organization=organization
        )
    except Family.DoesNotExist:
        return Response(
            {'error': 'Family not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    member_ids = request.data.get('member_ids', [])
    if not isinstance(member_ids, list):
        return Response(
            {'error': 'member_ids must be a list'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get members that belong to the same organization
    members = Member.objects.filter(
        id__in=member_ids,
        organization=organization
    )
    
    # Add family to each member
    for member in members:
        member.family = family
        member.save()
    
    return Response({
        'success': True,
        'message': f'Added {len(members)} members to {family.family_name}',
        'added_count': len(members),
        'family': FamilySerializer(family, context={'request': request}).data
    })

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def family_remove_members_api_view(request, family_id):
    """Remove members from a family."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        family = Family.objects.get(
            id=family_id,
            organization=organization
        )
    except Family.DoesNotExist:
        return Response(
            {'error': 'Family not found or access denied'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    member_ids = request.data.get('member_ids', [])
    if not isinstance(member_ids, list):
        return Response(
            {'error': 'member_ids must be a list'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get members that belong to the same organization and this family
    members = Member.objects.filter(
        id__in=member_ids,
        organization=organization,
        family=family
    )
    
    # Remove family from each member
    for member in members:
        member.family = None
        member.save()
    
    return Response({
        'success': True,
        'message': f'Removed {len(members)} members from {family.family_name}',
        'removed_count': len(members),
        'family': FamilySerializer(family, context={'request': request}).data
    })
# In your church/views.py


# inventory/views.py (UPDATED)
@login_required
@require_http_methods(["GET", "POST"])
def inventory_item_edit_view(request, item_id):
    """Edit inventory item - handles both form POST and JSON POST"""
    organization = get_user_organization(request.user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")
    
    try:
        item = InventoryItem.objects.get(id=item_id, organization=organization)
    except InventoryItem.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Item not found'}, status=404)
        return HttpResponseNotFound("Item not found")
    
    # Check permissions
    user = request.user
    can_manage = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False) or
        getattr(user, "is_hod", False)
    )
    
    if not can_manage:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Permission denied'}, status=403)
        return HttpResponseForbidden("Permission denied")
    
    if request.method == 'POST':
        is_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
        
        if is_json:
            data = json.loads(request.body)
        else:
            data = request.POST.copy()
            if 'image' in request.FILES:
                data['image'] = request.FILES['image']
            if 'clear_image' in request.POST:
                data['clear_image'] = True
        
        # Validate required fields
        errors = {}
        if not data.get('name', '').strip():
            errors['name'] = 'Item name is required'
        
        # Validate numeric fields
        numeric_fields = ['quantity', 'reorder_level', 'reorder_quantity']
        for field in numeric_fields:
            if field in data and data[field]:
                try:
                    value = int(data[field])
                    if value < 0:
                        errors[field] = f'{field.replace("_", " ").title()} cannot be negative'
                except ValueError:
                    errors[field] = f'{field.replace("_", " ").title()} must be a number'
        
        # Validate price
        if 'purchase_price' in data and data['purchase_price']:
            try:
                price = float(data['purchase_price'])
                if price < 0:
                    errors['purchase_price'] = 'Price cannot be negative'
            except ValueError:
                errors['purchase_price'] = 'Price must be a number'
        
        if errors:
            if is_json:
                return JsonResponse({'errors': errors}, status=400)
            # For web, re-render form with errors
            categories = InventoryCategory.objects.filter(organization=organization)
            departments = Department.objects.filter(organization=organization)
            vendors = InventoryVendor.objects.filter(organization=organization)
            
            return render(request, 'inventory/items/edit.html', {
                'item': item,
                'errors': errors,
                'data': data,
                'categories': categories,
                'departments': departments,
                'vendors': vendors,
                'item_type_choices': InventoryItem.ITEM_TYPES,
                'condition_choices': InventoryItem.CONDITION_CHOICES,
            })
        
        try:
            # Track if quantity changed for transaction
            old_quantity = item.quantity
            
            # Update item fields
            item.name = data.get('name', item.name)
            item.description = data.get('description', item.description)
            item.sku = data.get('sku', item.sku)
            item.barcode = data.get('barcode', item.barcode)
            item.asset_tag = data.get('asset_tag', item.asset_tag)
            
            # Update quantities
            new_quantity = int(data.get('quantity', item.quantity))
            item.reorder_level = int(data.get('reorder_level', item.reorder_level))
            item.reorder_quantity = int(data.get('reorder_quantity', item.reorder_quantity))
            item.alert_on_low = bool(data.get('alert_on_low', item.alert_on_low))
            
            item.location = data.get('location', item.location)
            item.condition = data.get('condition', item.condition)
            item.item_type = data.get('item_type', item.item_type)
            item.storage_instructions = data.get('storage_instructions', item.storage_instructions)
            
            # Handle price
            purchase_price = data.get('purchase_price')
            if purchase_price is not None:
                if purchase_price == '':
                    item.purchase_price = None
                else:
                    item.purchase_price = float(purchase_price)
            
            item.notes = data.get('notes', item.notes)
            
            # Handle relationships
            category_id = data.get('category')
            if category_id:
                try:
                    category = InventoryCategory.objects.get(id=category_id, organization=organization)
                    item.category = category
                except InventoryCategory.DoesNotExist:
                    pass
            elif category_id == '':
                item.category = None
            
            department_id = data.get('department')
            if department_id:
                try:
                    department = Department.objects.get(id=department_id, organization=organization)
                    item.department = department
                except Department.DoesNotExist:
                    pass
            elif department_id == '':
                item.department = None
            
            vendor_id = data.get('vendor')
            if vendor_id:
                try:
                    vendor = InventoryVendor.objects.get(id=vendor_id, organization=organization)
                    item.vendor = vendor
                except InventoryVendor.DoesNotExist:
                    pass
            elif vendor_id == '':
                item.vendor = None
            
            # Handle dates
            purchase_date = data.get('purchase_date')
            if purchase_date:
                try:
                    item.purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif purchase_date == '':
                item.purchase_date = None
            
            warranty_expiry = data.get('warranty_expiry')
            if warranty_expiry:
                try:
                    item.warranty_expiry = datetime.strptime(warranty_expiry, '%Y-%m-%d').date()
                except ValueError:
                    pass
            elif warranty_expiry == '':
                item.warranty_expiry = None
            
            # Handle image (for form submissions)
            if not is_json:
                if 'image' in request.FILES:
                    item.image = request.FILES['image']
                elif 'clear_image' in data:
                    item.image = None
            
            # Check if quantity changed
            if new_quantity != old_quantity:
                # Create adjustment transaction
                quantity_diff = new_quantity - old_quantity
                transaction_type = 'add' if quantity_diff > 0 else 'remove'
                
                InventoryTransaction.objects.create(
                    organization=organization,
                    item=item,
                    transaction_type=transaction_type,
                    quantity=abs(quantity_diff),
                    performed_by=request.user,
                    notes=f'Manual adjustment from {old_quantity} to {new_quantity}',
                    approved_by=request.user,
                    approved_at=timezone.now(),
                )
            
            item.quantity = new_quantity
            item.save()
            
            if is_json:
                return JsonResponse({
                    'success': True,
                    'message': 'Item updated successfully',
                    'item': {
                        'id': str(item.id),
                        'name': item.name,
                        'quantity': item.quantity,
                        'status': item.status,
                    }
                })
            
            # For web, redirect with success message
            messages.success(request, 'Item updated successfully')
            return redirect('inventory_item_detail', item_id=item.id)
            
        except Exception as e:
            if is_json:
                return JsonResponse({'error': str(e)}, status=500)
            
            messages.error(request, f'Error updating item: {str(e)}')
            categories = InventoryCategory.objects.filter(organization=organization)
            departments = Department.objects.filter(organization=organization)
            vendors = InventoryVendor.objects.filter(organization=organization)
            
            return render(request, 'inventory/items/edit.html', {
                'item': item,
                'data': data,
                'categories': categories,
                'departments': departments,
                'vendors': vendors,
                'item_type_choices': InventoryItem.ITEM_TYPES,
                'condition_choices': InventoryItem.CONDITION_CHOICES,
            })
    
    # GET request - show edit form
    categories = InventoryCategory.objects.filter(organization=organization)
    departments = Department.objects.filter(organization=organization)
    vendors = InventoryVendor.objects.filter(organization=organization)
    
    context = {
        'item': item,
        'categories': categories,
        'departments': departments,
        'vendors': vendors,
        'item_type_choices': InventoryItem.ITEM_TYPES,
        'condition_choices': InventoryItem.CONDITION_CHOICES,
    }
    
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return current item data for mobile app
        return JsonResponse({
            'id': str(item.id),
            'name': item.name,
            'description': item.description,
            'sku': item.sku,
            'barcode': item.barcode,
            'asset_tag': item.asset_tag,
            'quantity': item.quantity,
            'reorder_level': item.reorder_level,
            'reorder_quantity': item.reorder_quantity,
            'alert_on_low': item.alert_on_low,
            'location': item.location,
            'condition': item.condition,
            'item_type': item.item_type,
            'storage_instructions': item.storage_instructions,
            'purchase_price': float(item.purchase_price) if item.purchase_price else None,
            'notes': item.notes,
            'category': str(item.category.id) if item.category else None,
            'department': str(item.department.id) if item.department else None,
            'vendor': str(item.vendor.id) if item.vendor else None,
            'purchase_date': item.purchase_date.isoformat() if item.purchase_date else None,
            'warranty_expiry': item.warranty_expiry.isoformat() if item.warranty_expiry else None,
            'image_url': request.build_absolute_uri(item.image.url) if item.image else None,
        })
    
    return render(request, 'inventory/items/edit.html', context)


@login_required
@require_http_methods(["GET", "POST", "DELETE"])
def inventory_item_delete_view(request, item_id):
    """Delete inventory item - handles DELETE for mobile and POST for web"""
    organization = get_user_organization(request.user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")
    
    try:
        item = InventoryItem.objects.get(id=item_id, organization=organization)
    except InventoryItem.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Item not found'}, status=404)
        return HttpResponseNotFound("Item not found")
    
    # Check permissions
    user = request.user
    can_manage = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False)
    )
    
    if not can_manage:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Permission denied'}, status=403)
        return HttpResponseForbidden("Permission denied")
    
    # Check if item has active checkouts
    active_checkouts = InventoryCheckout.objects.filter(
        item=item,
        status__in=['active', 'overdue']
    ).exists()
    
    if active_checkouts:
        message = f"Cannot delete '{item.name}' because it has active checkouts. Please return all items first."
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': message}, status=400)
        messages.error(request, message)
        return redirect('inventory_item_detail', item_id=item.id)
    
    # Handle DELETE request (for mobile API)
    if request.method == 'DELETE' or request.headers.get("x-requested-with") == "XMLHttpRequest":
        item_name = item.name
        item_sku = item.sku
        item.delete()
        
        return JsonResponse({
            'success': True,
            'message': f"Item '{item_name}' has been deleted.",
            'deleted_item': {
                'id': item_id,
                'name': item_name,
                'sku': item_sku,
            }
        })
    
    # Handle POST request (for web form submission)
    if request.method == 'POST':
        item_name = item.name
        item.delete()
        
        messages.success(request, f"Item '{item_name}' has been deleted.")
        return redirect('inventory_item_list')
    
    # GET request - show confirmation page (for web)
    return render(request, 'inventory/items/delete_confirm.html', {
        'item': item,
    })


# Add these imports at the top of your views.py
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import base64
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.core.files.base import ContentFile
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
