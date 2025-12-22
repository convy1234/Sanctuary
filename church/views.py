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




from django.db.models import Q  # ADD THIS IMPORT
from .models import  Member,Organization,Campus,Department,Family 

# In church/views.py - ADD THESE HYBRID VIEWS USING YOUR EXISTING PATTERN
@login_required
def member_list_view(request):
    """List members - JSON for mobile, HTML for web (same as dashboard_view)."""
    user = request.user
    organization = get_user_organization(request.user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")
    
    # Get query parameters
    status_filter = request.GET.get('status')
    search = request.GET.get('search', '')
    
    # Build queryset (same logic for both)
    members = Member.objects.filter(organization=organization)
    
    if status_filter:
        members = members.filter(status=status_filter)
    
    if search:
        members = members.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )
    
    # Check if it's an API/mobile request (YOUR EXISTING PATTERN)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return JSON for mobile (like your dashboard_view does)
        data = [
            {
                'id': str(m.id),
                'full_name': f"{m.first_name} {m.last_name}",
                'first_name': m.first_name,
                'last_name': m.last_name,
                'email': m.email,
                'phone': str(m.phone) if m.phone else '',
                'status': m.status,
                'join_date': m.join_date.isoformat() if m.join_date else None,
                'photo_url': request.build_absolute_uri(m.photo.url) if m.photo else None,
            }
            for m in members
        ]
        return JsonResponse({'members': data})
    
    # Return HTML for web (like your dashboard_view does)
    return render(request, 'members/list.html', {'members': members})

@login_required
def member_detail_view(request, member_id):
    """Single member - JSON for mobile, HTML for web."""
    try:
        member = Member.objects.get(id=member_id, organization=request.user.organization)
    except Member.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Member not found'}, status=404)
        return HttpResponseNotFound("Member not found")
    
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return JSON for mobile
        data = {
            'id': str(member.id),
            'full_name': f"{member.first_name} {member.last_name}",
            'first_name': member.first_name,
            'last_name': member.last_name,
            'gender': member.gender,
            'date_of_birth': member.date_of_birth.isoformat() if member.date_of_birth else None,
            'email': member.email,
            'phone': str(member.phone) if member.phone else '',
            'status': member.status,
            'marital_status': member.marital_status,
            'occupation': member.occupation,
            'address': member.address,
            # ... include all fields you need
        }
        return JsonResponse(data)
    
    # Return HTML for web
    return render(request, 'members/detail.html', {'member': member})

@login_required
@require_http_methods(["GET", "POST"])
def member_create_view(request):
    """Create member - handles both form POST and JSON POST."""
    if request.method == 'POST':
        # Get data based on content type
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            import json
            data = json.loads(request.body)
            is_json = True
        else:
            data = request.POST
            is_json = False
        
        # Validation logic (same for both)
        errors = {}
        if not data.get('first_name'):
            errors['first_name'] = 'First name is required'
        if not data.get('last_name'):
            errors['last_name'] = 'Last name is required'
        
        if errors:
            if is_json:
                return JsonResponse({'errors': errors}, status=400)
            return render(request, 'members/create.html', {'errors': errors, 'data': data})
        
        # Create member (same logic)
        member = Member.objects.create(
            first_name=data['first_name'],
            last_name=data['last_name'],
            organization=request.user.organization,
            email=data.get('email', ''),
            phone=data.get('phone', ''),
            status=data.get('status', 'new'),
            created_by=request.user,
        )
        
        if is_json:
            return JsonResponse({
                'success': True,
                'member_id': str(member.id),
                'message': 'Member created successfully'
            })
        return redirect('member_detail', member_id=member.id)
    
    # GET request - show form
    return render(request, 'members/create.html')

@login_required
@require_http_methods(["GET", "POST", "PUT"])
def member_edit_view(request, member_id):
    """Edit member - handles both form POST and JSON PUT."""
    try:
        member = Member.objects.get(id=member_id, organization=request.user.organization)
    except Member.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Member not found'}, status=404)
        return HttpResponseNotFound("Member not found")
    
    # Check permissions (admin/pastor/owner can edit)
    user = request.user
    can_edit = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False)
    )
    
    if not can_edit:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Permission denied'}, status=403)
        return HttpResponseForbidden("Permission denied")
    
    if request.method in ['POST', 'PUT']:
        # Get data based on content type
        is_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
        
        if is_json:
            import json
            data = json.loads(request.body)
        else:
            data = request.POST
        
        # Validation logic (same for both)
        errors = {}
        
        # Required fields
        if not data.get('first_name', '').strip():
            errors['first_name'] = 'First name is required'
        if not data.get('last_name', '').strip():
            errors['last_name'] = 'Last name is required'
        
        # Email uniqueness check (within organization)
        email = data.get('email', '').strip()
        if email:
            existing = Member.objects.filter(
                organization=request.user.organization,
                email=email
            ).exclude(id=member_id).first()
            if existing:
                errors['email'] = 'Email already exists in this organization'
        
        # Phone uniqueness check
        phone = data.get('phone', '').strip()
        if phone:
            existing = Member.objects.filter(
                organization=request.user.organization,
                phone=phone
            ).exclude(id=member_id).first()
            if existing:
                errors['phone'] = 'Phone number already exists in this organization'
        
        if errors:
            if is_json:
                return JsonResponse({'errors': errors}, status=400)
            return render(request, 'members/edit.html', {
                'member': member,
                'errors': errors,
                'data': data
            })
        
        # Update member fields
        member.first_name = data.get('first_name', member.first_name)
        member.last_name = data.get('last_name', member.last_name)
        member.gender = data.get('gender', member.gender)
        
        # Date fields
        dob = data.get('date_of_birth')
        if dob:
            try:
                member.date_of_birth = datetime.strptime(dob, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        join_date = data.get('join_date')
        if join_date:
            try:
                member.join_date = datetime.strptime(join_date, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # Contact info
        member.email = data.get('email', member.email)
        member.phone = data.get('phone', member.phone)
        
        # Status and info
        member.status = data.get('status', member.status)
        member.marital_status = data.get('marital_status', member.marital_status)
        member.occupation = data.get('occupation', member.occupation)
        member.blood_type = data.get('blood_type', member.blood_type)
        
        # Address
        member.address = data.get('address', member.address)
        member.residential_country = data.get('residential_country', member.residential_country)
        member.residential_state = data.get('residential_state', member.residential_state)
        member.residential_city = data.get('residential_city', member.residential_city)
        member.origin_country = data.get('origin_country', member.origin_country)
        member.origin_state = data.get('origin_state', member.origin_state)
        member.origin_city = data.get('origin_city', member.origin_city)
        
        # Emergency contact
        member.next_of_kin_name = data.get('next_of_kin_name', member.next_of_kin_name)
        member.next_of_kin_phone = data.get('next_of_kin_phone', member.next_of_kin_phone)
        member.next_of_kin_relationship = data.get('next_of_kin_relationship', member.next_of_kin_relationship)
        
        # Spiritual info
        member.baptism_status = data.get('baptism_status', member.baptism_status)
        baptism_date = data.get('baptism_date')
        if baptism_date:
            try:
                member.baptism_date = datetime.strptime(baptism_date, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # Notes
        member.notes = data.get('notes', member.notes)
        
        # Handle photo upload (for form submissions)
        if not is_json and 'photo' in request.FILES:
            member.photo = request.FILES['photo']
        
        # Handle campus assignment
        campus_id = data.get('campus')
        if campus_id:
            try:
                campus = Campus.objects.get(id=campus_id, organization=request.user.organization)
                member.campus = campus
            except Campus.DoesNotExist:
                pass
        
        # Handle family assignment
        family_id = data.get('family')
        if family_id:
            try:
                family = Family.objects.get(id=family_id, organization=request.user.organization)
                member.family = family
                member.family_role = data.get('family_role', member.family_role)
            except Family.DoesNotExist:
                pass
        
        # Handle spouse assignment
        spouse_id = data.get('spouse')
        if spouse_id:
            try:
                spouse = Member.objects.get(id=spouse_id, organization=request.user.organization)
                # Clear previous spouse relationship
                if member.spouse:
                    old_spouse = member.spouse
                    old_spouse.spouse = None
                    old_spouse.save()
                # Set new spouse relationship (bidirectional)
                member.spouse = spouse
                spouse.spouse = member
                spouse.save()
            except Member.DoesNotExist:
                pass
        elif data.get('spouse') == '':  # Empty string means remove spouse
            if member.spouse:
                old_spouse = member.spouse
                old_spouse.spouse = None
                old_spouse.save()
                member.spouse = None
        
        member.save()
        
        # Handle departments (ManyToMany)
        department_ids = data.get('departments', [])
        if isinstance(department_ids, str):
            department_ids = [id.strip() for id in department_ids.split(',') if id.strip()]
        
        if department_ids:
            departments = Department.objects.filter(
                id__in=department_ids,
                organization=request.user.organization
            )
            member.departments.set(departments)
        
        # Success response
        if is_json:
            return JsonResponse({
                'success': True,
                'message': 'Member updated successfully',
                'member_id': str(member.id),
                'member': {
                    'id': str(member.id),
                    'full_name': member.full_name,
                    'email': member.email,
                    'status': member.status,
                }
            })
        
        # For web, redirect to detail page with success message
        messages.success(request, 'Member updated successfully')
        return redirect('member_detail', member_id=member.id)
    
    # GET request - show edit form with current data
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return current member data for mobile app
        return JsonResponse({
            'id': str(member.id),
            'first_name': member.first_name,
            'last_name': member.last_name,
            'gender': member.gender,
            'date_of_birth': member.date_of_birth.isoformat() if member.date_of_birth else None,
            'email': member.email,
            'phone': str(member.phone) if member.phone else '',
            'status': member.status,
            'marital_status': member.marital_status,
            'occupation': member.occupation,
            'blood_type': member.blood_type,
            'address': member.address,
            'residential_country': member.residential_country,
            'residential_state': member.residential_state,
            'residential_city': member.residential_city,
            'origin_country': member.origin_country,
            'origin_state': member.origin_state,
            'origin_city': member.origin_city,
            'next_of_kin_name': member.next_of_kin_name,
            'next_of_kin_phone': str(member.next_of_kin_phone) if member.next_of_kin_phone else '',
            'next_of_kin_relationship': member.next_of_kin_relationship,
            'baptism_status': member.baptism_status,
            'baptism_date': member.baptism_date.isoformat() if member.baptism_date else None,
            'join_date': member.join_date.isoformat() if member.join_date else None,
            'notes': member.notes,
            'campus': str(member.campus.id) if member.campus else None,
            'family': str(member.family.id) if member.family else None,
            'family_role': member.family_role,
            'spouse': str(member.spouse.id) if member.spouse else None,
            'departments': [str(dept.id) for dept in member.departments.all()],
            'photo_url': request.build_absolute_uri(member.photo.url) if member.photo else None,
        })
    
    # For web, show edit form
    # Get related data for dropdowns
    campuses = Campus.objects.filter(organization=request.user.organization)
    families = Family.objects.filter(organization=request.user.organization)
    departments = Department.objects.filter(organization=request.user.organization)
    other_members = Member.objects.filter(
        organization=request.user.organization
    ).exclude(id=member.id)
    
    return render(request, 'members/edit.html', {
        'member': member,
        'campuses': campuses,
        'families': families,
        'departments': departments,
        'other_members': other_members,
        'status_choices': Member.STATUS_CHOICES,
        'gender_choices': Member.GENDER_CHOICES,
        'marital_status_choices': Member.MARITAL_STATUS_CHOICES,
        'blood_type_choices': Member.BLOOD_TYPE_CHOICES,
        'baptism_status_choices': Member.BAPTISM_STATUS_CHOICES,
        'family_role_choices': Member.FAMILY_ROLE_CHOICES,
    })


@login_required
def member_statistics_view(request):
    """Member statistics - JSON for mobile, HTML for web."""
    user = request.user
    organization = get_user_organization(request.user)


    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")
    
    # Calculate statistics (same logic for both)
    stats = {
        'total_members': Member.objects.filter(organization=organization).count(),
        'active_members': Member.objects.filter(organization=organization, status='active').count(),
        'new_members': Member.objects.filter(organization=organization, status='new').count(),
        'inactive_members': Member.objects.filter(organization=organization, status='inactive').count(),
        'visitor_count': Member.objects.filter(organization=organization, status='visitor').count(),
        'families': Family.objects.filter(organization=organization).count(),
        'departments': Department.objects.filter(organization=organization).count(),
        'campuses': Campus.objects.filter(organization=organization).count(),
    }
    
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(stats)
    
    return render(request, 'members/statistics.html', {'stats': stats, 'organization': organization})


    



from django.views.decorators.http import require_http_methods
from django.contrib import messages

@login_required
@require_http_methods(["DELETE", "POST", "GET"])
def member_delete_view(request, member_id):
    """
    Delete member - handles DELETE for mobile API and POST for web forms.
    GET shows confirmation page for web.
    """
    try:
        member = Member.objects.get(id=member_id, organization=request.user.organization)
    except Member.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Member not found'}, status=404)
        return HttpResponseNotFound("Member not found")
    
    # Check permissions (admin/pastor/owner can delete)
    user = request.user
    can_delete = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False)
    )
    
    if not can_delete:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Permission denied'}, status=403)
        return HttpResponseForbidden("Permission denied")
    
    # Handle actual deletion
    if request.method in ['DELETE', 'POST']:
        # Check if this is a soft delete request
        soft_delete = request.POST.get('soft_delete', False) or (
            request.headers.get("x-requested-with") == "XMLHttpRequest" and 
            request.GET.get('soft_delete', 'false').lower() == 'true'
        )
        
        # Store member info for response/messages
        member_name = member.full_name
        member_email = member.email
        
        if soft_delete:
            # Soft delete: change status to inactive instead of deleting
            member.status = 'inactive'
            member.save()
            
            message = f"Member '{member_name}' has been deactivated."
            success_message = "Member deactivated successfully"
        else:
            # Hard delete: actually delete from database
            member.delete()
            message = f"Member '{member_name}' has been permanently deleted."
            success_message = "Member deleted successfully"
        
        # YOUR EXISTING PATTERN
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                'success': True,
                'message': message,
                'soft_delete': soft_delete,
                'deleted_member': {
                    'id': str(member.id) if soft_delete else member_id,
                    'name': member_name,
                    'email': member_email,
                }
            })
        
        # For web, redirect to member list with success message
        messages.success(request, success_message)
        return redirect('member_list')
    
    # GET request: show confirmation page
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return member info for mobile app confirmation
        return JsonResponse({
            'member': {
                'id': str(member.id),
                'full_name': member.full_name,
                'email': member.email,
                'status': member.status,
                'join_date': member.join_date.isoformat() if member.join_date else None,
                'member_since': member.created_at.strftime('%Y-%m-%d'),
            },
            'warning': 'This action cannot be undone for hard delete.',
            'soft_delete_note': 'Soft delete will change status to inactive instead of deleting.'
        })
    
    # For web, show delete confirmation page
    return render(request, 'members/delete_confirm.html', {
        'member': member,
    })





































# mobileviews

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

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def member_list_api_view(request):
    """API endpoint for listing members with filtering and search."""
    user = request.user
    organization = get_user_organization(user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get query parameters
    status_filter = request.query_params.get('status')
    search = request.query_params.get('search', '')
    campus = request.query_params.get('campus')
    department = request.query_params.get('department')
    
    # Build queryset
    members = Member.objects.filter(organization=organization)
    
    # Apply filters
    if status_filter:
        members = members.filter(status=status_filter)
    
    if campus:
        members = members.filter(campus_id=campus)
    
    if department:
        members = members.filter(departments__id=department)
    
    if search:
        members = members.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )
    
    # Order by name
    members = members.order_by('last_name', 'first_name')
    
    # Paginate (optional)
    page_size = request.query_params.get('page_size', 50)
    page_number = request.query_params.get('page', 1)
    
    try:
        from django.core.paginator import Paginator
        paginator = Paginator(members, page_size)
        page_obj = paginator.get_page(page_number)
        
        serializer = MemberSerializer(page_obj, many=True, context={'request': request})
        
        return Response({
            'count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'next': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'members': serializer.data
        })
    except:
        # If pagination fails, return all
        serializer = MemberSerializer(members, many=True, context={'request': request})
        return Response({
            'count': members.count(),
            'members': serializer.data
        })

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def member_detail_api_view(request, member_id):
    """API endpoint for single member details."""
    try:
        organization = get_user_organization(request.user)
        if not organization:
            return Response(
                {'error': 'No organization assigned'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        member = Member.objects.get(id=member_id, organization=organization)
        serializer = MemberSerializer(member, context={'request': request})
        return Response(serializer.data)
        
    except Member.DoesNotExist:
        return Response(
            {'error': 'Member not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

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
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def member_create_api_view(request):
    
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
    
    # Prepare the data
    data = request.data.copy()
    
    # Add organization ID
    data['organization'] = str(organization.id)
    
    # Format date fields
    date_fields = ['date_of_birth', 'join_date', 'baptism_date']
    for field in date_fields:
        if field in data and data[field]:
            formatted_date = format_date_for_model(data[field])
            if formatted_date:
                data[field] = formatted_date
            else:
                # Remove invalid dates
                data[field] = None
        elif field in data and data[field] == '':
            data[field] = None  # ✅ Dates can be null
    
    # Handle phone numbers - clean them but keep empty strings
    phone_fields = ['phone', 'next_of_kin_phone']
    for field in phone_fields:
        if field in data and data[field]:
            # Remove non-numeric characters
            phone = ''.join(filter(str.isdigit, str(data[field])))
            if phone:
                data[field] = phone
            else:
                data[field] = ''  # ✅ Empty string, not None
        elif field in data and data[field] == '':
            data[field] = ''  # ✅ Keep empty string
    
    # ✅ DO NOT convert empty strings to None for these fields
    # The frontend is sending empty strings, keep them as empty strings
    # Database has NOT NULL constraints, so it needs empty strings, not null
    
    # Log the data for debugging
    print(f"📝 Creating member with data: {data}")
    print(f"📝 Notes field: '{data.get('notes')}' (should be empty string, not None)")
    
    serializer = MemberSerializer(data=data, context={'request': request})
    
    if serializer.is_valid():
        member = serializer.save(created_by=request.user)
        return Response(
            {
                'success': True,
                'message': 'Member created successfully',
                'member_id': str(member.id),
                'member': MemberSerializer(member, context={'request': request}).data
            },
            status=status.HTTP_201_CREATED
        )
    
    # Return detailed validation errors
    errors = {}
    for field, error_list in serializer.errors.items():
        if isinstance(error_list, list):
            errors[field] = error_list[0] if error_list else "Invalid value"
        else:
            errors[field] = str(error_list)
    
    return Response(
        {
            'success': False,
            'message': 'Validation failed',
            'errors': errors
        },
        status=status.HTTP_400_BAD_REQUEST
    )

@api_view(['PUT', 'PATCH'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def member_update_api_view(request, member_id):
    """API endpoint for updating a member."""
    try:
        organization = get_user_organization(request.user)
        if not organization:
            return Response(
                {'error': 'No organization assigned'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        member = Member.objects.get(id=member_id, organization=organization)
        
        # Check permissions
        user = request.user
        can_edit = (
            user.is_staff or 
            getattr(user, "is_owner", False) or 
            getattr(user, "is_admin", False) or 
            getattr(user, "is_pastor", False)
        )
        
        if not can_edit:
            return Response(
                {'error': 'Permission denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Prepare the data
        data = request.data.copy()
        
        # ✅ Add organization ID (required field)
        data['organization'] = str(organization.id)
        
        # ✅ Format date fields
        date_fields = ['date_of_birth', 'join_date', 'baptism_date']
        for field in date_fields:
            if field in data and data[field]:
                formatted_date = format_date_for_model(data[field])
                if formatted_date:
                    data[field] = formatted_date
                else:
                    data[field] = None
            elif field in data and data[field] == '':
                data[field] = None  # Dates can be null
        
        # ✅ Handle phone numbers - clean them but keep empty strings
        phone_fields = ['phone', 'next_of_kin_phone']
        for field in phone_fields:
            if field in data and data[field]:
                # Remove non-numeric characters
                phone = ''.join(filter(str.isdigit, str(data[field])))
                if phone:
                    data[field] = phone
                else:
                    data[field] = ''  # Empty string, not None
            elif field in data and data[field] == '':
                data[field] = ''  # Keep empty string
        
        # ✅ DO NOT convert empty strings to None for string fields
        # List of fields that should keep empty strings
        string_fields = [
            'email', 'gender', 'marital_status', 'occupation', 'address',
            'residential_city', 'residential_state', 'residential_country',
            'origin_city', 'origin_state', 'origin_country', 'blood_type',
            'next_of_kin_name', 'next_of_kin_relationship', 'baptism_status',
            'notes', 'family_role'
        ]
        
        for field in string_fields:
            if field in data and data[field] == '':
                data[field] = ''  # Keep empty string
        
        # ✅ Relationship fields - handle empty strings
        relationship_fields = ['campus', 'family']
        for field in relationship_fields:
            if field in data and data[field] == '':
                data[field] = None  # Foreign keys can be null
        
        # Log for debugging
        print(f"📝 Updating member {member_id} with data: {data}")
        
        # Use partial=True for PATCH requests
        is_partial = request.method == 'PATCH'
        serializer = MemberSerializer(
            member, 
            data=data, 
            partial=is_partial,
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Member updated successfully',
                'member': serializer.data
            })
        
        # Return detailed validation errors
        print(f"❌ Serializer errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    except Member.DoesNotExist:
        return Response(
            {'error': 'Member not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def member_delete_api_view(request, member_id):
    """API endpoint for deleting a member."""
    try:
        organization = get_user_organization(request.user)
        if not organization:
            return Response(
                {'error': 'No organization assigned'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        member = Member.objects.get(id=member_id, organization=organization)
        
        # Check permissions
        user = request.user
        can_delete = (
            user.is_staff or 
            getattr(user, "is_owner", False) or 
            getattr(user, "is_admin", False) or 
            getattr(user, "is_pastor", False)
        )
        
        if not can_delete:
            return Response(
                {'error': 'Permission denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if soft delete requested
        soft_delete = request.query_params.get('soft_delete', 'false').lower() == 'true'
        
        member_name = member.full_name
        
        if soft_delete:
            # Soft delete: change status to inactive
            member.status = 'inactive'
            member.save()
            
            return Response({
                'success': True,
                'message': f"Member '{member_name}' has been deactivated.",
                'soft_delete': True,
                'deleted_member': {
                    'id': str(member.id),
                    'name': member_name,
                    'email': member.email,
                }
            })
        else:
            # Hard delete
            member.delete()
            return Response({
                'success': True,
                'message': f"Member '{member_name}' has been permanently deleted.",
                'soft_delete': False,
                'deleted_member': {
                    'id': member_id,
                    'name': member_name,
                    'email': member.email,
                }
            })
        
    except Member.DoesNotExist:
        return Response(
            {'error': 'Member not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def member_statistics_api_view(request):
    """API endpoint for member statistics."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Calculate statistics
    stats = {
        'total_members': Member.objects.filter(organization=organization).count(),
        'active_members': Member.objects.filter(organization=organization, status='active').count(),
        'new_members': Member.objects.filter(organization=organization, status='new').count(),
        'inactive_members': Member.objects.filter(organization=organization, status='inactive').count(),
        'visitor_count': Member.objects.filter(organization=organization, status='visitor').count(),
        'transferred_count': Member.objects.filter(organization=organization, status='transferred').count(),
        'deceased_count': Member.objects.filter(organization=organization, status='deceased').count(),
        'families': Family.objects.filter(organization=organization).count(),
        'departments': Department.objects.filter(organization=organization).count(),
        'campuses': Campus.objects.filter(organization=organization).count(),
    }
    
    return Response(stats)

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


# church/views.py - Add these API views


# Add to your church/views.py

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
from django.db.models import Q, Sum, Count
from django.contrib import messages
from django.core.paginator import Paginator
import json
from datetime import datetime
from .models import VoucherTemplate
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden


# Add to your imports at the top
from .models import Voucher, VoucherAttachment, VoucherComment

# Helper function to get user's organization
def get_user_organization(user):
    if hasattr(user, 'organization') and user.organization:
        return user.organization
    # fallback if user belongs via profile or membership
    if hasattr(user, 'profile') and hasattr(user.profile, 'organization'):
        return user.profile.organization
    return None




def get_voucher_template(organization):
    """Get the default template for an organization."""
    try:
        return VoucherTemplate.objects.get(organization=organization, is_default=True)
    except VoucherTemplate.DoesNotExist:
        try:
            return VoucherTemplate.objects.filter(organization=organization).first()
        except VoucherTemplate.DoesNotExist:
            # Create a default template if none exists
            return VoucherTemplate.objects.create(
                organization=organization,
                name="Default Voucher Template",
                is_default=True,
                created_by=request.user
            )


# ==================== VOUCHER LIST VIEW ====================
@login_required
def voucher_list_view(request):
    """List vouchers - JSON for mobile, HTML for web."""
    user = request.user
    organization = get_user_organization(user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")
    
    # Get query parameters
    status_filter = request.GET.get('status')
    search = request.GET.get('search', '')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    voucher_type = request.GET.get('type')
    
    # Build queryset
    vouchers = Voucher.objects.filter(organization=organization)
    
    # Apply filters
    if status_filter:
        vouchers = vouchers.filter(status=status_filter)
    
    if search:
        vouchers = vouchers.filter(
            Q(voucher_number__icontains=search) |
            Q(purpose__icontains=search) |
            Q(requested_by__email__icontains=search) |
            Q(requested_by__first_name__icontains=search) |
            Q(requested_by__last_name__icontains=search) |
            Q(payable_to__icontains=search)
        )
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            vouchers = vouchers.filter(date_prepared__gte=start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            vouchers = vouchers.filter(date_prepared__lte=end)
        except ValueError:
            pass
    
    # Order by date prepared (most recent first)
    vouchers = vouchers.order_by('-date_prepared', '-created_at')
    
    # YOUR EXISTING PATTERN - Check for AJAX/mobile request
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return JSON for mobile
        data = [
            {
                'id': str(v.id),
                'voucher_number': v.voucher_number,
                'title': v.title,
                'purpose': v.purpose[:100] + '...' if len(v.purpose) > 100 else v.purpose,
                'requester_name': v.requester_name_department,
                'amount_in_figures': float(v.amount_in_figures) if v.amount_in_figures else 0,
                'currency': v.currency,
                'status': v.status,
                'status_display': v.get_status_display(),
                'date_prepared': v.date_prepared.isoformat() if v.date_prepared else None,
                'needed_by': v.needed_by.isoformat() if v.needed_by else None,
                'approved_amount': float(v.approved_amount) if v.approved_amount else None,
                'paid_amount': float(v.paid_amount) if v.paid_amount else None,
                'is_overdue': v.is_overdue,
                'days_open': v.days_open,
            }
            for v in vouchers
        ]
        return JsonResponse({'vouchers': data})
    
    # Return HTML for web
    # Add pagination for web view
    paginator = Paginator(vouchers, 20)  # 20 items per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get summary statistics
    total_vouchers = vouchers.count()
    total_amount = vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or 0
    pending_vouchers = vouchers.filter(status__in=['draft', 'submitted']).count()
    
    context = {
        'vouchers': page_obj,
        'total_vouchers': total_vouchers,
        'total_amount': total_amount,
        'pending_vouchers': pending_vouchers,
        'status_filter': status_filter,
        'search': search,
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return render(request, 'vouchers/list.html', context)




@login_required
def voucher_template_list_view(request):
    """List all voucher templates for the organization."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return HttpResponseForbidden("No organization assigned")
    
    templates = VoucherTemplate.objects.filter(organization=organization).order_by('-is_default', '-created_at')
    
    context = {
        'templates': templates,
        'organization': organization,
    }
    return render(request, 'vouchers/template_list.html', context)

@login_required
@require_http_methods(["GET", "POST"])
def voucher_template_create_view(request):
    """Create a new voucher template."""
    organization = get_user_organization(request.user)
    
    if not organization:
        messages.error(request, "No organization assigned")
        return redirect('dashboard')
    
    if request.method == 'POST':
        # Get form data
        name = request.POST.get('name', '').strip()
        church_name = request.POST.get('church_name', organization.name).strip()
        church_motto = request.POST.get('church_motto', '').strip()
        form_title = request.POST.get('form_title', 'Funds Requisition Form').strip()
        description = request.POST.get('description', '').strip()
        warning_text = request.POST.get('warning_text', '').strip()
        is_default = request.POST.get('is_default') == 'true'
        
        # Section visibility
        show_urgent_items = request.POST.get('show_urgent_items') == 'on'
        show_important_items = request.POST.get('show_important_items') == 'on'
        show_permissible_items = request.POST.get('show_permissible_items') == 'on'
        
        # Labels
        signature_label = request.POST.get('signature_label', 'Department Leader Signature').strip()
        date_label = request.POST.get('date_label', 'Date').strip()
        phone_label = request.POST.get('phone_label', 'Phone Number').strip()
        
        # Default commitments
        default_usage_commitment = request.POST.get('default_usage_commitment', '').strip()
        default_maintenance_commitment = request.POST.get('default_maintenance_commitment', '').strip()
        
        # Validate
        errors = {}
        if not name:
            errors['name'] = 'Template name is required'
        
        if not errors:
            # Create template
            template = VoucherTemplate.objects.create(
                organization=organization,
                name=name,
                church_name=church_name,
                church_motto=church_motto,
                form_title=form_title,
                description=description,
                warning_text=warning_text,
                is_default=is_default,
                show_urgent_items=show_urgent_items,
                show_important_items=show_important_items,
                show_permissible_items=show_permissible_items,
                signature_label=signature_label,
                date_label=date_label,
                phone_label=phone_label,
                default_usage_commitment=default_usage_commitment,
                default_maintenance_commitment=default_maintenance_commitment,
                created_by=request.user
            )
            
            # Handle logo upload
            if 'logo' in request.FILES:
                template.logo = request.FILES['logo']
                template.save()
            
            # If this is set as default, unset others
            if is_default:
                VoucherTemplate.objects.filter(
                    organization=organization
                ).exclude(id=template.id).update(is_default=False)
            
            messages.success(request, f'Template "{name}" created successfully!')
            
            # Check if we should redirect to voucher creation
            redirect_to_voucher = request.POST.get('redirect_to_voucher') == 'true'
            if redirect_to_voucher:
                return redirect('voucher_create')
            else:
                return redirect('voucher_template_list')
        
        # If errors, show form again with submitted data
        context = {
            'errors': errors,
            'data': request.POST,  # This is what was missing
            'organization': organization,
            'default_church_name': organization.name,
        }
        return render(request, 'vouchers/template_form.html', context)
    
    # GET request - show form
    context = {
        'organization': organization,
        'default_church_name': organization.name,
        'data': {},  # Add empty data dict for GET requests
    }
    return render(request, 'vouchers/template_form.html', context)

@login_required
def voucher_template_edit_view(request, template_id):
    """Edit a voucher template."""
    template = get_object_or_404(VoucherTemplate, id=template_id, organization=request.user.organization)
    if request.method == 'POST':
        # Edit template logic
        pass
    return render(request, 'vouchers/template_form.html', {'template': template})

@login_required
def voucher_template_edit_view(request, template_id):
    """Edit an existing voucher template."""
    organization = get_user_organization(request.user)
    try:
        template = VoucherTemplate.objects.get(id=template_id, organization=organization)
    except VoucherTemplate.DoesNotExist:
        messages.error(request, "Template not found")
        return redirect('voucher_template_list')
    
    if request.method == 'POST':
        # Get form data
        name = request.POST.get('name', '').strip()
        church_name = request.POST.get('church_name', organization.name).strip()
        church_motto = request.POST.get('church_motto', '').strip()
        form_title = request.POST.get('form_title', 'Funds Requisition Form').strip()
        description = request.POST.get('description', '').strip()
        warning_text = request.POST.get('warning_text', '').strip()
        is_default = request.POST.get('is_default') == 'true'
        
        # Section visibility
        show_urgent_items = request.POST.get('show_urgent_items') == 'on'
        show_important_items = request.POST.get('show_important_items') == 'on'
        show_permissible_items = request.POST.get('show_permissible_items') == 'on'
        
        # Labels
        signature_label = request.POST.get('signature_label', 'Department Leader Signature').strip()
        date_label = request.POST.get('date_label', 'Date').strip()
        phone_label = request.POST.get('phone_label', 'Phone Number').strip()
        
        # Default commitments
        default_usage_commitment = request.POST.get('default_usage_commitment', '').strip()
        default_maintenance_commitment = request.POST.get('default_maintenance_commitment', '').strip()
        
        # Validate
        errors = {}
        if not name:
            errors['name'] = 'Template name is required'
        
        if not errors:
            # Update template fields
            template.name = name
            template.church_name = church_name
            template.church_motto = church_motto
            template.form_title = form_title
            template.description = description
            template.warning_text = warning_text
            template.is_default = is_default
            template.show_urgent_items = show_urgent_items
            template.show_important_items = show_important_items
            template.show_permissible_items = show_permissible_items
            template.signature_label = signature_label
            template.date_label = date_label
            template.phone_label = phone_label
            template.default_usage_commitment = default_usage_commitment
            template.default_maintenance_commitment = default_maintenance_commitment
            
            # Handle logo upload - only update if new file is provided
            if 'logo' in request.FILES:
                # New logo uploaded
                template.logo = request.FILES['logo']
            elif request.POST.get('clear_logo') == 'true':
                # Clear logo checkbox was checked
                template.logo = None
            
            template.save()
            
            # If this is set as default, unset others
            if is_default:
                VoucherTemplate.objects.filter(
                    organization=organization
                ).exclude(id=template.id).update(is_default=False)
            
            messages.success(request, f'Template "{name}" updated successfully!')
            return redirect('voucher_template_list')
        
        context = {
            'template': template,  # Keep template for edit mode
            'errors': errors,
            'data': request.POST,  # Pass POST data for re-population
            'organization': organization,
        }
        return render(request, 'vouchers/template_form.html', context)
    
    # GET request - show edit form with existing data
    # Prepare data from template instance
    data = {
        'name': template.name,
        'church_name': template.church_name,
        'church_motto': template.church_motto,
        'form_title': template.form_title,
        'description': template.description,
        'warning_text': template.warning_text,
        'is_default': 'true' if template.is_default else 'false',
        'show_urgent_items': 'on' if template.show_urgent_items else '',
        'show_important_items': 'on' if template.show_important_items else '',
        'show_permissible_items': 'on' if template.show_permissible_items else '',
        'signature_label': template.signature_label,
        'date_label': template.date_label,
        'phone_label': template.phone_label,
        'default_usage_commitment': template.default_usage_commitment,
        'default_maintenance_commitment': template.default_maintenance_commitment,
    }
    
    context = {
        'template': template,  # Pass template for edit mode detection AND logo access
        'organization': organization,
        'data': data,  # Pass data to populate form fields
    }
    return render(request, 'vouchers/template_form.html', context)


@login_required
def voucher_template_delete_view(request, template_id):
    """Delete a voucher template."""
    organization = get_user_organization(request.user)
    
    try:
        template = VoucherTemplate.objects.get(id=template_id, organization=organization)
    except VoucherTemplate.DoesNotExist:
        messages.error(request, "Template not found")
        return redirect('voucher_template_list')
    
    # Check if template is in use
    if template.vouchers.exists():
        messages.error(request, "Cannot delete template that is being used by vouchers")
        return redirect('voucher_template_list')
    
    if request.method == 'POST':
        template_name = template.name
        template.delete()
        messages.success(request, f'Template "{template_name}" deleted successfully')
        return redirect('voucher_template_list')
    
    return render(request, 'vouchers/template_confirm_delete.html', {
        'template': template,
        'organization': organization,
    })

@login_required
def voucher_template_duplicate_view(request, template_id):
    """Duplicate a voucher template."""
    organization = get_user_organization(request.user)
    
    try:
        original = VoucherTemplate.objects.get(id=template_id, organization=organization)
    except VoucherTemplate.DoesNotExist:
        messages.error(request, "Template not found")
        return redirect('voucher_template_list')
    
    # Create duplicate
    new_template = VoucherTemplate.objects.create(
        organization=original.organization,
        name=f"{original.name} (Copy)",
        church_name=original.church_name,
        church_motto=original.church_motto,
        form_title=original.form_title,
        description=original.description,
        warning_text=original.warning_text,
        logo=original.logo,
        show_urgent_items=original.show_urgent_items,
        show_important_items=original.show_important_items,
        show_permissible_items=original.show_permissible_items,
        signature_label=original.signature_label,
        date_label=original.date_label,
        phone_label=original.phone_label,
        default_usage_commitment=original.default_usage_commitment,
        default_maintenance_commitment=original.default_maintenance_commitment,
        is_default=False,  # Don't duplicate default status
        created_by=request.user
    )
    
    messages.success(request, f'Template duplicated as "{new_template.name}"')
    return redirect('voucher_template_edit', template_id=new_template.id)

# ==================== VOUCHER DETAIL VIEW ====================
@login_required
def voucher_detail_view(request, voucher_id):
    """Single voucher - JSON for mobile, HTML for web."""
    organization = get_user_organization(request.user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")
    
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=organization)
    except Voucher.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Voucher not found'}, status=404)
        return HttpResponseNotFound("Voucher not found")
    
    # YOUR EXISTING PATTERN for JSON response
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return JSON for mobile
        data = {
            'id': str(voucher.id),
            'voucher_number': voucher.voucher_number,
            'title': voucher.title,
            'date_prepared': voucher.date_prepared.isoformat() if voucher.date_prepared else None,
            'requester_name_department': voucher.requester_name_department,
            'purpose': voucher.purpose,
            'urgent_items': voucher.urgent_items,
            'important_items': voucher.important_items,
            'permissible_items': voucher.permissible_items,
            'amount_in_words': voucher.amount_in_words,
            'amount_in_figures': float(voucher.amount_in_figures) if voucher.amount_in_figures else 0,
            'currency': voucher.currency,
            'payable_to': voucher.payable_to,
            'payee_phone': voucher.payee_phone,
            'payment_method': voucher.payment_method,
            'payment_method_display': voucher.get_payment_method_display(),
            'needed_by': voucher.needed_by.isoformat() if voucher.needed_by else None,
            'usage_commitment': voucher.usage_commitment,
            'maintenance_commitment': voucher.maintenance_commitment,
            'requester_signature': voucher.requester_signature,
            'requester_signed_date': voucher.requester_signed_date.isoformat() if voucher.requester_signed_date else None,
            'requester_phone': voucher.requester_phone,
            
            # Template information
            'template': {
                'id': str(voucher.template.id) if voucher.template else None,
                'name': voucher.template.name if voucher.template else None,
                'church_name': voucher.template.church_name if voucher.template else None,
                'church_motto': voucher.template.church_motto if voucher.template else None,
                'form_title': voucher.template.form_title if voucher.template else None,
                'description': voucher.template.description if voucher.template else None,
                'warning_text': voucher.template.warning_text if voucher.template else None,
                'logo_url': request.build_absolute_uri(voucher.template.logo.url) if voucher.template and voucher.template.logo else None,
                'show_urgent_items': voucher.template.show_urgent_items if voucher.template else True,
                'show_important_items': voucher.template.show_important_items if voucher.template else True,
                'show_permissible_items': voucher.template.show_permissible_items if voucher.template else True,
                'signature_label': voucher.template.signature_label if voucher.template else None,
                'date_label': voucher.template.date_label if voucher.template else None,
                'phone_label': voucher.template.phone_label if voucher.template else None,
                'finance_section_title': voucher.template.finance_section_title if voucher.template else None,
                'finance_office_name': voucher.template.finance_office_name if voucher.template else None,
                'default_usage_commitment': voucher.template.default_usage_commitment if voucher.template else None,
                'default_maintenance_commitment': voucher.template.default_maintenance_commitment if voucher.template else None,
            } if voucher.template else None,
            
            # Signature image
            'requester_signature_image_url': request.build_absolute_uri(voucher.requester_signature_image.url) if voucher.requester_signature_image else None,
            
            # Finance Office section
            'status': voucher.status,
            'status_display': voucher.get_status_display(),
            'funds_approved': float(voucher.funds_approved) if voucher.funds_approved else None,
            'funds_denied': float(voucher.funds_denied) if voucher.funds_denied else None,
            'approved_amount': float(voucher.approved_amount) if voucher.approved_amount else None,
            'finance_remarks': voucher.finance_remarks,
            'finance_signature': voucher.finance_signature,
            'approved_by': voucher.approved_by.get_full_name() if voucher.approved_by else None,
            'approved_date': voucher.approved_date.isoformat() if voucher.approved_date else None,
            
            # Payment info
            'paid_amount': float(voucher.paid_amount) if voucher.paid_amount else None,
            'paid_date': voucher.paid_date.isoformat() if voucher.paid_date else None,
            'payment_reference': voucher.payment_reference,
            
            # Calculated properties
            'is_approved': voucher.is_approved,
            'is_paid': voucher.is_paid,
            'is_pending': voucher.is_pending,
            'is_overdue': voucher.is_overdue,
            'days_open': voucher.days_open,
            'total_items_count': voucher.total_items_count,
            'all_items': voucher.get_all_items(),
            
            # Requested by info
            'requested_by': {
                'id': str(voucher.requested_by.id),
                'name': voucher.requested_by.get_full_name(),
                'email': voucher.requested_by.email,
            } if voucher.requested_by else None,
            
            # Attachments
            'attachments': [
                {
                    'id': str(att.id),
                    'file_name': att.file_name,
                    'file_type': att.file_type,
                    'file_size': att.file_size,
                    'description': att.description,
                    'uploaded_at': att.uploaded_at.isoformat(),
                    'url': request.build_absolute_uri(att.file.url) if att.file else None,
                }
                for att in voucher.attachments.all()
            ],
            
            # Comments
            'comments': [
                {
                    'id': str(comment.id),
                    'author': comment.author.get_full_name() if comment.author else None,
                    'comment': comment.comment,
                    'is_internal': comment.is_internal,
                    'created_at': comment.created_at.isoformat(),
                }
                for comment in voucher.comments.all()
            ],
        }
        return JsonResponse(data)
    
    # Return HTML for web - with complete context
    context = {
        'voucher': voucher,
        'organization': organization,
        'can_approve': request.user.has_perm('church.approve_voucher') or request.user.is_superuser,
        'can_pay': request.user.has_perm('church.mark_voucher_paid') or request.user.is_superuser,
    }
    
    return render(request, 'vouchers/detail.html', context)

# ==================== VOUCHER CREATE VIEW ====================
import json
import base64
from decimal import Decimal, InvalidOperation
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.core.files.base import ContentFile

from .models import Voucher, VoucherTemplate, VoucherAttachment

@login_required
@require_http_methods(["GET", "POST"])
def voucher_create_view(request):
    """Create voucher - handles both form POST and JSON POST."""
    organization = get_user_organization(request.user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")

    available_templates = VoucherTemplate.objects.filter(organization=organization)
    
    # If no templates exist, redirect to create template first
    if not available_templates.exists():
        messages.info(request, "Please create a voucher template first.")
        return redirect('voucher_template_create')
    
    # Get the template to use
    template_id = request.GET.get('template')
    if template_id:
        try:
            template = VoucherTemplate.objects.get(id=template_id, organization=organization)
        except VoucherTemplate.DoesNotExist:
            template = available_templates.first()
    else:
        # Try to get default template
        try:
            template = VoucherTemplate.objects.get(organization=organization, is_default=True)
        except VoucherTemplate.DoesNotExist:
            template = available_templates.first()
    
    if request.method == 'POST':
        # Get data based on content type
        is_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
        
        if is_json:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
        else:
            data = request.POST
        
        # Get the action
        action = data.get('action')
        
        # ========== HANDLE SAVE AS BLANK ==========
        if action == 'save_blank':
            # Create a blank voucher with minimal information
            try:
                voucher = Voucher.objects.create(
                    organization=organization,
                    template=template,
                    requested_by=request.user,
                    requester_name_department=f"{request.user.get_full_name()}",
                    purpose="[To be filled]",
                    urgent_items="",
                    important_items="",
                    permissible_items="",
                    amount_in_words="[To be filled]",
                    amount_in_figures=Decimal('0.00'),
                    currency=data.get('currency', 'NGN'),
                    payable_to="[To be filled]",
                    payee_phone="",
                    payment_method=data.get('payment_method', 'transfer'),
                    needed_by=timezone.now().date() + timedelta(days=7),
                    usage_commitment=template.default_usage_commitment if hasattr(template, 'default_usage_commitment') else Voucher._meta.get_field('usage_commitment').default,
                    maintenance_commitment=template.default_maintenance_commitment if hasattr(template, 'default_maintenance_commitment') else Voucher._meta.get_field('maintenance_commitment').default,
                    requester_signature="",
                    requester_signed_date=timezone.now().date(),
                    requester_phone="",
                    status='draft',
                )
                
                if is_json:
                    return JsonResponse({
                        'success': True,
                        'voucher_id': str(voucher.id),
                        'voucher_number': voucher.voucher_number,
                        'message': 'Blank voucher created successfully'
                    })
                
                messages.success(request, f'Blank voucher {voucher.voucher_number} created successfully')
                return redirect('voucher_edit', voucher_id=voucher.id)
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                
                if is_json:
                    return JsonResponse({'error': str(e)}, status=500)
                
                messages.error(request, f'Error creating blank voucher: {str(e)}')
                return redirect('voucher_list')
        
        # ========== REGULAR VOUCHER CREATION ==========
        # Get template from POST data
        post_template_id = data.get('template_id')
        if post_template_id:
            try:
                template = VoucherTemplate.objects.get(id=post_template_id, organization=organization)
            except VoucherTemplate.DoesNotExist:
                pass  # Keep current template

        # Validation logic (skip for save_as_draft without validation if needed)
        # For now, let's keep validation for all actions except 'save_blank'
        errors = {}
        
        # Only validate required fields for 'submit' action
        if action == 'submit':
            required_fields = [
                'requester_name_department', 'purpose', 'amount_in_words', 
                'amount_in_figures', 'payable_to', 'payee_phone', 'needed_by'
            ]
            
            for field in required_fields:
                if not data.get(field, '').strip():
                    field_label = field.replace('_', ' ').title()
                    errors[field] = f'{field_label} is required'
        
        # For 'save_draft', only validate amount if provided
        elif action == 'save_draft':
            amount_str = data.get('amount_in_figures', '').strip()
            if amount_str:
                try:
                    amount = Decimal(amount_str)
                    if amount < 0:
                        errors['amount_in_figures'] = 'Amount cannot be negative'
                except (ValueError, InvalidOperation, TypeError):
                    errors['amount_in_figures'] = 'Invalid amount'
        
        # Validate amount for any action if provided
        amount_str = data.get('amount_in_figures', '').strip()
        if amount_str:
            try:
                amount = Decimal(amount_str)
                if amount < 0:
                    errors['amount_in_figures'] = 'Amount cannot be negative'
            except (ValueError, InvalidOperation, TypeError):
                errors['amount_in_figures'] = 'Invalid amount'
        
        # Validate date if provided
        needed_by = data.get('needed_by')
        if needed_by:
            try:
                needed_date = datetime.strptime(needed_by, '%Y-%m-%d').date()
                if needed_date < timezone.now().date():
                    errors['needed_by'] = 'Date cannot be in the past'
            except ValueError:
                errors['needed_by'] = 'Invalid date format (use YYYY-MM-DD)'
        
        # For non-JSON submissions, validate signature when submitting
        if not is_json and action == 'submit':
            # Check if signature is required when submitting
            signature_data = data.get('signature_data')
            has_signature_file = 'signature_image' in request.FILES
            
            if not signature_data and not has_signature_file:
                # Check if we have at least a text signature
                if not data.get('requester_signature', '').strip():
                    errors['signature'] = 'Signature is required when submitting'
        
        if errors:
            if is_json:
                return JsonResponse({'errors': errors}, status=400)
            
            # For web form, show errors with template context
            context = {
                'payment_methods': Voucher.PAYMENT_METHOD_CHOICES,
                'template': template,
                'available_templates': available_templates,
                'errors': errors,
                'data': data,
                'organization': organization,
                'default_usage_commitment': template.default_usage_commitment if hasattr(template, 'default_usage_commitment') else Voucher._meta.get_field('usage_commitment').default,
                'default_maintenance_commitment': template.default_maintenance_commitment if hasattr(template, 'default_maintenance_commitment') else Voucher._meta.get_field('maintenance_commitment').default,
            }
            return render(request, 'vouchers/create.html', context)
        
        # Create voucher (for save_draft and submit actions)
        try:
            # Determine status based on action
            if action == 'submit':
                status = 'submitted'
            else:  # 'save_draft' or default
                status = 'draft'
            
            # Get amount - default to 0 if not provided
            amount_str = data.get('amount_in_figures', '0').strip()
            if amount_str:
                try:
                    amount = Decimal(amount_str)
                except (ValueError, InvalidOperation, TypeError):
                    amount = Decimal('0.00')
            else:
                amount = Decimal('0.00')
            
            # Get date fields
            needed_by = data.get('needed_by')
            if needed_by:
                try:
                    needed_date = datetime.strptime(needed_by, '%Y-%m-%d').date()
                except ValueError:
                    needed_date = timezone.now().date() + timedelta(days=7)
            else:
                needed_date = timezone.now().date() + timedelta(days=7)
            
            signed_date_str = data.get('requester_signed_date')
            if signed_date_str:
                try:
                    signed_date = datetime.strptime(signed_date_str, '%Y-%m-%d').date()
                except ValueError:
                    signed_date = timezone.now().date()
            else:
                signed_date = timezone.now().date()
            
            # Create voucher with template
            voucher = Voucher.objects.create(
                organization=organization,
                template=template,  # Save the template
                requested_by=request.user,
                requester_name_department=data.get('requester_name_department', f"{request.user.get_full_name()}"),
                purpose=data.get('purpose', '[To be filled]'),
                urgent_items=data.get('urgent_items', ''),
                important_items=data.get('important_items', ''),
                permissible_items=data.get('permissible_items', ''),
                amount_in_words=data.get('amount_in_words', '[To be filled]'),
                amount_in_figures=amount,
                currency=data.get('currency', 'NGN'),
                payable_to=data.get('payable_to', '[To be filled]'),
                payee_phone=data.get('payee_phone', ''),
                payment_method=data.get('payment_method', 'transfer'),
                needed_by=needed_date,
                usage_commitment=data.get('usage_commitment', template.default_usage_commitment if hasattr(template, 'default_usage_commitment') else Voucher._meta.get_field('usage_commitment').default),
                maintenance_commitment=data.get('maintenance_commitment', template.default_maintenance_commitment if hasattr(template, 'default_maintenance_commitment') else Voucher._meta.get_field('maintenance_commitment').default),
                requester_signature=data.get('requester_signature', ''),
                requester_signed_date=signed_date,
                requester_phone=data.get('requester_phone', ''),
                status=status,
            )
            
            # Handle signature image upload (for web form submissions)
            if not is_json and 'signature_image' in request.FILES:
                voucher.requester_signature_image = request.FILES['signature_image']
                voucher.save()
            
            # Handle signature data URL (if signature was drawn)
            elif not is_json and data.get('signature_data'):
                # Convert data URL to image file
                signature_data = data.get('signature_data')
                if signature_data.startswith('data:image/'):
                    # Extract image data from data URL
                    format, imgstr = signature_data.split(';base64,')
                    ext = format.split('/')[-1]
                    
                    # Create file from base64 data
                    data_file = ContentFile(base64.b64decode(imgstr))
                    
                    # Generate filename
                    filename = f'signature_{voucher.voucher_number}.{ext}'
                    
                    # Save to signature image field
                    voucher.requester_signature_image.save(filename, data_file, save=True)
            
            # Handle attachments for form submissions
            if not is_json and 'attachments' in request.FILES:
                for file in request.FILES.getlist('attachments'):
                    VoucherAttachment.objects.create(
                        voucher=voucher,
                        file=file,
                        file_name=file.name,
                        file_type=file.content_type,
                        file_size=file.size,
                        uploaded_by=request.user
                    )
            
            # Handle other file uploads (quotes, receipts, etc.)
            if not is_json:
                for field_name in ['quotes', 'receipts', 'supporting_docs']:
                    if field_name in request.FILES:
                        for file in request.FILES.getlist(field_name):
                            VoucherAttachment.objects.create(
                                voucher=voucher,
                                file=file,
                                file_name=file.name,
                                file_type=file.content_type,
                                file_size=file.size,
                                description=field_name.replace('_', ' ').title(),
                                uploaded_by=request.user
                            )
            
            # Handle JSON submissions (mobile app)
            if is_json:
                return JsonResponse({
                    'success': True,
                    'voucher_id': str(voucher.id),
                    'voucher_number': voucher.voucher_number,
                    'message': 'Voucher created successfully'
                })
            
            # For web form submissions
            messages.success(request, f'Voucher {voucher.voucher_number} created successfully')
            
            # Submit for approval if action is 'submit'
            if action == 'submit':
                voucher.submit_for_approval()
                messages.success(request, 'Voucher submitted for approval')
                return redirect('voucher_detail', voucher_id=voucher.id)
            else:
                # Saved as draft
                return redirect('voucher_detail', voucher_id=voucher.id)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            if is_json:
                return JsonResponse({'error': str(e)}, status=500)
            
            # For web form, show error with context
            context = {
                'payment_methods': Voucher.PAYMENT_METHOD_CHOICES,
                'template': template,
                'available_templates': available_templates,
                'error': str(e),
                'data': data,
                'organization': organization,
                'default_usage_commitment': template.default_usage_commitment if hasattr(template, 'default_usage_commitment') else Voucher._meta.get_field('usage_commitment').default,
                'default_maintenance_commitment': template.default_maintenance_commitment if hasattr(template, 'default_maintenance_commitment') else Voucher._meta.get_field('maintenance_commitment').default,
            }
            return render(request, 'vouchers/create.html', context, status=500)
    
    # GET request - show form
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return form structure for mobile app
        return JsonResponse({
            'fields': [
                {'name': 'purpose', 'label': 'Purpose', 'type': 'textarea', 'required': True},
                {'name': 'urgent_items', 'label': 'URGENT Items', 'type': 'textarea'},
                {'name': 'important_items', 'label': 'IMPORTANT Items', 'type': 'textarea'},
                {'name': 'permissible_items', 'label': 'PERMISSIBLE Items', 'type': 'textarea'},
                {'name': 'amount_in_words', 'label': 'Amount in Words', 'type': 'text', 'required': True},
                {'name': 'amount_in_figures', 'label': 'Amount in Figures', 'type': 'number', 'required': True},
                {'name': 'payable_to', 'label': 'Payable To', 'type': 'text', 'required': True},
                {'name': 'payee_phone', 'label': 'Payee Phone', 'type': 'tel', 'required': True},
                {'name': 'payment_method', 'label': 'Payment Method', 'type': 'select', 
                 'options': [{'value': val, 'label': label} for val, label in Voucher.PAYMENT_METHOD_CHOICES]},
                {'name': 'needed_by', 'label': 'Needed By', 'type': 'date', 'required': True},
            ]
        })

    # For web GET request
    context = {
        'payment_methods': Voucher.PAYMENT_METHOD_CHOICES,
        'template': template,
        'available_templates': available_templates,
        'organization': organization,
        'default_usage_commitment': template.default_usage_commitment if hasattr(template, 'default_usage_commitment') else Voucher._meta.get_field('usage_commitment').default,
        'default_maintenance_commitment': template.default_maintenance_commitment if hasattr(template, 'default_maintenance_commitment') else Voucher._meta.get_field('maintenance_commitment').default,
    }
    
    return render(request, 'vouchers/create.html', context)
    # For web, show create form

# ==================== VOUCHER UPDATE VIEW ====================
@login_required
@require_http_methods(["GET", "POST", "PUT"])
def voucher_update_view(request, voucher_id):
    """Update voucher - handles both form POST and JSON PUT."""
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=request.user.organization)
    except Voucher.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Voucher not found'}, status=404)
        return HttpResponseNotFound("Voucher not found")
    
    # Check if this is a blank voucher (all main fields are empty)
    is_blank_voucher = (
        not voucher.requester_name_department and
        not voucher.purpose and
        not voucher.amount_in_words and
        not voucher.payable_to and
        voucher.amount_in_figures == Decimal('0.00')
    )
    
    # Check permissions - only requester can edit draft vouchers
    if voucher.status != 'draft' and voucher.requested_by != request.user:
        if not request.user.is_staff and not getattr(request.user, 'is_admin', False):
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({'error': 'Permission denied. Only draft vouchers can be edited by requester.'}, status=403)
            return HttpResponseForbidden("Permission denied")
    
    if request.method in ['POST', 'PUT']:
        # Get data based on content type
        is_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
        
        if is_json:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
        else:
            data = request.POST
        
        # Get the action
        action = data.get('action', 'save')
        
        # Validation logic
        errors = {}
        
        # Only validate if voucher is still draft
        if voucher.status == 'draft':
            # Different validation for blank vouchers
            if is_blank_voucher:
                if action == 'submit':
                    # When submitting a blank voucher, all main fields must be filled
                    required_fields = [
                        'requester_name_department', 'purpose', 'amount_in_words',
                        'amount_in_figures', 'payable_to', 'payee_phone', 'needed_by'
                    ]
                    
                    for field in required_fields:
                        value = data.get(field, '').strip()
                        if not value:
                            field_label = field.replace('_', ' ').title()
                            errors[field] = f'{field_label} is required'
                
                # For 'save' action on blank vouchers, no validation needed
                # Allow saving draft with empty fields
            else:
                # Regular validation for non-blank vouchers
                if action == 'submit':
                    required_fields = [
                        'requester_name_department', 'purpose', 'amount_in_words', 
                        'amount_in_figures', 'payable_to', 'payee_phone', 'needed_by'
                    ]
                    
                    for field in required_fields:
                        if not data.get(field, '').strip():
                            field_label = field.replace('_', ' ').title()
                            errors[field] = f'{field_label} is required'
        
        # Validate amount if provided (for both blank and non-blank)
        if data.get('amount_in_figures'):
            try:
                amount = Decimal(data.get('amount_in_figures'))
                if amount < 0:
                    errors['amount_in_figures'] = 'Amount cannot be negative'
            except (ValueError, InvalidOperation, TypeError):
                errors['amount_in_figures'] = 'Invalid amount'
        
        # Validate date if provided
        needed_by = data.get('needed_by')
        if needed_by:
            try:
                needed_date = datetime.strptime(needed_by, '%Y-%m-%d').date()
                if needed_date < timezone.now().date():
                    errors['needed_by'] = 'Date cannot be in the past'
            except ValueError:
                errors['needed_by'] = 'Invalid date format (use YYYY-MM-DD)'
        
        # For non-JSON submissions, validate signature when submitting blank vouchers
        if not is_json and action == 'submit' and is_blank_voucher:
            # Check if signature is required when submitting blank vouchers
            signature_data = data.get('signature_data')
            has_signature_file = 'signature_image' in request.FILES
            
            if not signature_data and not has_signature_file:
                # Check if we have at least a text signature
                if not data.get('requester_signature', '').strip():
                    errors['signature'] = 'Signature is required when submitting'
        
        if errors:
            if is_json:
                return JsonResponse({'errors': errors}, status=400)
            
            # For web form, show errors with template context
            return render(request, 'vouchers/edit.html', {
                'voucher': voucher,
                'errors': errors,
                'data': data,
                'is_blank_voucher': is_blank_voucher,
                'payment_methods': Voucher.PAYMENT_METHOD_CHOICES,
                'can_edit': voucher.status == 'draft' and voucher.requested_by == request.user,
                'can_approve': request.user.is_staff or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_finance', False),
                'can_pay': request.user.is_staff or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_finance', False),
                'attachments': voucher.attachments.all(),
                'comments': voucher.comments.all(),
            })
        
        try:
            # Update voucher fields (only if draft or blank voucher needs updating)
            if voucher.status == 'draft':
                voucher.requester_name_department = data.get('requester_name_department', voucher.requester_name_department)
                voucher.purpose = data.get('purpose', voucher.purpose)
                voucher.urgent_items = data.get('urgent_items', voucher.urgent_items)
                voucher.important_items = data.get('important_items', voucher.important_items)
                voucher.permissible_items = data.get('permissible_items', voucher.permissible_items)
                voucher.amount_in_words = data.get('amount_in_words', voucher.amount_in_words)
                
                if data.get('amount_in_figures'):
                    try:
                        voucher.amount_in_figures = Decimal(data.get('amount_in_figures'))
                    except (ValueError, InvalidOperation, TypeError):
                        pass  # Keep existing value if invalid
                
                voucher.currency = data.get('currency', voucher.currency)
                voucher.payable_to = data.get('payable_to', voucher.payable_to)
                voucher.payee_phone = data.get('payee_phone', voucher.payee_phone)
                voucher.payment_method = data.get('payment_method', voucher.payment_method)
                
                if needed_by:
                    voucher.needed_by = needed_date
            
            # Always allow updating these fields
            voucher.usage_commitment = data.get('usage_commitment', voucher.usage_commitment)
            voucher.maintenance_commitment = data.get('maintenance_commitment', voucher.maintenance_commitment)
            voucher.requester_signature = data.get('requester_signature', voucher.requester_signature)
            voucher.requester_phone = data.get('requester_phone', voucher.requester_phone)
            
            # Handle requester signed date
            if data.get('requester_signed_date'):
                try:
                    signed_date = datetime.strptime(data.get('requester_signed_date'), '%Y-%m-%d').date()
                    voucher.requester_signed_date = signed_date
                except ValueError:
                    pass
            
            # Handle signature image upload (for web form submissions)
            if not is_json and 'signature_image' in request.FILES:
                voucher.requester_signature_image = request.FILES['signature_image']
            
            # Handle signature data URL (if signature was drawn)
            elif not is_json and data.get('signature_data'):
                # Convert data URL to image file
                signature_data = data.get('signature_data')
                if signature_data.startswith('data:image/'):
                    # Extract image data from data URL
                    format, imgstr = signature_data.split(';base64,')
                    ext = format.split('/')[-1]
                    
                    # Create file from base64 data
                    data_file = ContentFile(base64.b64decode(imgstr))
                    
                    # Generate filename
                    filename = f'signature_{voucher.voucher_number}.{ext}'
                    
                    # Save to signature image field
                    voucher.requester_signature_image.save(filename, data_file, save=False)
            
            # Handle attachments for form submissions
            if not is_json and 'attachments' in request.FILES:
                for file in request.FILES.getlist('attachments'):
                    VoucherAttachment.objects.create(
                        voucher=voucher,
                        file=file,
                        file_name=file.name,
                        file_type=file.content_type,
                        file_size=file.size,
                        uploaded_by=request.user
                    )
            
            voucher.save()
            
            # Add comment if provided
            comment_text = data.get('comment', '').strip()
            if comment_text:
                VoucherComment.objects.create(
                    voucher=voucher,
                    author=request.user,
                    comment=comment_text,
                    is_internal=data.get('is_internal_comment', False)
                )
            
            # Handle status changes
            if action == 'submit' and voucher.status == 'draft':
                voucher.submit_for_approval()
                
                # If this was a blank voucher that got submitted, show special message
                if is_blank_voucher:
                    messages.success(request, f'Blank voucher {voucher.voucher_number} submitted for approval')
                else:
                    messages.success(request, f'Voucher {voucher.voucher_number} submitted for approval')
                    
                return redirect('voucher_detail', voucher_id=voucher.id)
            
            elif action == 'approve' and voucher.status in ['submitted', 'draft']:
                # Check if user has approval permission
                can_approve = (
                    request.user.is_staff or 
                    getattr(request.user, 'is_admin', False) or 
                    getattr(request.user, 'is_finance', False)
                )
                if can_approve:
                    approved_amount = data.get('approved_amount')
                    remarks = data.get('finance_remarks', '')
                    voucher.approve(request.user, approved_amount, remarks)
                    messages.success(request, f'Voucher {voucher.voucher_number} approved')
            
            elif action == 'reject' and voucher.status in ['submitted', 'draft']:
                can_reject = (
                    request.user.is_staff or 
                    getattr(request.user, 'is_admin', False) or 
                    getattr(request.user, 'is_finance', False)
                )
                if can_reject:
                    reason = data.get('rejection_reason', '')
                    voucher.reject(request.user, reason)
                    messages.success(request, f'Voucher {voucher.voucher_number} rejected')
            
            elif action == 'pay' and voucher.status == 'approved':
                # Check if user has payment permission
                can_pay = (
                    request.user.is_staff or 
                    getattr(request.user, 'is_admin', False) or 
                    getattr(request.user, 'is_finance', False)
                )
                if can_pay:
                    amount = data.get('paid_amount')
                    reference = data.get('payment_reference', '')
                    voucher.mark_as_paid(amount, reference)
                    messages.success(request, f'Voucher {voucher.voucher_number} marked as paid')
            
            else:
                # Regular save action
                if is_blank_voucher:
                    messages.success(request, f'Blank voucher {voucher.voucher_number} saved as draft')
                else:
                    messages.success(request, f'Voucher {voucher.voucher_number} updated successfully')
            
            if is_json:
                return JsonResponse({
                    'success': True,
                    'message': 'Voucher updated successfully',
                    'voucher_id': str(voucher.id),
                    'voucher_number': voucher.voucher_number,
                    'status': voucher.status,
                    'is_blank_voucher': is_blank_voucher,
                })
            
            return redirect('voucher_detail', voucher_id=voucher.id)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            if is_json:
                return JsonResponse({'error': str(e)}, status=500)
            
            # For web form, show error with context
            return render(request, 'vouchers/edit.html', {
                'voucher': voucher,
                'error': str(e),
                'data': data,
                'is_blank_voucher': is_blank_voucher,
                'payment_methods': Voucher.PAYMENT_METHOD_CHOICES,
                'can_edit': voucher.status == 'draft' and voucher.requested_by == request.user,
                'can_approve': request.user.is_staff or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_finance', False),
                'can_pay': request.user.is_staff or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_finance', False),
                'attachments': voucher.attachments.all(),
                'comments': voucher.comments.all(),
            }, status=500)
    
    # GET request - show edit form
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return current voucher data for mobile app
        return JsonResponse({
            'id': str(voucher.id),
            'voucher_number': voucher.voucher_number,
            'requester_name_department': voucher.requester_name_department,
            'purpose': voucher.purpose,
            'urgent_items': voucher.urgent_items,
            'important_items': voucher.important_items,
            'permissible_items': voucher.permissible_items,
            'amount_in_words': voucher.amount_in_words,
            'amount_in_figures': float(voucher.amount_in_figures) if voucher.amount_in_figures else 0,
            'currency': voucher.currency,
            'payable_to': voucher.payable_to,
            'payee_phone': voucher.payee_phone,
            'payment_method': voucher.payment_method,
            'needed_by': voucher.needed_by.isoformat() if voucher.needed_by else None,
            'usage_commitment': voucher.usage_commitment,
            'maintenance_commitment': voucher.maintenance_commitment,
            'requester_signature': voucher.requester_signature,
            'requester_signed_date': voucher.requester_signed_date.isoformat() if voucher.requester_signed_date else None,
            'requester_phone': voucher.requester_phone,
            'status': voucher.status,
            'is_blank_voucher': is_blank_voucher,
            'can_edit': voucher.status == 'draft' and voucher.requested_by == request.user,
            'can_approve': request.user.is_staff or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_finance', False),
            'can_pay': request.user.is_staff or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_finance', False),
        })
    
    # For web, show edit form
    return render(request, 'vouchers/edit.html', {
        'voucher': voucher,
        'payment_methods': Voucher.PAYMENT_METHOD_CHOICES,
        'status_choices': Voucher.STATUS_CHOICES,
        'is_blank_voucher': is_blank_voucher,
        'can_edit': voucher.status == 'draft' and voucher.requested_by == request.user,
        'can_approve': request.user.is_staff or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_finance', False),
        'can_pay': request.user.is_staff or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_finance', False),
        'attachments': voucher.attachments.all(),
        'comments': voucher.comments.all(),
    })

# ==================== VOUCHER DASHBOARD VIEW ====================
# In your church/views.py, update the voucher_dashboard_view function:

from django.utils import timezone
from datetime import timedelta

@login_required
def voucher_dashboard_view(request):
    """Voucher dashboard with statistics."""
    organization = get_user_organization(request.user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return render(request, 'vouchers/dashboard.html', {'error': 'No organization assigned'})
    
    # Get statistics
    vouchers = Voucher.objects.filter(organization=organization)
    
    stats = {
        'total': vouchers.count(),
        'draft': vouchers.filter(status='draft').count(),
        'submitted': vouchers.filter(status='submitted').count(),
        'approved': vouchers.filter(status='approved').count(),
        'paid': vouchers.filter(status='paid').count(),
        'rejected': vouchers.filter(status='rejected').count(),
        'total_amount': vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or 0,
        'approved_amount': vouchers.filter(status='approved').aggregate(Sum('approved_amount'))['approved_amount__sum'] or 0,
        'paid_amount': vouchers.filter(status='paid').aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0,
        'overdue': vouchers.filter(status__in=['submitted', 'approved']).filter(needed_by__lt=timezone.now().date()).count(),
    }
    
    # Recent vouchers
    recent_vouchers = vouchers.order_by('-created_at')[:10]
    
    # Monthly summary (last 6 months) - FIXED VERSION
    monthly_summary = []
    
    # If you want to implement monthly summary, you can add it later
    # For now, let's keep it simple
    
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return JSON for mobile
        return JsonResponse({
            'stats': stats,
            'recent_vouchers': [
                {
                    'id': str(v.id),
                    'voucher_number': v.voucher_number,
                    'purpose': v.purpose[:50] + '...' if len(v.purpose) > 50 else v.purpose,
                    'amount': float(v.amount_in_figures) if v.amount_in_figures else 0,
                    'status': v.status,
                    'date_prepared': v.date_prepared.isoformat() if v.date_prepared else None,
                }
                for v in recent_vouchers
            ],
            'monthly_summary': monthly_summary
        })
    
    # Return HTML for web
    context = {
        'stats': stats,
        'recent_vouchers': recent_vouchers,
        'monthly_summary': monthly_summary,
        'can_approve': request.user.is_staff or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_finance', False),
        'can_pay': request.user.is_staff or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_finance', False),
    }
    
    return render(request, 'vouchers/dashboard.html', context)
@login_required
@require_http_methods(["GET", "POST"])
def voucher_create_blank_view(request, template_id=None):
    """Create a COMPLETELY blank voucher with NO pre-filled values."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return HttpResponseForbidden("No organization assigned")
    
    # Get template (same logic as regular create)
    if template_id:
        template = get_object_or_404(VoucherTemplate, id=template_id, organization=organization)
    else:
        try:
            template = VoucherTemplate.objects.get(organization=organization, is_default=True)
        except VoucherTemplate.DoesNotExist:
            template = VoucherTemplate.objects.filter(organization=organization).first()
            if not template:
                messages.error(request, "Please create a voucher template first.")
                return redirect('voucher_template_create')
    
    if request.method == 'POST':
        # Create voucher with COMPLETELY empty/None values
        try:
            voucher = Voucher.objects.create(
                organization=organization,
                requested_by=request.user,
                
                # TEXT FIELDS - Empty strings
                requester_name_department="",
                purpose="",
                urgent_items="",
                important_items="",
                permissible_items="",
                amount_in_words="",
                
                # NUMERIC FIELD - NULL instead of 0.00
                amount_in_figures=None,  # Changed from Decimal('0.00')
                
                # CURRENCY & PAYMENT
                currency='',  # Empty string instead of 'NGN'
                payable_to="",
                payee_phone="",
                payment_method='',  # Empty string instead of 'transfer'
                
                # DATE FIELDS - NULL instead of auto-filled dates
                needed_by=None,  # Changed from timezone.now().date() + timedelta(days=7)
                
                # COMMITMENTS - Empty strings
                usage_commitment="",
                maintenance_commitment="",
                
                # SIGNATURE FIELDS - Empty
                requester_signature="",
                requester_signed_date=None,  # Changed from timezone.now().date()
                requester_phone="",
                
                # STATUS
                status='draft',
                template=template,
            )
            
            messages.success(request, f"Completely blank voucher created: {voucher.voucher_number}")
            return redirect('voucher_edit', voucher_id=voucher.id)
            
        except Exception as e:
            messages.error(request, f"Error creating blank voucher: {str(e)}")
            return redirect('voucher_list')
    
    # GET request - just create it immediately
    # Auto-create on GET for convenience
    try:
        voucher = Voucher.objects.create(
            organization=organization,
            requested_by=request.user,
            
            # TEXT FIELDS - Empty strings
            requester_name_department="",
            purpose="",
            urgent_items="",
            important_items="",
            permissible_items="",
            amount_in_words="",
            
            # NUMERIC FIELD - NULL instead of 0.00
            amount_in_figures=None,  # Changed from Decimal('0.00')
            
            # CURRENCY & PAYMENT
            currency='',  # Empty string instead of 'NGN'
            payable_to="",
            payee_phone="",
            payment_method='',  # Empty string instead of 'transfer'
            
            # DATE FIELDS - NULL instead of auto-filled dates
            needed_by=None,  # Changed from timezone.now().date() + timedelta(days=7)
            
            # COMMITMENTS - Empty strings (don't use template defaults)
            usage_commitment="",
            maintenance_commitment="",
            
            # SIGNATURE FIELDS - Empty
            requester_signature="",
            requester_signed_date=None,  # Changed from timezone.now().date()
            requester_phone="",
            
            # STATUS
            status='draft',
            template=template,
        )
        
        messages.success(request, f"Completely blank voucher created: {voucher.voucher_number}")
        return redirect('voucher_edit', voucher_id=voucher.id)
        
    except Exception as e:
        messages.error(request, f"Error creating blank voucher: {str(e)}")
        return redirect('voucher_list')
# ==================== VOUCHER ACTION VIEWS ====================
@login_required
@require_http_methods(["POST"])
def voucher_submit_view(request, voucher_id):
    """Submit voucher for approval."""
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=request.user.organization)
    except Voucher.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Voucher not found'}, status=404)
        return HttpResponseNotFound("Voucher not found")
    
    # Check permission
    if voucher.requested_by != request.user and not request.user.is_staff:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Permission denied'}, status=403)
        return HttpResponseForbidden("Permission denied")
    
    if voucher.status != 'draft':
        error_msg = f'Cannot submit voucher with status: {voucher.status}'
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect('voucher_detail', voucher_id=voucher.id)
    
    if voucher.submit_for_approval():
        success_msg = 'Voucher submitted for approval'
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'success': True, 'message': success_msg})
        messages.success(request, success_msg)
    else:
        error_msg = 'Failed to submit voucher'
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': error_msg}, status=400)
        messages.error(request, error_msg)
    
    return redirect('voucher_detail', voucher_id=voucher.id)

@login_required
@require_http_methods(["POST"])
def voucher_approve_view(request, voucher_id):
    """Approve a voucher (finance/admin only)."""
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=request.user.organization)
    except Voucher.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Voucher not found'}, status=404)
        return HttpResponseNotFound("Voucher not found")
    
    # Check permission
    can_approve = (
        request.user.is_staff or 
        getattr(request.user, 'is_admin', False) or 
        getattr(request.user, 'is_finance', False)
    )
    if not can_approve:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Permission denied'}, status=403)
        return HttpResponseForbidden("Permission denied")
    
    if voucher.status not in ['submitted', 'draft']:
        error_msg = f'Cannot approve voucher with status: {voucher.status}'
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect('voucher_detail', voucher_id=voucher.id)
    
    # Get data
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        data = json.loads(request.body)
    else:
        data = request.POST
    
    approved_amount = data.get('approved_amount')
    remarks = data.get('finance_remarks', '')
    
    if voucher.approve(request.user, approved_amount, remarks):
        success_msg = 'Voucher approved successfully'
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'success': True, 'message': success_msg})
        messages.success(request, success_msg)
    else:
        error_msg = 'Failed to approve voucher'
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': error_msg}, status=400)
        messages.error(request, error_msg)
    
    return redirect('voucher_detail', voucher_id=voucher.id)

# ==================== PDF GENERATION VIEW ====================
# ==================== UPDATED PDF GENERATION VIEW ====================
from django.template.loader import render_to_string
from django.utils.text import slugify

@login_required
def voucher_pdf_view(request, voucher_id):
    """Render HTML template for PDF printing."""
    
    organization = get_user_organization(request.user)

    if not organization:
        return HttpResponseForbidden("No organization assigned")
    
    try:
        voucher = Voucher.objects.select_related('template').get(
            id=voucher_id, 
            organization=organization
        )
    except Voucher.DoesNotExist:
        return HttpResponseNotFound("Voucher not found")
    
    # Check permission
    if voucher.requested_by != request.user and not request.user.is_staff:
        if not getattr(request.user, 'is_admin', False) and not getattr(request.user, 'is_finance', False):
            return HttpResponseForbidden("Permission denied")
    
    context = {
        'voucher': voucher,
        'organization': organization,
    }
    
    # Render HTML template
    return render(request, 'vouchers/voucher_pdf_template.html', context)


# Alternative: If you want to keep the download functionality
@login_required
def voucher_download_view(request, voucher_id):
    """Redirect to PDF view or trigger download."""
    return voucher_pdf_view(request, voucher_id)




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



# inventory/views.py
import json
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, F, Count
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (
    InventoryCategory, InventoryVendor, InventoryItem, 
    InventoryTransaction, InventoryCheckout, InventoryAudit,
    InventoryAuditItem
)



@login_required
def inventory_dashboard_view(request):
    """Inventory dashboard - JSON for mobile, HTML for web"""
    organization = get_user_organization(request.user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")
    
    # Calculate dashboard statistics (same for both)
    stats = {
        'total_items': InventoryItem.objects.filter(organization=organization).count(),
        'low_stock_items': InventoryItem.objects.filter(
            organization=organization,
            quantity__lte=F('reorder_level'),
            alert_on_low=True
        ).count(),
        'active_checkouts': InventoryCheckout.objects.filter(
            organization=organization,
            status='active'
        ).count(),
        'overdue_checkouts': InventoryCheckout.objects.filter(
            organization=organization,
            status='overdue'
        ).count(),
        'total_value': InventoryItem.objects.filter(
            organization=organization
        ).aggregate(total=Sum(F('quantity') * F('purchase_price')))['total'] or 0,
    }
    
    # Recent transactions
    recent_transactions = InventoryTransaction.objects.filter(
        organization=organization
    ).select_related('item').order_by('-created_at')[:10]
    
    # Low stock alerts
    low_stock_items = InventoryItem.objects.filter(
        organization=organization,
        quantity__lte=F('reorder_level'),
        alert_on_low=True
    ).order_by('quantity')[:10]
    
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return JSON for mobile
        data = {
            'stats': stats,
            'recent_transactions': [
                {
                    'id': str(t.id),
                    'item_name': t.item.name,
                    'transaction_type': t.transaction_type,
                    'quantity': t.quantity,
                    'created_at': t.created_at.isoformat() if t.created_at else None,
                    'performed_by': t.performed_by.get_full_name() if t.performed_by else 'System',
                }
                for t in recent_transactions
            ],
            'low_stock_alerts': [
                {
                    'id': str(item.id),
                    'name': item.name,
                    'quantity': item.quantity,
                    'reorder_level': item.reorder_level,
                    'status': item.status,
                }
                for item in low_stock_items
            ]
        }
        return JsonResponse(data)
    
    # Return HTML for web
    return render(request, 'inventory/dashboard.html', {
        'stats': stats,
        'recent_transactions': recent_transactions,
        'low_stock_items': low_stock_items,
        'organization': organization,
    })


@login_required
def inventory_item_list_view(request):
    """List inventory items - JSON for mobile, HTML for web"""
    organization = get_user_organization(request.user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")
    
    # Get filters
    search = request.GET.get('search', '')
    category_id = request.GET.get('category')
    department_id = request.GET.get('department')
    status_filter = request.GET.get('status')
    low_stock_only = request.GET.get('low_stock') == 'true'
    
    # Build queryset
    items = InventoryItem.objects.filter(organization=organization)
    
    # Apply filters
    if search:
        items = items.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search) |
            Q(sku__icontains=search) |
            Q(barcode__icontains=search)
        )
    
    if category_id:
        items = items.filter(category_id=category_id)
    
    if department_id:
        items = items.filter(department_id=department_id)
    
    if status_filter:
        items = items.filter(status=status_filter)
    
    if low_stock_only:
        items = items.filter(quantity__lte=F('reorder_level'))
    
    # Order by
    sort_by = request.GET.get('sort', 'name')
    if sort_by == 'quantity':
        items = items.order_by('quantity')
    elif sort_by == 'value':
        items = items.order_by(F('quantity') * F('purchase_price'))
    else:
        items = items.order_by('name')
    
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return JSON for mobile
        data = [
            {
                'id': str(item.id),
                'name': item.name,
                'description': item.description[:100] if item.description else '',
                'sku': item.sku,
                'quantity': item.quantity,
                'reorder_level': item.reorder_level,
                'status': item.status,
                'is_low_stock': item.is_low_stock,
                'total_value': float(item.total_value) if item.total_value else 0,
                'location': item.location,
                'department': item.department.name if item.department else None,
                'category': item.category.name if item.category else None,
                'image_url': request.build_absolute_uri(item.image.url) if item.image else None,
            }
            for item in items
        ]
        return JsonResponse({'items': data})
    
    # Return HTML for web
    # Get filter options
    categories = InventoryCategory.objects.filter(organization=organization)
    departments = Department.objects.filter(organization=organization)
    
    return render(request, 'inventory/items/list.html', {
        'items': items,
        'categories': categories,
        'departments': departments,
        'search': search,
        'category_id': category_id,
        'department_id': department_id,
        'status_filter': status_filter,
        'low_stock_only': low_stock_only,
    })


@login_required
def inventory_item_detail_view(request, item_id):
    """Single inventory item - JSON for mobile, HTML for web"""
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
    
    # Get related data
    transactions = InventoryTransaction.objects.filter(
        item=item
    ).order_by('-created_at')[:20]
    
    checkouts = InventoryCheckout.objects.filter(
        item=item
    ).order_by('-checkout_date')[:10]
    
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return JSON for mobile
        data = {
            'id': str(item.id),
            'name': item.name,
            'description': item.description,
            'sku': item.sku,
            'barcode': item.barcode,
            'asset_tag': item.asset_tag,
            'quantity': item.quantity,
            'reorder_level': item.reorder_level,
            'reorder_quantity': item.reorder_quantity,
            'status': item.status,
            'is_low_stock': item.is_low_stock,
            'purchase_price': float(item.purchase_price) if item.purchase_price else 0,
            'total_value': float(item.total_value) if item.total_value else 0,
            'location': item.location,
            'condition': item.condition,
            'item_type': item.item_type,
            'department': {
                'id': str(item.department.id),
                'name': item.department.name,
                'code': item.department.code,
            } if item.department else None,
            'category': {
                'id': str(item.category.id),
                'name': item.category.name,
                'category_type': item.category.category_type,
            } if item.category else None,
            'vendor': {
                'id': str(item.vendor.id),
                'name': item.vendor.name,
            } if item.vendor else None,
            'purchase_date': item.purchase_date.isoformat() if item.purchase_date else None,
            'warranty_expiry': item.warranty_expiry.isoformat() if item.warranty_expiry else None,
            'storage_instructions': item.storage_instructions,
            'notes': item.notes,
            'image_url': request.build_absolute_uri(item.image.url) if item.image else None,
            'recent_transactions': [
                {
                    'id': str(t.id),
                    'transaction_type': t.transaction_type,
                    'quantity': t.quantity,
                    'performed_by': t.performed_by.get_full_name() if t.performed_by else 'System',
                    'created_at': t.created_at.isoformat(),
                    'notes': t.notes,
                }
                for t in transactions
            ],
            'active_checkouts': [
                {
                    'id': str(c.id),
                    'member_name': c.member.full_name,
                    'quantity': c.quantity,
                    'checkout_date': c.checkout_date.isoformat(),
                    'due_date': c.due_date.isoformat() if c.due_date else None,
                    'status': c.status,
                }
                for c in checkouts if c.status in ['active', 'overdue']
            ]
        }
        return JsonResponse(data)
    
    # Return HTML for web
    return render(request, 'inventory/items/detail.html', {
        'item': item,
        'transactions': transactions,
        'checkouts': checkouts,
    })


@login_required
@require_http_methods(["GET", "POST"])
def inventory_item_create_view(request):
    """Create inventory item - handles both form POST and JSON POST"""
    organization = get_user_organization(request.user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")
    
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
        # Get data based on content type
        is_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
        
        if is_json:
            data = json.loads(request.body)
        else:
            data = request.POST.copy()
            if 'image' in request.FILES:
                data['image'] = request.FILES['image']
        
        # Validation
        errors = {}
        if not data.get('name', '').strip():
            errors['name'] = 'Item name is required'
        
        # Validate quantity fields
        try:
            quantity = int(data.get('quantity', 0))
            if quantity < 0:
                errors['quantity'] = 'Quantity cannot be negative'
        except ValueError:
            errors['quantity'] = 'Quantity must be a number'
        
        try:
            reorder_level = int(data.get('reorder_level', 0))
            if reorder_level < 0:
                errors['reorder_level'] = 'Reorder level cannot be negative'
        except ValueError:
            errors['reorder_level'] = 'Reorder level must be a number'
        
        # Validate price
        purchase_price = data.get('purchase_price')
        if purchase_price:
            try:
                price = float(purchase_price)
                if price < 0:
                    errors['purchase_price'] = 'Price cannot be negative'
            except ValueError:
                errors['purchase_price'] = 'Price must be a number'
        
        if errors:
            if is_json:
                return JsonResponse({'errors': errors}, status=400)
            return render(request, 'inventory/items/create.html', {
                'errors': errors,
                'data': data,
                'organization': organization,
            })
        
        try:
            # Create item
            item = InventoryItem.objects.create(
                organization=organization,
                name=data.get('name'),
                description=data.get('description', ''),
                sku=data.get('sku', ''),
                barcode=data.get('barcode', ''),
                asset_tag=data.get('asset_tag', ''),
                quantity=int(data.get('quantity', 0)),
                reorder_level=int(data.get('reorder_level', 0)),
                reorder_quantity=int(data.get('reorder_quantity', 1)),
                alert_on_low=bool(data.get('alert_on_low', True)),
                location=data.get('location', ''),
                condition=data.get('condition', 'good'),
                item_type=data.get('item_type', 'supply'),
                storage_instructions=data.get('storage_instructions', ''),
                purchase_price=float(purchase_price) if purchase_price else None,
                notes=data.get('notes', ''),
                created_by=request.user,
            )
            
            # Handle relationships
            category_id = data.get('category')
            if category_id:
                try:
                    category = InventoryCategory.objects.get(id=category_id, organization=organization)
                    item.category = category
                except InventoryCategory.DoesNotExist:
                    pass
            
            department_id = data.get('department')
            if department_id:
                try:
                    department = Department.objects.get(id=department_id, organization=organization)
                    item.department = department
                except Department.DoesNotExist:
                    pass
            
            vendor_id = data.get('vendor')
            if vendor_id:
                try:
                    vendor = InventoryVendor.objects.get(id=vendor_id, organization=organization)
                    item.vendor = vendor
                except InventoryVendor.DoesNotExist:
                    pass
            
            # Handle dates
            purchase_date = data.get('purchase_date')
            if purchase_date:
                try:
                    item.purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            warranty_expiry = data.get('warranty_expiry')
            if warranty_expiry:
                try:
                    item.warranty_expiry = datetime.strptime(warranty_expiry, '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            # Handle image (for form submissions)
            if not is_json and 'image' in request.FILES:
                item.image = request.FILES['image']
            
            item.save()
            
            # Create initial stock transaction
            if item.quantity > 0:
                InventoryTransaction.objects.create(
                    organization=organization,
                    item=item,
                    transaction_type='add',
                    quantity=item.quantity,
                    performed_by=request.user,
                    notes='Initial stock',
                    approved_by=request.user,
                    approved_at=timezone.now(),
                )
            
            if is_json:
                return JsonResponse({
                    'success': True,
                    'message': 'Item created successfully',
                    'item_id': str(item.id),
                    'item': {
                        'id': str(item.id),
                        'name': item.name,
                        'sku': item.sku,
                        'quantity': item.quantity,
                    }
                })
            
            messages.success(request, 'Item created successfully')
            return redirect('inventory_item_detail', item_id=item.id)
            
        except Exception as e:
            if is_json:
                return JsonResponse({'error': str(e)}, status=500)
            messages.error(request, f'Error creating item: {str(e)}')
            return render(request, 'inventory/items/create.html', {
                'data': data,
                'organization': organization,
            })
    
    # GET request - show form
    # Get options for dropdowns
    categories = InventoryCategory.objects.filter(organization=organization)
    departments = Department.objects.filter(organization=organization)
    vendors = InventoryVendor.objects.filter(organization=organization)
    
    context = {
        'categories': categories,
        'departments': departments,
        'vendors': vendors,
        'item_type_choices': InventoryItem.ITEM_TYPES,
        'condition_choices': InventoryItem.CONDITION_CHOICES,
    }
    
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return options for mobile app
        return JsonResponse({
            'categories': [
                {'id': str(c.id), 'name': c.name, 'category_type': c.category_type}
                for c in categories
            ],
            'departments': [
                {'id': str(d.id), 'name': d.name, 'code': d.code}
                for d in departments
            ],
            'vendors': [
                {'id': str(v.id), 'name': v.name}
                for v in vendors
            ],
            'item_types': InventoryItem.ITEM_TYPES,
            'conditions': InventoryItem.CONDITION_CHOICES,
        })
    
    return render(request, 'inventory/items/create.html', context)


@login_required
@require_http_methods(["GET", "POST", "PUT"])
def inventory_item_update_view(request, item_id):
    """Update inventory item - handles both form POST and JSON PUT"""
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
    
    if request.method in ['POST', 'PUT']:
        is_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
        
        if is_json:
            data = json.loads(request.body)
        else:
            data = request.POST.copy()
            if 'image' in request.FILES:
                data['image'] = request.FILES['image']
        
        # Validation
        errors = {}
        if not data.get('name', '').strip():
            errors['name'] = 'Item name is required'
        
        # Validate numeric fields
        for field in ['quantity', 'reorder_level', 'reorder_quantity']:
            if field in data:
                try:
                    value = int(data[field])
                    if value < 0:
                        errors[field] = f'{field.replace("_", " ").title()} cannot be negative'
                except ValueError:
                    errors[field] = f'{field.replace("_", " ").title()} must be a number'
        
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
            return render(request, 'inventory/items/edit.html', {
                'item': item,
                'errors': errors,
                'data': data,
            })
        
        try:
            # Update item fields
            item.name = data.get('name', item.name)
            item.description = data.get('description', item.description)
            item.sku = data.get('sku', item.sku)
            item.barcode = data.get('barcode', item.barcode)
            item.asset_tag = data.get('asset_tag', item.asset_tag)
            item.quantity = int(data.get('quantity', item.quantity))
            item.reorder_level = int(data.get('reorder_level', item.reorder_level))
            item.reorder_quantity = int(data.get('reorder_quantity', item.reorder_quantity))
            item.alert_on_low = bool(data.get('alert_on_low', item.alert_on_low))
            item.location = data.get('location', item.location)
            item.condition = data.get('condition', item.condition)
            item.item_type = data.get('item_type', item.item_type)
            item.storage_instructions = data.get('storage_instructions', item.storage_instructions)
            
            # Handle price
            purchase_price = data.get('purchase_price')
            if purchase_price:
                item.purchase_price = float(purchase_price)
            elif purchase_price == '':  # Clear price if empty string
                item.purchase_price = None
            
            item.notes = data.get('notes', item.notes)
            
            # Handle relationships
            category_id = data.get('category')
            if category_id:
                try:
                    category = InventoryCategory.objects.get(id=category_id, organization=organization)
                    item.category = category
                except InventoryCategory.DoesNotExist:
                    pass
            elif category_id == '':  # Clear category
                item.category = None
            
            department_id = data.get('department')
            if department_id:
                try:
                    department = Department.objects.get(id=department_id, organization=organization)
                    item.department = department
                except Department.DoesNotExist:
                    pass
            elif department_id == '':  # Clear department
                item.department = None
            
            vendor_id = data.get('vendor')
            if vendor_id:
                try:
                    vendor = InventoryVendor.objects.get(id=vendor_id, organization=organization)
                    item.vendor = vendor
                except InventoryVendor.DoesNotExist:
                    pass
            elif vendor_id == '':  # Clear vendor
                item.vendor = None
            
            # Handle dates
            for date_field in ['purchase_date', 'warranty_expiry']:
                date_value = data.get(date_field)
                if date_value:
                    try:
                        setattr(item, date_field, datetime.strptime(date_value, '%Y-%m-%d').date())
                    except ValueError:
                        pass
                elif date_value == '':  # Clear date
                    setattr(item, date_field, None)
            
            # Handle image (for form submissions)
            if not is_json:
                if 'image' in request.FILES:
                    item.image = request.FILES['image']
                elif 'clear_image' in data:  # Clear image if requested
                    item.image = None
            
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
            
            messages.success(request, 'Item updated successfully')
            return redirect('inventory_item_detail', item_id=item.id)
            
        except Exception as e:
            if is_json:
                return JsonResponse({'error': str(e)}, status=500)
            messages.error(request, f'Error updating item: {str(e)}')
            return render(request, 'inventory/items/edit.html', {
                'item': item,
                'data': data,
            })
    
    # GET request - show form with current data
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
@require_http_methods(["DELETE", "POST"])
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
    
    # Store item info for response
    item_name = item.name
    item_sku = item.sku
    
    # Delete item
    item.delete()
    
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            'success': True,
            'message': f"Item '{item_name}' has been deleted.",
            'deleted_item': {
                'id': item_id,
                'name': item_name,
                'sku': item_sku,
            }
        })
    
    messages.success(request, f"Item '{item_name}' has been deleted.")
    return redirect('inventory_item_list')


@login_required
def inventory_checkout_list_view(request):
    """List inventory checkouts - JSON for mobile, HTML for web"""
    organization = get_user_organization(request.user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")
    
    # Get filters
    status_filter = request.GET.get('status')
    member_id = request.GET.get('member')
    department_id = request.GET.get('department')
    overdue_only = request.GET.get('overdue') == 'true'
    
    # Build queryset
    checkouts = InventoryCheckout.objects.filter(organization=organization)
    
    # Apply filters
    if status_filter:
        checkouts = checkouts.filter(status=status_filter)
    
    if member_id:
        checkouts = checkouts.filter(member_id=member_id)
    
    if department_id:
        checkouts = checkouts.filter(department_id=department_id)
    
    if overdue_only:
        checkouts = checkouts.filter(status='overdue')
    
    # Order by
    sort_by = request.GET.get('sort', '-checkout_date')
    checkouts = checkouts.order_by(sort_by)
    
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return JSON for mobile
        data = [
            {
                'id': str(c.id),
                'item_name': c.item.name,
                'member_name': c.member.full_name,
                'quantity': c.quantity,
                'checkout_date': c.checkout_date.isoformat(),
                'due_date': c.due_date.isoformat() if c.due_date else None,
                'status': c.status,
                'is_overdue': c.is_overdue,
                'days_overdue': c.days_overdue,
                'purpose': c.purpose,
                'department': c.department.name if c.department else None,
            }
            for c in checkouts
        ]
        return JsonResponse({'checkouts': data})
    
    # Return HTML for web
    members = Member.objects.filter(organization=organization).order_by('last_name', 'first_name')
    departments = Department.objects.filter(organization=organization)
    
    return render(request, 'inventory/checkouts/list.html', {
        'checkouts': checkouts,
        'members': members,
        'departments': departments,
        'status_filter': status_filter,
        'member_id': member_id,
        'department_id': department_id,
        'overdue_only': overdue_only,
    })


@login_required
@require_http_methods(["GET", "POST"])
def inventory_checkout_create_view(request):
    """Create inventory checkout - handles both form POST and JSON POST"""
    organization = get_user_organization(request.user)
    
    if not organization:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'No organization assigned'}, status=400)
        return HttpResponseForbidden("No organization assigned")
    
    # Check permissions
    user = request.user
    can_checkout = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False) or
        getattr(user, "is_hod", False)
    )
    
    if not can_checkout:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Permission denied'}, status=403)
        return HttpResponseForbidden("Permission denied")
    
    if request.method == 'POST':
        is_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
        
        if is_json:
            data = json.loads(request.body)
        else:
            data = request.POST.copy()
        
        # Validation
        errors = {}
        
        # Validate required fields
        if not data.get('item'):
            errors['item'] = 'Item is required'
        
        if not data.get('member'):
            errors['member'] = 'Member is required'
        
        if not data.get('quantity'):
            errors['quantity'] = 'Quantity is required'
        else:
            try:
                quantity = int(data['quantity'])
                if quantity <= 0:
                    errors['quantity'] = 'Quantity must be greater than 0'
                
                # Check if item has enough stock
                if data.get('item'):
                    try:
                        item = InventoryItem.objects.get(id=data['item'], organization=organization)
                        if item.quantity < quantity:
                            errors['quantity'] = f'Only {item.quantity} available in stock'
                    except InventoryItem.DoesNotExist:
                        errors['item'] = 'Item not found'
            except ValueError:
                errors['quantity'] = 'Quantity must be a number'
        
        if not data.get('department'):
            errors['department'] = 'Department is required'
        
        if errors:
            if is_json:
                return JsonResponse({'errors': errors}, status=400)
            return render(request, 'inventory/checkouts/create.html', {
                'errors': errors,
                'data': data,
                'organization': organization,
            })
        
        try:
            # Get related objects
            item = InventoryItem.objects.get(id=data['item'], organization=organization)
            member = Member.objects.get(id=data['member'], organization=organization)
            department = Department.objects.get(id=data['department'], organization=organization)
            
            # Create checkout
            checkout = InventoryCheckout.objects.create(
                organization=organization,
                item=item,
                member=member,
                department=department,
                quantity=int(data['quantity']),
                purpose=data.get('purpose', ''),
                event_name=data.get('event_name', ''),
                due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None,
                status='active',
                created_by=request.user,
                approved_by=request.user,
                approved_at=timezone.now(),
                notes=data.get('notes', ''),
            )
            
            # Update item quantity
            item.quantity -= checkout.quantity
            if item.quantity < 0:
                item.quantity = 0
            item.save()
            
            # Create transaction
            InventoryTransaction.objects.create(
                organization=organization,
                item=item,
                transaction_type='checkout',
                quantity=checkout.quantity,
                from_department=department,
                performed_by=request.user,
                notes=f"Checked out to {member.full_name}. Purpose: {checkout.purpose}",
                approved_by=request.user,
                approved_at=timezone.now(),
            )
            
            if is_json:
                return JsonResponse({
                    'success': True,
                    'message': 'Item checked out successfully',
                    'checkout_id': str(checkout.id),
                    'checkout': {
                        'id': str(checkout.id),
                        'item_name': item.name,
                        'member_name': member.full_name,
                        'quantity': checkout.quantity,
                        'due_date': checkout.due_date.isoformat() if checkout.due_date else None,
                    }
                })
            
            messages.success(request, 'Item checked out successfully')
            return redirect('inventory_checkout_list')
            
        except Exception as e:
            if is_json:
                return JsonResponse({'error': str(e)}, status=500)
            messages.error(request, f'Error checking out item: {str(e)}')
            return render(request, 'inventory/checkouts/create.html', {
                'data': data,
                'organization': organization,
            })
    
    # GET request - show form
    items = InventoryItem.objects.filter(
        organization=organization,
        quantity__gt=0,
        is_active=True
    ).order_by('name')
    
    members = Member.objects.filter(organization=organization).order_by('last_name', 'first_name')
    departments = Department.objects.filter(organization=organization)
    
    context = {
        'items': items,
        'members': members,
        'departments': departments,
    }
    
    # YOUR EXISTING PATTERN
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # Return options for mobile app
        return JsonResponse({
            'items': [
                {
                    'id': str(i.id),
                    'name': i.name,
                    'quantity': i.quantity,
                    'sku': i.sku,
                }
                for i in items
            ],
            'members': [
                {
                    'id': str(m.id),
                    'full_name': m.full_name,
                    'email': m.email,
                }
                for m in members
            ],
            'departments': [
                {
                    'id': str(d.id),
                    'name': d.name,
                    'code': d.code,
                }
                for d in departments
            ],
        })
    
    return render(request, 'inventory/checkouts/create.html', context)



# inventory/views.py - ADD THESE VIEWS

@login_required
@require_http_methods(["POST"])
def inventory_checkout_return_view(request, checkout_id):
    """Process item return"""
    organization = get_user_organization(request.user)
    
    if not organization:
        return JsonResponse({'error': 'No organization assigned'}, status=400)
    
    try:
        checkout = InventoryCheckout.objects.get(
            id=checkout_id, 
            organization=organization
        )
        
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
        
        returned_quantity = int(request.POST.get('returned_quantity', 0))
        returned_condition = request.POST.get('returned_condition', 'good')
        return_notes = request.POST.get('return_notes', '')
        
        # Validate returned quantity
        if returned_quantity <= 0:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({'error': 'Quantity must be greater than 0'}, status=400)
            messages.error(request, 'Quantity must be greater than 0')
            return redirect('inventory_checkout_list')
        
        if returned_quantity > checkout.quantity:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({'error': f'Cannot return more than {checkout.quantity} units'}, status=400)
            messages.error(request, f'Cannot return more than {checkout.quantity} units')
            return redirect('inventory_checkout_list')
        
        # Update checkout
        checkout.returned_quantity = returned_quantity
        checkout.returned_condition = returned_condition
        checkout.return_notes = return_notes
        checkout.returned_at = timezone.now()
        
        if returned_quantity >= checkout.quantity:
            checkout.status = 'returned'
        else:
            checkout.status = 'active'  # Partial return
            checkout.quantity -= returned_quantity  # Update remaining quantity
        
        checkout.save()
        
        # Update item stock
        checkout.item.quantity += returned_quantity
        checkout.item.save()
        
        # Create transaction
        InventoryTransaction.objects.create(
            organization=organization,
            item=checkout.item,
            transaction_type='return',
            quantity=returned_quantity,
            performed_by=request.user,
            notes=f'Returned by {checkout.member.full_name}. Condition: {returned_condition}. Notes: {return_notes}',
            approved_by=request.user,
            approved_at=timezone.now(),
        )
        
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                'success': True,
                'message': f'Item returned successfully. {returned_quantity} units returned.',
                'checkout': {
                    'id': str(checkout.id),
                    'status': checkout.status,
                    'returned_quantity': checkout.returned_quantity,
                }
            })
        
        messages.success(request, f'Item returned successfully. {returned_quantity} units returned.')
        return redirect('inventory_checkout_list')
        
    except InventoryCheckout.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Checkout not found'}, status=404)
        messages.error(request, 'Checkout not found')
        return redirect('inventory_checkout_list')
    except ValueError:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Invalid quantity'}, status=400)
        messages.error(request, 'Invalid quantity')
        return redirect('inventory_checkout_list')


@login_required
@require_http_methods(["POST"])
def inventory_checkout_extend_view(request, checkout_id):
    """Extend checkout due date"""
    organization = get_user_organization(request.user)
    
    if not organization:
        return JsonResponse({'error': 'No organization assigned'}, status=400)
    
    try:
        checkout = InventoryCheckout.objects.get(
            id=checkout_id, 
            organization=organization
        )
        
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
        
        new_due_date = request.POST.get('new_due_date')
        extend_reason = request.POST.get('extend_reason', '')
        
        if not new_due_date:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({'error': 'New due date is required'}, status=400)
            messages.error(request, 'New due date is required')
            return redirect('inventory_checkout_list')
        
        # Validate date
        try:
            due_date = datetime.strptime(new_due_date, '%Y-%m-%d').date()
            if due_date < timezone.now().date():
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({'error': 'Due date cannot be in the past'}, status=400)
                messages.error(request, 'Due date cannot be in the past')
                return redirect('inventory_checkout_list')
        except ValueError:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({'error': 'Invalid date format'}, status=400)
            messages.error(request, 'Invalid date format')
            return redirect('inventory_checkout_list')
        
        # Update checkout
        old_due_date = checkout.due_date
        checkout.due_date = new_due_date
        
        # Add extension note
        extension_note = f"\n\n[Due date extended on {timezone.now().strftime('%Y-%m-%d %H:%M')}] "
        extension_note += f"From: {old_due_date.strftime('%Y-%m-%d') if old_due_date else 'Not set'} "
        extension_note += f"To: {new_due_date}"
        if extend_reason:
            extension_note += f"\nReason: {extend_reason}"
        
        checkout.notes = (checkout.notes or '') + extension_note
        checkout.save()
        
        # Create transaction note
        InventoryTransaction.objects.create(
            organization=organization,
            item=checkout.item,
            transaction_type='adjust',
            quantity=0,
            performed_by=request.user,
            notes=f'Due date extended for {checkout.member.full_name}. New due date: {new_due_date}',
            approved_by=request.user,
            approved_at=timezone.now(),
        )
        
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                'success': True,
                'message': f'Due date extended to {new_due_date}',
                'checkout': {
                    'id': str(checkout.id),
                    'due_date': new_due_date,
                }
            })
        
        messages.success(request, f'Due date extended to {new_due_date}')
        return redirect('inventory_checkout_list')
        
    except InventoryCheckout.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Checkout not found'}, status=404)
        messages.error(request, 'Checkout not found')
        return redirect('inventory_checkout_list')



















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

# ==================== MOBILE VOUCHER API VIEWS ====================

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_list_api_view(request):
    """Mobile API for listing vouchers."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get query parameters
    status_filter = request.query_params.get('status')
    search = request.query_params.get('search', '')
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    # Build queryset
    vouchers = Voucher.objects.filter(organization=organization)
    
    # Apply filters
    if status_filter and status_filter != 'all':
        vouchers = vouchers.filter(status=status_filter)
    
    if search:
        vouchers = vouchers.filter(
            Q(voucher_number__icontains=search) |
            Q(purpose__icontains=search) |
            Q(payable_to__icontains=search) |
            Q(requester_name_department__icontains=search)
        )
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            vouchers = vouchers.filter(date_prepared__gte=start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            vouchers = vouchers.filter(date_prepared__lte=end)
        except ValueError:
            pass
    
    # Order by date prepared (most recent first)
    vouchers = vouchers.order_by('-date_prepared', '-created_at')
    
    # Serialize data
    data = [
        {
            'id': str(v.id),
            'voucher_number': v.voucher_number,
            'title': v.title or '',
            'purpose': v.purpose[:100] + '...' if len(v.purpose) > 100 else v.purpose,
            'requester_name_department': v.requester_name_department,
            'amount_in_figures': float(v.amount_in_figures) if v.amount_in_figures else 0,
            'currency': v.currency,
            'status': v.status,
            'status_display': v.get_status_display(),
            'date_prepared': v.date_prepared.isoformat() if v.date_prepared else None,
            'needed_by': v.needed_by.isoformat() if v.needed_by else None,
            'is_overdue': v.is_overdue,
            'days_open': v.days_open,
        }
        for v in vouchers
    ]
    
    return Response({
        'success': True,
        'count': len(data),
        'vouchers': data
    })

    
@api_view(['GET', 'POST'])  # Allow both GET and POST
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_create_api_view(request):
    """Mobile API for creating vouchers - GET for form data, POST for creation."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # ========== HANDLE GET REQUEST (Form Data) ==========
    if request.method == 'GET':
        # Return form structure and available templates for mobile app
        templates = VoucherTemplate.objects.filter(organization=organization).order_by('-is_default', '-created_at')
        
        templates_data = [
            {
                'id': str(t.id),
                'name': t.name,
                'is_default': t.is_default,
                'church_name': t.church_name,
                'form_title': t.form_title,
                'description': t.description,
                'show_urgent_items': t.show_urgent_items,
                'show_important_items': t.show_important_items,
                'show_permissible_items': t.show_permissible_items,
                'default_usage_commitment': t.default_usage_commitment,
                'default_maintenance_commitment': t.default_maintenance_commitment,
                'created_at': t.created_at.isoformat(),
            }
            for t in templates
        ]
        
        # Default form fields structure
        form_fields = [
            {'name': 'template_id', 'label': 'Template', 'type': 'select', 
             'options': templates_data, 'required': True},
            {'name': 'purpose', 'label': 'Purpose', 'type': 'textarea', 'required': True},
            {'name': 'urgent_items', 'label': 'URGENT Items', 'type': 'textarea', 'required': False},
            {'name': 'important_items', 'label': 'IMPORTANT Items', 'type': 'textarea', 'required': False},
            {'name': 'permissible_items', 'label': 'PERMISSIBLE Items', 'type': 'textarea', 'required': False},
            {'name': 'amount_in_words', 'label': 'Amount in Words', 'type': 'text', 'required': True},
            {'name': 'amount_in_figures', 'label': 'Amount in Figures', 'type': 'number', 'required': True},
            {'name': 'currency', 'label': 'Currency', 'type': 'text', 'default': 'NGN', 'required': True},
            {'name': 'payable_to', 'label': 'Payable To', 'type': 'text', 'required': True},
            {'name': 'payee_phone', 'label': 'Payee Phone', 'type': 'tel', 'required': True},
            {'name': 'payment_method', 'label': 'Payment Method', 'type': 'select', 
             'options': [{'value': 'transfer', 'label': 'Bank Transfer'}, 
                        {'value': 'cash', 'label': 'Cash'},
                        {'value': 'cheque', 'label': 'Cheque'}],
             'required': True},
            {'name': 'needed_by', 'label': 'Needed By', 'type': 'date', 'required': True},
            {'name': 'usage_commitment', 'label': 'Usage Commitment', 'type': 'text', 'required': False},
            {'name': 'maintenance_commitment', 'label': 'Maintenance Commitment', 'type': 'text', 'required': False},
            {'name': 'requester_signature', 'label': 'Requester Signature', 'type': 'text', 'required': False},
            {'name': 'requester_phone', 'label': 'Requester Phone', 'type': 'tel', 'required': False},
        ]
        
        # Try to get default template to pre-fill commitments
        default_template = None
        for template in templates:
            if template.is_default:
                default_template = template
                break
        
        # If no default, use first template
        if not default_template and templates:
            default_template = templates[0]
        
        # Prepare default values based on template
        default_values = {}
        if default_template:
            default_values = {
                'template_id': str(default_template.id),
                'usage_commitment': default_template.default_usage_commitment or '',
                'maintenance_commitment': default_template.default_maintenance_commitment or '',
            }
        
        return Response({
            'success': True,
            'form_fields': form_fields,
            'templates': templates_data,
            'default_values': default_values,
            'payment_methods': [{'value': 'transfer', 'label': 'Bank Transfer'}, 
                               {'value': 'cash', 'label': 'Cash'},
                               {'value': 'cheque', 'label': 'Cheque'}],
            'currencies': [{'value': 'NGN', 'label': 'Nigerian Naira'}],
            'message': 'Form data retrieved successfully'
        })
    
    # ========== HANDLE POST REQUEST (Create Voucher) ==========
    # Your existing POST logic remains the same
    # Get template
    template_id = request.data.get('template_id')
    if template_id:
        try:
            template = VoucherTemplate.objects.get(id=template_id, organization=organization)
        except VoucherTemplate.DoesNotExist:
            template = None
    else:
        # Try to get default template
        try:
            template = VoucherTemplate.objects.get(organization=organization, is_default=True)
        except VoucherTemplate.DoesNotExist:
            template = VoucherTemplate.objects.filter(organization=organization).first()
    
    if not template:
        return Response(
            {'error': 'No voucher template available. Please create a template first.'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate data
    data = request.data.copy()
    
    # Map mobile field names to model field names if needed
    if 'amount' in data:
        data['amount_in_figures'] = data.pop('amount')
    
    if 'amount_in_words' not in data and 'amount_in_figures' in data:
        # Auto-generate amount in words if not provided
        try:
            from num2words import num2words
            amount = float(data['amount_in_figures'])
            data['amount_in_words'] = num2words(amount, lang='en').title()
        except:
            pass
    
    # Create voucher
    try:
        # Parse needed_by date
        needed_by = data.get('needed_by')
        needed_date = None
        if needed_by:
            try:
                needed_date = datetime.strptime(needed_by, '%Y-%m-%d').date()
            except ValueError:
                needed_date = datetime.now().date() + timedelta(days=7)
        else:
            needed_date = datetime.now().date() + timedelta(days=7)
        
        # Parse amount
        amount_str = data.get('amount_in_figures', '0')
        try:
            amount = Decimal(amount_str)
        except (InvalidOperation, ValueError, TypeError):
            amount = Decimal('0.00')
        
        voucher = Voucher.objects.create(
            organization=organization,
            template=template,
            requested_by=request.user,
            requester_name_department=data.get('requester_name_department', f"{request.user.get_full_name()}"),
            purpose=data.get('purpose', ''),
            urgent_items=data.get('urgent_items', ''),
            important_items=data.get('important_items', ''),
            permissible_items=data.get('permissible_items', ''),
            amount_in_words=data.get('amount_in_words', ''),
            amount_in_figures=amount,
            currency=data.get('currency', 'NGN'),
            payable_to=data.get('payable_to', ''),
            payee_phone=data.get('payee_phone', ''),
            payment_method=data.get('payment_method', 'transfer'),
            needed_by=needed_date,
            usage_commitment=data.get('usage_commitment', template.default_usage_commitment or ''),
            maintenance_commitment=data.get('maintenance_commitment', template.default_maintenance_commitment or ''),
            requester_signature=data.get('requester_signature', ''),
            requester_signed_date=datetime.now().date() if data.get('requester_signature') else None,
            requester_phone=data.get('requester_phone', ''),
            status='draft',
        )
        
        # Handle signature image if provided (base64)
        signature_image = data.get('signature_image')
        if signature_image and signature_image.startswith('data:image/'):
            try:
                format, imgstr = signature_image.split(';base64,')
                ext = format.split('/')[-1]
                data_file = ContentFile(base64.b64decode(imgstr))
                filename = f'signature_{voucher.voucher_number}.{ext}'
                voucher.requester_signature_image.save(filename, data_file, save=True)
            except Exception as e:
                print(f"Error saving signature image: {e}")
        
        return Response({
            'success': True,
            'message': 'Voucher created successfully',
            'voucher_id': str(voucher.id),
            'voucher_number': voucher.voucher_number,
            'status': voucher.status
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )



# FIXED VERSION of voucher_detail_api_view
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_detail_api_view(request, voucher_id):
    """Mobile API for getting voucher details."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=organization)
    except Voucher.DoesNotExist:
        return Response(
            {'error': 'Voucher not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Helper function to safely get user ID
    def get_user_id(user_obj):
        if not user_obj:
            return None
        # Try different ways to get ID
        if hasattr(user_obj, 'id'):
            return str(user_obj.id)
        elif hasattr(user_obj, 'pk'):
            return str(user_obj.pk)
        elif hasattr(user_obj, '_id'):
            return str(user_obj._id)
        return None
    
    # Build requested_by data safely
    requested_by_data = None
    if voucher.requested_by:
        requested_by_data = {
            'id': get_user_id(voucher.requested_by),  # Use helper function
            'name': voucher.requested_by.get_full_name() if hasattr(voucher.requested_by, 'get_full_name') else 
                    getattr(voucher.requested_by, 'username', 'Unknown'),
            'email': getattr(voucher.requested_by, 'email', None),
        }
    
    # Serialize voucher data
    data = {
        'id': str(voucher.id),
        'voucher_number': voucher.voucher_number,
        'title': voucher.title,
        'date_prepared': voucher.date_prepared.isoformat() if voucher.date_prepared else None,
        'requester_name_department': voucher.requester_name_department,
        'purpose': voucher.purpose,
        'urgent_items': voucher.urgent_items,
        'important_items': voucher.important_items,
        'permissible_items': voucher.permissible_items,
        'amount_in_words': voucher.amount_in_words,
        'amount_in_figures': float(voucher.amount_in_figures) if voucher.amount_in_figures else 0,
        'currency': voucher.currency,
        'payable_to': voucher.payable_to,
        'payee_phone': voucher.payee_phone,
        'payment_method': voucher.payment_method,
        'payment_method_display': voucher.get_payment_method_display(),
        'needed_by': voucher.needed_by.isoformat() if voucher.needed_by else None,
        'usage_commitment': voucher.usage_commitment,
        'maintenance_commitment': voucher.maintenance_commitment,
        'requester_signature': voucher.requester_signature,
        'requester_signed_date': voucher.requester_signed_date.isoformat() if voucher.requester_signed_date else None,
        'requester_phone': voucher.requester_phone,
        
        # Template information
        'template': {
            'id': str(voucher.template.id) if voucher.template else None,
            'name': voucher.template.name if voucher.template else None,
            'church_name': voucher.template.church_name if voucher.template else None,
            'form_title': voucher.template.form_title if voucher.template else None,
        } if voucher.template else None,
        
        # Status information
        'status': voucher.status,
        'status_display': voucher.get_status_display(),
        
        # Finance Office section
        'funds_approved': float(voucher.funds_approved) if voucher.funds_approved else None,
        'funds_denied': float(voucher.funds_denied) if voucher.funds_denied else None,
        'approved_amount': float(voucher.approved_amount) if voucher.approved_amount else None,
        'finance_remarks': voucher.finance_remarks,
        'finance_signature': voucher.finance_signature,
        'approved_by': voucher.approved_by.get_full_name() if voucher.approved_by and hasattr(voucher.approved_by, 'get_full_name') else None,
        'approved_date': voucher.approved_date.isoformat() if voucher.approved_date else None,
        
        # Payment info
        'paid_amount': float(voucher.paid_amount) if voucher.paid_amount else None,
        'paid_date': voucher.paid_date.isoformat() if voucher.paid_date else None,
        'payment_reference': voucher.payment_reference,
        
        # Calculated properties
        'is_approved': voucher.is_approved,
        'is_paid': voucher.is_paid,
        'is_pending': voucher.is_pending,
        'is_overdue': voucher.is_overdue,
        'days_open': voucher.days_open,
        'total_items_count': voucher.total_items_count,
        
        # Requested by info - USING SAFE VERSION
        'requested_by': requested_by_data,
        
        # Attachments
        'attachments': [
            {
                'id': str(att.id),
                'file_name': att.file_name,
                'file_type': att.file_type,
                'file_size': att.file_size,
                'description': att.description,
                'uploaded_at': att.uploaded_at.isoformat(),
            }
            for att in voucher.attachments.all()
        ],
        
        # Comments - ALSO NEED TO FIX HERE
        'comments': [
            {
                'id': str(comment.id),
                'author': {
                    'id': get_user_id(comment.author),  # Use helper here too
                    'name': comment.author.get_full_name() if comment.author and hasattr(comment.author, 'get_full_name') else 
                            getattr(comment.author, 'username', 'Unknown'),
                } if comment.author else None,
                'comment': comment.comment,
                'is_internal': comment.is_internal,
                'created_at': comment.created_at.isoformat(),
            }
            for comment in voucher.comments.all()
        ],
    }
    
    return Response(data)

@api_view(['PUT', 'PATCH'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_update_api_view(request, voucher_id):
    """Mobile API for updating vouchers."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=organization)
    except Voucher.DoesNotExist:
        return Response(
            {'error': 'Voucher not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if voucher can be updated
    if voucher.status != 'draft':
        return Response(
            {'error': f'Cannot update voucher with status: {voucher.status}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    data = request.data.copy()
    
    try:
        # Update fields
        if 'purpose' in data:
            voucher.purpose = data['purpose']
        if 'urgent_items' in data:
            voucher.urgent_items = data['urgent_items']
        if 'important_items' in data:
            voucher.important_items = data['important_items']
        if 'permissible_items' in data:
            voucher.permissible_items = data['permissible_items']
        if 'amount_in_words' in data:
            voucher.amount_in_words = data['amount_in_words']
        if 'amount_in_figures' in data:
            try:
                voucher.amount_in_figures = Decimal(data['amount_in_figures'])
            except (InvalidOperation, ValueError, TypeError):
                pass
        if 'currency' in data:
            voucher.currency = data['currency']
        if 'payable_to' in data:
            voucher.payable_to = data['payable_to']
        if 'payee_phone' in data:
            voucher.payee_phone = data['payee_phone']
        if 'payment_method' in data:
            voucher.payment_method = data['payment_method']
        if 'needed_by' in data:
            try:
                needed_date = datetime.strptime(data['needed_by'], '%Y-%m-%d').date()
                voucher.needed_by = needed_date
            except ValueError:
                pass
        if 'usage_commitment' in data:
            voucher.usage_commitment = data['usage_commitment']
        if 'maintenance_commitment' in data:
            voucher.maintenance_commitment = data['maintenance_commitment']
        if 'requester_signature' in data:
            voucher.requester_signature = data['requester_signature']
        if 'requester_phone' in data:
            voucher.requester_phone = data['requester_phone']
        
        voucher.save()
        
        return Response({
            'success': True,
            'message': 'Voucher updated successfully',
            'voucher_id': str(voucher.id),
            'voucher_number': voucher.voucher_number,
            'status': voucher.status
        })
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_delete_api_view(request, voucher_id):
    """Mobile API for deleting vouchers."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=organization)
    except Voucher.DoesNotExist:
        return Response(
            {'error': 'Voucher not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if voucher can be deleted
    if voucher.status != 'draft':
        return Response(
            {'error': f'Cannot delete voucher with status: {voucher.status}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        voucher_number = voucher.voucher_number
        voucher.delete()
        
        return Response({
            'success': True,
            'message': f'Voucher {voucher_number} deleted successfully'
        })
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_submit_api_view(request, voucher_id):
    """Mobile API for submitting vouchers for approval."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=organization)
    except Voucher.DoesNotExist:
        return Response(
            {'error': 'Voucher not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if voucher can be submitted
    if voucher.status != 'draft':
        return Response(
            {'error': f'Cannot submit voucher with status: {voucher.status}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate required fields
    required_fields = ['purpose', 'amount_in_figures', 'amount_in_words', 'payable_to']
    missing_fields = []
    for field in required_fields:
        value = getattr(voucher, field, '')
        if not value or (isinstance(value, Decimal) and value == Decimal('0.00')):
            missing_fields.append(field)
    
    if missing_fields:
        return Response({
            'error': 'Missing required fields',
            'missing_fields': missing_fields
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        if voucher.submit_for_approval():
            return Response({
                'success': True,
                'message': 'Voucher submitted for approval',
                'voucher_id': str(voucher.id),
                'voucher_number': voucher.voucher_number,
                'status': voucher.status
            })
        else:
            return Response(
                {'error': 'Failed to submit voucher for approval'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )


from decimal import Decimal, InvalidOperation

from decimal import Decimal, InvalidOperation

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_approve_api_view(request, voucher_id):
    """Mobile API for approving vouchers."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=organization)
    except Voucher.DoesNotExist:
        return Response(
            {'error': 'Voucher not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user has permission to approve
    can_approve = (
        request.user.is_staff or 
        getattr(request.user, 'is_admin', False) or 
        getattr(request.user, 'is_finance', False)
    )
    
    if not can_approve:
        return Response(
            {'error': 'Permission denied. You cannot approve vouchers.'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Check if voucher can be approved
    if voucher.status not in ['submitted', 'draft']:
        return Response(
            {'error': f'Cannot approve voucher with status: {voucher.status}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    data = request.data
    
    try:
        approved_amount = data.get('approved_amount')
        finance_remarks = data.get('finance_remarks', '')
        
        # Handle approved_amount conversion
        approved_amount_decimal = None
        if approved_amount is not None:
            # Convert to string first to avoid float issues
            try:
                if isinstance(approved_amount, (int, float)):
                    approved_amount_str = str(approved_amount)
                else:
                    approved_amount_str = str(approved_amount)
                
                approved_amount_decimal = Decimal(approved_amount_str)
            except (InvalidOperation, ValueError, TypeError) as e:
                print(f"Error converting approved_amount: {e}")
                # Use voucher amount as fallback
                approved_amount_decimal = voucher.amount_in_figures
        else:
            # If no amount provided, use voucher amount
            approved_amount_decimal = voucher.amount_in_figures
        
        print(f"Approving voucher {voucher_id}:")
        print(f"  - Requested amount: {approved_amount}")
        print(f"  - Converted to Decimal: {approved_amount_decimal}")
        print(f"  - Voucher amount: {voucher.amount_in_figures}")
        print(f"  - Remarks: {finance_remarks}")
        
        # Call the approve method
        if voucher.approve(request.user, approved_amount_decimal, finance_remarks):
            # Refresh the voucher from database to get updated data
            voucher.refresh_from_db()
            
            # Return the updated voucher data
            response_data = {
                'success': True,
                'message': 'Voucher approved successfully',
                'voucher_id': str(voucher.id),
                'voucher_number': voucher.voucher_number,
                'status': voucher.status,
                'approved_amount': float(voucher.approved_amount) if voucher.approved_amount else None,
                'approved_date': voucher.approved_date.isoformat() if voucher.approved_date else None,
                'finance_remarks': voucher.finance_remarks
            }
            
            # Add approved_by info safely
            if voucher.approved_by:
                # Use pk instead of id since Django User model uses pk
                response_data['approved_by'] = {
                    'id': str(voucher.approved_by.pk),  # Changed to pk
                    'name': voucher.approved_by.get_full_name() if hasattr(voucher.approved_by, 'get_full_name') else str(voucher.approved_by),
                    'email': voucher.approved_by.email if hasattr(voucher.approved_by, 'email') else None
                }
            
            return Response(response_data)
        else:
            return Response(
                {'error': 'Failed to approve voucher. Check server logs.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
    except Exception as e:
        print(f"Exception in voucher_approve_api_view: {e}")
        print(f"Exception type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        return Response(
            {'error': f'Internal server error: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_reject_api_view(request, voucher_id):
    """Mobile API for rejecting vouchers."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=organization)
    except Voucher.DoesNotExist:
        return Response(
            {'error': 'Voucher not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user has permission to reject
    can_reject = (
        request.user.is_staff or 
        getattr(request.user, 'is_admin', False) or 
        getattr(request.user, 'is_finance', False)
    )
    
    if not can_reject:
        return Response(
            {'error': 'Permission denied. You cannot reject vouchers.'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Check if voucher can be rejected
    if voucher.status not in ['submitted', 'draft']:
        return Response(
            {'error': f'Cannot reject voucher with status: {voucher.status}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    data = request.data
    rejection_reason = data.get('rejection_reason', 'Rejected')
    
    try:
        if voucher.reject(request.user, rejection_reason):
            return Response({
                'success': True,
                'message': 'Voucher rejected',
                'voucher_id': str(voucher.id),
                'voucher_number': voucher.voucher_number,
                'status': voucher.status
            })
        else:
            return Response(
                {'error': 'Failed to reject voucher'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_pay_api_view(request, voucher_id):
    """Mobile API for marking vouchers as paid."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=organization)
    except Voucher.DoesNotExist:
        return Response(
            {'error': 'Voucher not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user has permission to mark as paid
    can_pay = (
        request.user.is_staff or 
        getattr(request.user, 'is_admin', False) or 
        getattr(request.user, 'is_finance', False)
    )
    
    if not can_pay:
        return Response(
            {'error': 'Permission denied. You cannot mark vouchers as paid.'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Check if voucher can be marked as paid
    if voucher.status != 'approved':
        return Response(
            {'error': f'Cannot mark voucher as paid with status: {voucher.status}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    data = request.data
    
    try:
        paid_amount = data.get('paid_amount')
        payment_reference = data.get('payment_reference', '')
        
        if paid_amount:
            try:
                paid_amount = Decimal(paid_amount)
            except (InvalidOperation, ValueError, TypeError):
                paid_amount = voucher.approved_amount or voucher.amount_in_figures
        else:
            paid_amount = voucher.approved_amount or voucher.amount_in_figures
        
        if voucher.mark_as_paid(paid_amount, payment_reference):
            return Response({
                'success': True,
                'message': 'Voucher marked as paid',
                'voucher_id': str(voucher.id),
                'voucher_number': voucher.voucher_number,
                'status': voucher.status,
                'paid_amount': float(voucher.paid_amount) if voucher.paid_amount else None,
                'payment_reference': voucher.payment_reference
            })
        else:
            return Response(
                {'error': 'Failed to mark voucher as paid'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_dashboard_api_view(request):
    """Mobile API for voucher dashboard statistics."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get statistics
    vouchers = Voucher.objects.filter(organization=organization)
    
    stats = {
        'total': vouchers.count(),
        'draft': vouchers.filter(status='draft').count(),
        'submitted': vouchers.filter(status='submitted').count(),
        'approved': vouchers.filter(status='approved').count(),
        'paid': vouchers.filter(status='paid').count(),
        'rejected': vouchers.filter(status='rejected').count(),
        'total_amount': float(vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or 0),
        'approved_amount': float(vouchers.filter(status='approved').aggregate(Sum('approved_amount'))['approved_amount__sum'] or 0),
        'paid_amount': float(vouchers.filter(status='paid').aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0),
        'overdue': vouchers.filter(status__in=['submitted', 'approved']).filter(needed_by__lt=datetime.now().date()).count(),
    }
    
    return Response({
        'success': True,
        'stats': stats
    })

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_template_list_api_view(request):
    """Mobile API for listing voucher templates."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    templates = VoucherTemplate.objects.filter(organization=organization).order_by('-is_default', '-created_at')
    
    data = [
        {
            'id': str(t.id),
            'name': t.name,
            'is_default': t.is_default,
            'church_name': t.church_name,
            'form_title': t.form_title,
            'description': t.description,
            'show_urgent_items': t.show_urgent_items,
            'show_important_items': t.show_important_items,
            'show_permissible_items': t.show_permissible_items,
            'default_usage_commitment': t.default_usage_commitment,
            'default_maintenance_commitment': t.default_maintenance_commitment,
            'created_at': t.created_at.isoformat(),
        }
        for t in templates
    ]
    
    return Response({
        'success': True,
        'templates': data,
        'count': len(data)
    })

# Optional: Add comment and attachment endpoints
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_add_comment_api_view(request, voucher_id):
    """Mobile API for adding comments to vouchers."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        voucher = Voucher.objects.get(id=voucher_id, organization=organization)
    except Voucher.DoesNotExist:
        return Response(
            {'error': 'Voucher not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    data = request.data
    comment_text = data.get('comment', '').strip()
    is_internal = data.get('is_internal', False)
    
    if not comment_text:
        return Response(
            {'error': 'Comment text is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        comment = VoucherComment.objects.create(
            voucher=voucher,
            author=request.user,
            comment=comment_text,
            is_internal=is_internal
        )
        
        return Response({
            'success': True,
            'message': 'Comment added successfully',
            'comment_id': str(comment.id),
            'comment': {
                'id': str(comment.id),
                'author': comment.author.get_full_name() if comment.author else None,
                'comment': comment.comment,
                'is_internal': comment.is_internal,
                'created_at': comment.created_at.isoformat(),
            }
        })
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )



# In your views.py - Add these imports at the top
from django.db.models import Count, Sum, Avg, Q
from datetime import datetime, timedelta
from django.utils import timezone
from decimal import Decimal

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_reports_api_view(request):
    """Mobile API for voucher reports and analytics - FIXED VERSION."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get period from query parameters
    period = request.query_params.get('period', 'month')
    
    # Calculate date range based on period
    today = timezone.now().date()
    if period == 'month':
        start_date = today.replace(day=1)
    elif period == 'quarter':
        current_month = today.month
        quarter_start_month = ((current_month - 1) // 3) * 3 + 1
        start_date = today.replace(month=quarter_start_month, day=1)
    else:  # year
        start_date = today.replace(month=1, day=1)
    
    # Get vouchers for the period
    vouchers = Voucher.objects.filter(
        organization=organization,
        date_prepared__gte=start_date,
        date_prepared__lte=today
    )
    
    # Calculate summary statistics
    total_vouchers = vouchers.count()
    total_amount = vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00')
    approved_count = vouchers.filter(status='approved').count()
    paid_count = vouchers.filter(status='paid').count()
    paid_amount = vouchers.filter(status='paid').aggregate(Sum('approved_amount'))['approved_amount__sum'] or Decimal('0.00')
    
    # Overdue vouchers
    overdue_vouchers = vouchers.filter(
        Q(status='submitted') | Q(status='approved'),
        needed_by__lt=today
    ).count()
    
    # Monthly trend (last 6 months)
    monthly_trend = []
    for i in range(5, -1, -1):
        month_date = today.replace(day=1) - timedelta(days=30*i)
        month_start = month_date.replace(day=1)
        if i == 0:
            month_end = today
        else:
            next_month = month_start + timedelta(days=32)
            month_end = next_month.replace(day=1) - timedelta(days=1)
        
        month_vouchers = vouchers.filter(
            date_prepared__gte=month_start,
            date_prepared__lte=month_end
        )
        
        monthly_trend.append({
            'month': month_start.strftime('%b %Y'),
            'count': month_vouchers.count(),
            'amount': float(month_vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00'))
        })
    
    # Department breakdown - FIXED VERSION
    department_breakdown = []
    
    # Get all departments in the organization
    departments = Department.objects.filter(organization=organization)
    
    for dept in departments:
        # Get members in this department
        department_members = Member.objects.filter(
            organization=organization,
            departments=dept
        ).values_list('user_id', flat=True)  # Get user IDs
        
        if department_members:
            # Get vouchers created by these members
            dept_vouchers = vouchers.filter(
                requested_by_id__in=department_members
            )
            
            if dept_vouchers.exists():
                dept_amount = dept_vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00')
                
                department_breakdown.append({
                    'department': dept.name,
                    'count': dept_vouchers.count(),
                    'amount': float(dept_amount)
                })
    
    # Sort by count descending and limit to top 5
    department_breakdown = sorted(department_breakdown, key=lambda x: x['count'], reverse=True)[:5]
    
    # Status breakdown
    status_breakdown = []
    for status_code, status_name in Voucher.STATUS_CHOICES:
        status_vouchers = vouchers.filter(status=status_code)
        if status_vouchers.exists():
            status_amount = status_vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00')
            status_breakdown.append({
                'status': status_name,
                'count': status_vouchers.count(),
                'amount': float(status_amount)
            })
    
    # Payment method breakdown
    payment_methods = []
    for method_code, method_name in Voucher.PAYMENT_METHOD_CHOICES:
        method_vouchers = vouchers.filter(payment_method=method_code)
        if method_vouchers.exists():
            payment_methods.append({
                'method': method_name,
                'count': method_vouchers.count(),
                'amount': float(method_vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00'))
            })
    
    # Recent activity
    recent_vouchers_list = []
    for voucher in vouchers.order_by('-date_prepared')[:5]:
        recent_vouchers_list.append({
            'id': str(voucher.id),
            'voucher_number': voucher.voucher_number,
            'purpose': voucher.purpose[:50] + '...' if len(voucher.purpose) > 50 else voucher.purpose,
            'amount_in_figures': float(voucher.amount_in_figures) if voucher.amount_in_figures else 0,
            'status': voucher.status,
            'status_display': voucher.get_status_display(),
            'date_prepared': voucher.date_prepared.isoformat() if voucher.date_prepared else None,
            'requester_name_department': voucher.requester_name_department,
        })
    
    # Build response
    report_data = {
        'summary': {
            'total_vouchers': total_vouchers,
            'total_amount': float(total_amount),
            'approved': approved_count,
            'paid': paid_count,
            'paid_amount': float(paid_amount),
            'overdue': overdue_vouchers,
            'avg_processing_days': 0,  # Skip for now to avoid complexity
            'approval_rate': round((approved_count / total_vouchers * 100) if total_vouchers > 0 else 0, 1),
            'payment_rate': round((paid_count / approved_count * 100) if approved_count > 0 else 0, 1),
        },
        'monthly_trend': monthly_trend,
        'department_breakdown': department_breakdown,
        'status_breakdown': status_breakdown,
        'payment_methods': payment_methods,
        'period': {
            'type': period,
            'start_date': start_date.isoformat(),
            'end_date': today.isoformat(),
            'display': f"{start_date.strftime('%b %d, %Y')} to {today.strftime('%b %d, %Y')}"
        },
        'recent_activity': recent_vouchers_list,
    }
    
    return Response({
        'success': True,
        'report': report_data
    })


# In your church/views.py - Add these report views
# Add these imports at the very top of your views.py
from django.db.models import Count, Sum, Avg, Min, Max, Q, F
from datetime import datetime, timedelta
from django.utils import timezone
from decimal import Decimal

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def pending_approvals_report_view(request):
    """Report for vouchers pending approval - FIXED VERSION."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response({'error': 'No organization assigned'}, status=400)
    
    # Get vouchers submitted but not yet approved
    pending_vouchers = Voucher.objects.filter(
        organization=organization,
        status='submitted'
    ).order_by('-date_prepared')
    
    # Group by department/requester
    departments = {}
    for voucher in pending_vouchers:
        # Extract department from requester_name_department
        if '/' in voucher.requester_name_department:
            dept = voucher.requester_name_department.split('/')[-1].strip()
        else:
            dept = 'General'
        
        if dept not in departments:
            departments[dept] = {
                'count': 0,
                'total_amount': Decimal('0'),
                'vouchers': []
            }
        
        departments[dept]['count'] += 1
        departments[dept]['total_amount'] += voucher.amount_in_figures
        
        # Calculate days pending
        days_pending = (timezone.now().date() - voucher.date_prepared).days if voucher.date_prepared else 0
        
        departments[dept]['vouchers'].append({
            'id': str(voucher.id),
            'voucher_number': voucher.voucher_number,
            'purpose': voucher.purpose,
            'amount': float(voucher.amount_in_figures),
            'date_prepared': voucher.date_prepared.isoformat() if voucher.date_prepared else None,
            'requester': voucher.requester_name_department,
            'days_pending': days_pending
        })
    
    # Summary stats
    total_pending = pending_vouchers.count()
    total_amount = pending_vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00')
    
    # Get oldest pending voucher
    oldest_voucher = pending_vouchers.order_by('date_prepared').first()
    
    summary = {
        'total_pending': total_pending,
        'total_amount': float(total_amount),
        'oldest_pending': oldest_voucher.date_prepared.isoformat() if oldest_voucher and oldest_voucher.date_prepared else None,
        'by_department': [
            {
                'department': dept,
                'count': data['count'],
                'total_amount': float(data['total_amount']),
                'percentage': round((data['count'] / total_pending) * 100, 1) if total_pending > 0 else 0
            }
            for dept, data in departments.items()
        ]
    }
    
    return Response({
        'success': True,
        'report': {
            'title': 'Pending Approvals Report',
            'period': 'Current',
            'generated_at': timezone.now().isoformat(),
            'summary': summary,
            'detailed': {
                'departments': departments,
                'vouchers': [
                    {
                        'id': str(v.id),
                        'voucher_number': v.voucher_number,
                        'purpose': v.purpose[:100] + '...' if len(v.purpose) > 100 else v.purpose,
                        'amount': float(v.amount_in_figures),
                        'requester': v.requester_name_department,
                        'date_prepared': v.date_prepared.isoformat() if v.date_prepared else None,
                        'days_pending': (timezone.now().date() - v.date_prepared).days if v.date_prepared else 0,
                        'is_overdue': v.needed_by < timezone.now().date() if v.needed_by else False
                    }
                    for v in pending_vouchers[:50]  # Limit to 50 for mobile
                ]
            }
        }
    })


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def payment_status_report_view(request):
    """Report on payment status of vouchers - FIXED VERSION."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response({'error': 'No organization assigned'}, status=400)
    
    # Get date range from query params
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    queryset = Voucher.objects.filter(organization=organization)
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            queryset = queryset.filter(date_prepared__gte=start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            queryset = queryset.filter(date_prepared__lte=end)
        except ValueError:
            pass
    
    # Group by status
    status_stats = {}
    for status_code, status_name in Voucher.STATUS_CHOICES:
        vouchers = queryset.filter(status=status_code)
        total_amount = vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00')
        approved_amount = vouchers.aggregate(Sum('approved_amount'))['approved_amount__sum'] or Decimal('0.00')
        paid_amount = vouchers.aggregate(Sum('paid_amount'))['paid_amount__sum'] or Decimal('0.00')
        
        if vouchers.exists():
            status_stats[status_code] = {
                'count': vouchers.count(),
                'total_amount': float(total_amount),
                'approved_amount': float(approved_amount),
                'paid_amount': float(paid_amount),
                'label': status_name
            }
    
    # Payment method breakdown
    payment_methods = {}
    for method_code, method_name in Voucher.PAYMENT_METHOD_CHOICES:
        paid_vouchers = queryset.filter(status='paid', payment_method=method_code)
        total = paid_vouchers.aggregate(Sum('paid_amount'))['paid_amount__sum'] or Decimal('0.00')
        if paid_vouchers.exists():
            payment_methods[method_code] = {
                'label': method_name,
                'count': paid_vouchers.count(),
                'total_amount': float(total),
                'percentage': round((float(total) / float(status_stats.get('paid', {}).get('paid_amount', 1))) * 100, 1) if status_stats.get('paid', {}).get('paid_amount', 0) > 0 else 0
            }
    
    # Get timeline data (monthly)
    timeline_data = []
    today = timezone.now().date()
    
    # Last 6 months
    for i in range(5, -1, -1):
        month_date = today.replace(day=1) - timedelta(days=30*i)
        month_start = month_date.replace(day=1)
        if i == 0:
            month_end = today
        else:
            next_month = month_start + timedelta(days=32)
            month_end = next_month.replace(day=1) - timedelta(days=1)
        
        month_vouchers = queryset.filter(
            date_prepared__gte=month_start,
            date_prepared__lte=month_end
        )
        
        total = month_vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00')
        paid = month_vouchers.filter(status='paid').aggregate(Sum('paid_amount'))['paid_amount__sum'] or Decimal('0.00')
        
        timeline_data.append({
            'month': month_start.strftime('%Y-%m'),
            'total': float(total),
            'paid': float(paid)
        })
    
    paid_amount_total = queryset.filter(status='paid').aggregate(Sum('paid_amount'))['paid_amount__sum'] or Decimal('0.00')
    pending_payment_total = queryset.filter(status='approved').aggregate(Sum('approved_amount'))['approved_amount__sum'] or Decimal('0.00')
    total_vouchers_count = queryset.count()
    approved_count = queryset.filter(status='approved').count()
    paid_count = queryset.filter(status='paid').count()
    
    return Response({
        'success': True,
        'report': {
            'title': 'Payment Status Report',
            'period': f"{start_date or 'All time'} to {end_date or 'now'}",
            'generated_at': timezone.now().isoformat(),
            'summary': {
                'total_vouchers': total_vouchers_count,
                'total_amount': float(queryset.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00')),
                'paid_amount': float(paid_amount_total),
                'pending_payment': float(pending_payment_total),
                'payment_rate': round((paid_count / approved_count * 100) if approved_count > 0 else 0, 1)
            },
            'breakdown': {
                'by_status': status_stats,
                'by_payment_method': payment_methods,
                'timeline': timeline_data
            }
        }
    })



@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def expense_trend_analysis_view(request):
    """Expense trend analysis over time - FIXED VERSION."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response({'error': 'No organization assigned'}, status=400)
    
    # Get parameters
    period = request.query_params.get('period', 'monthly')  # monthly, quarterly, yearly
    months = int(request.query_params.get('months', 12))
    
    # Calculate date range
    today = timezone.now().date()
    start_date = today - timedelta(days=months * 30)
    
    vouchers = Voucher.objects.filter(
        organization=organization,
        date_prepared__range=[start_date, today]
    )
    
    # Group by time period
    trend_data = []
    
    # Generate periods
    if period == 'monthly':
        for i in range(months):
            period_start = today.replace(day=1) - timedelta(days=30*i)
            period_end = period_start + timedelta(days=32)
            period_end = period_end.replace(day=1) - timedelta(days=1)
            if i == 0:
                period_end = today
            
            period_vouchers = vouchers.filter(
                date_prepared__gte=period_start,
                date_prepared__lte=period_end
            )
            
            total_amount = period_vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00')
            approved_amount = period_vouchers.aggregate(Sum('approved_amount'))['approved_amount__sum'] or Decimal('0.00')
            paid_amount = period_vouchers.aggregate(Sum('paid_amount'))['paid_amount__sum'] or Decimal('0.00')
            
            trend_data.append({
                'period': period_start.strftime('%Y-%m'),
                'total_vouchers': period_vouchers.count(),
                'total_amount': float(total_amount),
                'approved_amount': float(approved_amount),
                'paid_amount': float(paid_amount),
                'avg_processing_days': 0  # Skip for now
            })
    
    trend_data.reverse()  # Sort chronologically
    
    # Top expenses
    top_expenses = vouchers.filter(status='paid').order_by('-paid_amount')[:10]
    
    # Category analysis - simplified version
    categories = {
        'Operational': 0,
        'Maintenance': 0,
        'Supplies': 0,
        'Events': 0,
        'Other': 0
    }
    
    # You might want to add a category field to your Voucher model
    # For now, we'll use a simple approach
    for voucher in vouchers.filter(status='paid'):
        purpose = voucher.purpose.lower()
        if 'operat' in purpose:
            categories['Operational'] += float(voucher.paid_amount or voucher.amount_in_figures)
        elif 'maintain' in purpose or 'repair' in purpose:
            categories['Maintenance'] += float(voucher.paid_amount or voucher.amount_in_figures)
        elif 'supply' in purpose or 'material' in purpose:
            categories['Supplies'] += float(voucher.paid_amount or voucher.amount_in_figures)
        elif 'event' in purpose or 'program' in purpose:
            categories['Events'] += float(voucher.paid_amount or voucher.amount_in_figures)
        else:
            categories['Other'] += float(voucher.paid_amount or voucher.amount_in_figures)
    
    # Calculate growth rate
    growth_rate = 0
    if len(trend_data) >= 2:
        current = trend_data[-1]['paid_amount']
        previous = trend_data[-2]['paid_amount']
        if previous > 0:
            growth_rate = ((current - previous) / previous) * 100
    
    total_expenditure = vouchers.filter(status='paid').aggregate(Sum('paid_amount'))['paid_amount__sum'] or Decimal('0.00')
    
    return Response({
        'success': True,
        'report': {
            'title': 'Expense Trend Analysis',
            'period': f"Last {months} months",
            'generated_at': timezone.now().isoformat(),
            'trend': trend_data,
            'insights': {
                'total_expenditure': float(total_expenditure),
                'avg_monthly_expense': float(total_expenditure) / max(months, 1),
                'growth_rate': round(growth_rate, 1),
                'top_expenses': [
                    {
                        'voucher_number': v.voucher_number,
                        'purpose': v.purpose[:50] + '...' if len(v.purpose) > 50 else v.purpose,
                        'amount': float(v.paid_amount or v.amount_in_figures),
                        'date': v.date_prepared.isoformat() if v.date_prepared else None
                    }
                    for v in top_expenses
                ],
                'category_breakdown': {
                    category: amount
                    for category, amount in categories.items()
                    if amount > 0
                }
            }
        }
    })




@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def overdue_vouchers_report_view(request):
    """Report on overdue vouchers - FIXED VERSION."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response({'error': 'No organization assigned'}, status=400)
    
    today = timezone.now().date()
    
    # Get overdue vouchers (submitted or approved but needed_by date has passed)
    overdue_vouchers = Voucher.objects.filter(
        organization=organization,
        status__in=['submitted', 'approved'],
        needed_by__lt=today
    ).order_by('needed_by')
    
    # Calculate overdue severity
    severe_overdue = overdue_vouchers.filter(needed_by__lt=today - timedelta(days=30))
    moderate_overdue = overdue_vouchers.filter(
        needed_by__range=[today - timedelta(days=30), today - timedelta(days=7)]
    )
    recent_overdue = overdue_vouchers.filter(
        needed_by__range=[today - timedelta(days=7), today]
    )
    
    # Group by department/requester
    departments = {}
    for voucher in overdue_vouchers:
        # Extract department
        if '/' in voucher.requester_name_department:
            dept = voucher.requester_name_department.split('/')[-1].strip()
        else:
            dept = 'General'
        
        if dept not in departments:
            departments[dept] = {
                'count': 0,
                'total_amount': Decimal('0.00'),
                'total_days_overdue': 0
            }
        
        departments[dept]['count'] += 1
        departments[dept]['total_amount'] += voucher.amount_in_figures
        days_overdue = (today - voucher.needed_by).days
        departments[dept]['total_days_overdue'] += days_overdue
    
    # Calculate averages
    for dept in departments:
        departments[dept]['avg_overdue_days'] = departments[dept]['total_days_overdue'] / departments[dept]['count']
    
    # Calculate average overdue days
    avg_overdue_days = 0
    if overdue_vouchers.exists():
        total_days = sum((today - v.needed_by).days for v in overdue_vouchers if v.needed_by)
        avg_overdue_days = total_days / overdue_vouchers.count()
    
    return Response({
        'success': True,
        'report': {
            'title': 'Overdue Vouchers Report',
            'generated_at': timezone.now().isoformat(),
            'summary': {
                'total_overdue': overdue_vouchers.count(),
                'total_amount': float(overdue_vouchers.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00')),
                'severe_overdue': severe_overdue.count(),
                'moderate_overdue': moderate_overdue.count(),
                'recent_overdue': recent_overdue.count(),
                'avg_overdue_days': round(avg_overdue_days, 1)
            },
            'breakdown': {
                'by_severity': {
                    'severe': {
                        'count': severe_overdue.count(),
                        'amount': float(severe_overdue.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00')),
                        'vouchers': [
                            {
                                'id': str(v.id),
                                'voucher_number': v.voucher_number,
                                'purpose': v.purpose[:50] + '...' if len(v.purpose) > 50 else v.purpose,
                                'amount': float(v.amount_in_figures),
                                'needed_by': v.needed_by.isoformat(),
                                'days_overdue': (today - v.needed_by).days,
                                'requester': v.requester_name_department
                            }
                            for v in severe_overdue[:10]
                        ]
                    },
                    'moderate': {
                        'count': moderate_overdue.count(),
                        'amount': float(moderate_overdue.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00'))
                    },
                    'recent': {
                        'count': recent_overdue.count(),
                        'amount': float(recent_overdue.aggregate(Sum('amount_in_figures'))['amount_in_figures__sum'] or Decimal('0.00'))
                    }
                },
                'by_department': [
                    {
                        'department': dept,
                        'count': data['count'],
                        'total_amount': float(data['total_amount']),
                        'avg_overdue_days': round(data['avg_overdue_days'], 1)
                    }
                    for dept, data in departments.items()
                ]
            },
            'detailed': [
                {
                    'id': str(v.id),
                    'voucher_number': v.voucher_number,
                    'purpose': v.purpose[:100] + '...' if len(v.purpose) > 100 else v.purpose,
                    'amount': float(v.amount_in_figures),
                    'needed_by': v.needed_by.isoformat(),
                    'days_overdue': (today - v.needed_by).days,
                    'requester': v.requester_name_department,
                    'status': v.status,
                    'status_display': v.get_status_display()
                }
                for v in overdue_vouchers[:50]
            ]
        }
    })


# In your church/views.py

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def voucher_notifications_api_view(request):
    """Mobile API for voucher notifications."""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response({'error': 'No organization assigned'}, status=400)
    
    # Get notifications based on user role
    notifications = []
    
    # 1. Vouchers pending approval (for approvers)
    can_approve = (
        request.user.is_staff or 
        getattr(request.user, 'is_admin', False) or 
        getattr(request.user, 'is_finance', False)
    )
    
    if can_approve:
        pending_vouchers = Voucher.objects.filter(
            organization=organization,
            status='submitted'
        ).order_by('-date_prepared')[:10]
        
        for voucher in pending_vouchers:
            days_pending = (timezone.now().date() - voucher.date_prepared).days if voucher.date_prepared else 0
            
            # Calculate urgency level
            if voucher.needed_by and voucher.needed_by < timezone.now().date():
                priority = 'high'
                urgency_text = f"OVERDUE by {(timezone.now().date() - voucher.needed_by).days} days"
            elif days_pending > 7:
                priority = 'medium'
                urgency_text = f"Pending for {days_pending} days"
            else:
                priority = 'low'
                urgency_text = f"Submitted {days_pending} days ago"
            
            notifications.append({
                'id': f'pending_{voucher.id}',
                'type': 'pending_approval',
                'title': 'Voucher Pending Approval',
                'message': f'Voucher {voucher.voucher_number} from {voucher.requester_name_department} needs approval',
                'data': {
                    'voucher_id': str(voucher.id),
                    'voucher_number': voucher.voucher_number,
                    'amount': float(voucher.amount_in_figures),
                    'purpose': voucher.purpose[:100],
                    'requester': voucher.requester_name_department,
                    'urgency': priority,
                    'urgency_text': urgency_text,
                    'date_prepared': voucher.date_prepared.isoformat() if voucher.date_prepared else None,
                    'needed_by': voucher.needed_by.isoformat() if voucher.needed_by else None,
                },
                'priority': priority,
                'read': False,
                'created_at': voucher.date_prepared.isoformat() if voucher.date_prepared else timezone.now().isoformat(),
                'action_required': True,
                'action_label': 'Review Now'
            })
    
    # 2. Approved vouchers awaiting payment (for finance/payment processors)
    can_pay = (
        request.user.is_staff or 
        getattr(request.user, 'is_admin', False) or 
        getattr(request.user, 'is_finance', False)
    )
    
    if can_pay:
        approved_vouchers = Voucher.objects.filter(
            organization=organization,
            status='approved',
            needed_by__gte=timezone.now().date() - timedelta(days=30)
        ).order_by('needed_by')[:10]
        
        for voucher in approved_vouchers:
            days_approved = (timezone.now().date() - voucher.approved_date).days if voucher.approved_date else 0
            
            if voucher.needed_by and voucher.needed_by < timezone.now().date():
                priority = 'high'
                urgency_text = f"Payment OVERDUE by {(timezone.now().date() - voucher.needed_by).days} days"
            elif voucher.needed_by and (voucher.needed_by - timezone.now().date()).days <= 3:
                priority = 'medium'
                urgency_text = f"Needs payment in {(voucher.needed_by - timezone.now().date()).days} days"
            else:
                priority = 'low'
                urgency_text = f"Approved {days_approved} days ago"
            
            notifications.append({
                'id': f'payment_{voucher.id}',
                'type': 'awaiting_payment',
                'title': 'Voucher Awaiting Payment',
                'message': f'Voucher {voucher.voucher_number} approved for ₦{voucher.approved_amount or voucher.amount_in_figures:,} needs payment',
                'data': {
                    'voucher_id': str(voucher.id),
                    'voucher_number': voucher.voucher_number,
                    'approved_amount': float(voucher.approved_amount or voucher.amount_in_figures),
                    'payable_to': voucher.payable_to,
                    'payment_method': voucher.payment_method,
                    'urgency': priority,
                    'urgency_text': urgency_text,
                    'approved_date': voucher.approved_date.isoformat() if voucher.approved_date else None,
                    'needed_by': voucher.needed_by.isoformat() if voucher.needed_by else None,
                },
                'priority': priority,
                'read': False,
                'created_at': voucher.approved_date.isoformat() if voucher.approved_date else timezone.now().isoformat(),
                'action_required': True,
                'action_label': 'Process Payment'
            })
    
    # 3. User's own vouchers status updates
    user_vouchers = Voucher.objects.filter(
        organization=organization,
        requested_by=request.user,
        status__in=['approved', 'rejected', 'paid']
    ).order_by('-updated_at')[:10]
    
    for voucher in user_vouchers:
        if voucher.status == 'approved' and voucher.approved_date:
            notifications.append({
                'id': f'approved_{voucher.id}',
                'type': 'voucher_approved',
                'title': 'Voucher Approved!',
                'message': f'Your voucher {voucher.voucher_number} has been approved',
                'data': {
                    'voucher_id': str(voucher.id),
                    'voucher_number': voucher.voucher_number,
                    'approved_amount': float(voucher.approved_amount or voucher.amount_in_figures),
                    'approved_by': voucher.approved_by.get_full_name() if voucher.approved_by else 'Finance',
                    'approved_date': voucher.approved_date.isoformat(),
                    'remarks': voucher.finance_remarks,
                },
                'priority': 'info',
                'read': False,
                'created_at': voucher.approved_date.isoformat(),
                'action_required': False,
                'action_label': 'View Details'
            })
        
        elif voucher.status == 'paid' and voucher.paid_date:
            notifications.append({
                'id': f'paid_{voucher.id}',
                'type': 'voucher_paid',
                'title': 'Voucher Paid',
                'message': f'Your voucher {voucher.voucher_number} has been paid',
                'data': {
                    'voucher_id': str(voucher.id),
                    'voucher_number': voucher.voucher_number,
                    'paid_amount': float(voucher.paid_amount or voucher.approved_amount or voucher.amount_in_figures),
                    'payment_reference': voucher.payment_reference,
                    'paid_date': voucher.paid_date.isoformat(),
                },
                'priority': 'info',
                'read': False,
                'created_at': voucher.paid_date.isoformat(),
                'action_required': False,
                'action_label': 'View Receipt'
            })
        
        elif voucher.status == 'rejected':
            notifications.append({
                'id': f'rejected_{voucher.id}',
                'type': 'voucher_rejected',
                'title': 'Voucher Rejected',
                'message': f'Your voucher {voucher.voucher_number} was rejected',
                'data': {
                    'voucher_id': str(voucher.id),
                    'voucher_number': voucher.voucher_number,
                    'rejection_reason': voucher.finance_remarks or 'No reason provided',
                },
                'priority': 'warning',
                'read': False,
                'created_at': voucher.updated_at.isoformat(),
                'action_required': True,
                'action_label': 'View & Resubmit'
            })
    
    # 4. Overdue vouchers (for everyone)
    overdue_vouchers = Voucher.objects.filter(
        organization=organization,
        status__in=['submitted', 'approved'],
        needed_by__lt=timezone.now().date()
    ).order_by('needed_by')[:5]
    
    for voucher in overdue_vouchers:
        if voucher.requested_by == request.user or can_approve or can_pay:
            days_overdue = (timezone.now().date() - voucher.needed_by).days
            
            notifications.append({
                'id': f'overdue_{voucher.id}',
                'type': 'voucher_overdue',
                'title': 'Voucher Overdue!',
                'message': f'Voucher {voucher.voucher_number} is overdue by {days_overdue} days',
                'data': {
                    'voucher_id': str(voucher.id),
                    'voucher_number': voucher.voucher_number,
                    'purpose': voucher.purpose[:100],
                    'amount': float(voucher.amount_in_figures),
                    'needed_by': voucher.needed_by.isoformat(),
                    'days_overdue': days_overdue,
                    'status': voucher.status,
                },
                'priority': 'high',
                'read': False,
                'created_at': voucher.needed_by.isoformat(),
                'action_required': True,
                'action_label': 'Take Action'
            })
    
    # Sort by priority and date
    priority_order = {'high': 0, 'medium': 1, 'low': 2, 'info': 3, 'warning': 4}
    notifications.sort(key=lambda x: (priority_order.get(x['priority'], 5), x['created_at']), reverse=True)
    
    # Count unread notifications
    unread_count = sum(1 for n in notifications if not n.get('read', False))
    
    return Response({
        'success': True,
        'notifications': notifications,
        'unread_count': unread_count,
        'total_count': len(notifications)
    })

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_notification_read_api_view(request, notification_id):
    """Mark a notification as read."""
    # Since we're generating notifications on the fly,
    # we can simulate marking as read by storing in session or cache
    # For now, we'll just acknowledge it
    
    return Response({
        'success': True,
        'message': 'Notification marked as read'
    })

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read_api_view(request):
    """Mark all notifications as read."""
    # In a real implementation, you'd store read status in database
    # For now, we'll just acknowledge
    
    return Response({
        'success': True,
        'message': 'All notifications marked as read'
    })






# inventory/api_views.py
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets, filters
from rest_framework_simplejwt.authentication import JWTAuthentication
from django_filters.rest_framework import DjangoFilterBackend
from django.core.paginator import Paginator
from django.db.models import Q, Sum, F

from .models import (
    InventoryCategory, InventoryVendor, InventoryItem, 
    InventoryTransaction, InventoryCheckout, InventoryAudit
)
from .serializers import (
    InventoryCategorySerializer, InventoryVendorSerializer,
    InventoryItemSerializer, InventoryTransactionSerializer,
    InventoryCheckoutSerializer, InventoryAuditSerializer
)


def get_user_organization(user):
    """Helper to get user's organization"""
    if hasattr(user, 'organization') and user.organization:
        return user.organization
    
    if hasattr(user, 'profile') and hasattr(user.profile, 'organization'):
        return user.profile.organization
    
    return None


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_dashboard_api_view(request):
    """API endpoint for inventory dashboard"""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Calculate statistics
    stats = {
        'total_items': InventoryItem.objects.filter(organization=organization).count(),
        'low_stock_items': InventoryItem.objects.filter(
            organization=organization,
            quantity__lte=F('reorder_level'),
            alert_on_low=True
        ).count(),
        'active_checkouts': InventoryCheckout.objects.filter(
            organization=organization,
            status='active'
        ).count(),
        'overdue_checkouts': InventoryCheckout.objects.filter(
            organization=organization,
            status='overdue'
        ).count(),
        'total_value': InventoryItem.objects.filter(
            organization=organization
        ).aggregate(total=Sum(F('quantity') * F('purchase_price')))['total'] or 0,
    }
    
    return Response(stats)


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_item_list_api_view(request):
    """API endpoint for listing inventory items with filtering"""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get query parameters
    search = request.query_params.get('search', '')
    category_id = request.query_params.get('category')
    department_id = request.query_params.get('department')
    status_filter = request.query_params.get('status')
    low_stock_only = request.query_params.get('low_stock', '').lower() == 'true'
    
    # Build queryset
    items = InventoryItem.objects.filter(organization=organization)
    
    # Apply filters
    if search:
        items = items.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search) |
            Q(sku__icontains=search) |
            Q(barcode__icontains=search)
        )
    
    if category_id:
        items = items.filter(category_id=category_id)
    
    if department_id:
        items = items.filter(department_id=department_id)
    
    if status_filter:
        items = items.filter(status=status_filter)
    
    if low_stock_only:
        items = items.filter(quantity__lte=F('reorder_level'))
    
    # Order by
    sort_by = request.query_params.get('sort', 'name')
    if sort_by == 'quantity':
        items = items.order_by('quantity')
    elif sort_by == 'value':
        items = items.order_by(F('quantity') * F('purchase_price'))
    else:
        items = items.order_by('name')
    
    # Paginate
    page_size = int(request.query_params.get('page_size', 50))
    page_number = int(request.query_params.get('page', 1))
    
    paginator = Paginator(items, page_size)
    page_obj = paginator.get_page(page_number)
    
    serializer = InventoryItemSerializer(page_obj, many=True, context={'request': request})
    
    return Response({
        'count': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': page_obj.number,
        'next': page_obj.next_page_number() if page_obj.has_next() else None,
        'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
        'items': serializer.data
    })


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_item_detail_api_view(request, item_id):
    """API endpoint for single inventory item details"""
    try:
        organization = get_user_organization(request.user)
        if not organization:
            return Response(
                {'error': 'No organization assigned'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        item = InventoryItem.objects.get(id=item_id, organization=organization)
        serializer = InventoryItemSerializer(item, context={'request': request})
        return Response(serializer.data)
        
    except InventoryItem.DoesNotExist:
        return Response(
            {'error': 'Item not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_item_create_api_view(request):
    """API endpoint for creating inventory items"""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check permissions
    user = request.user
    can_manage = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False)
    )
    
    if not can_manage:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Prepare the data
    data = request.data.copy()
    data['organization'] = str(organization.id)
    
    serializer = InventoryItemSerializer(data=data, context={'request': request})
    
    if serializer.is_valid():
        item = serializer.save(created_by=request.user)
        return Response(
            {
                'success': True,
                'message': 'Item created successfully',
                'item_id': str(item.id),
                'item': InventoryItemSerializer(item, context={'request': request}).data
            },
            status=status.HTTP_201_CREATED
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'PATCH'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_item_update_api_view(request, item_id):
    """API endpoint for updating inventory items"""
    try:
        organization = get_user_organization(request.user)
        if not organization:
            return Response(
                {'error': 'No organization assigned'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        item = InventoryItem.objects.get(id=item_id, organization=organization)
        
        # Check permissions
        user = request.user
        can_manage = (
            user.is_staff or 
            getattr(user, "is_owner", False) or 
            getattr(user, "is_admin", False) or 
            getattr(user, "is_pastor", False)
        )
        
        if not can_manage:
            return Response(
                {'error': 'Permission denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Prepare the data
        data = request.data.copy()
        data['organization'] = str(organization.id)
        
        # Use partial=True for PATCH requests
        is_partial = request.method == 'PATCH'
        serializer = InventoryItemSerializer(
            item, 
            data=data, 
            partial=is_partial,
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Item updated successfully',
                'item': serializer.data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    except InventoryItem.DoesNotExist:
        return Response(
            {'error': 'Item not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_item_delete_api_view(request, item_id):
    """API endpoint for deleting inventory items"""
    try:
        organization = get_user_organization(request.user)
        if not organization:
            return Response(
                {'error': 'No organization assigned'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        item = InventoryItem.objects.get(id=item_id, organization=organization)
        
        # Check permissions
        user = request.user
        can_manage = (
            user.is_staff or 
            getattr(user, "is_owner", False) or 
            getattr(user, "is_admin", False) or 
            getattr(user, "is_pastor", False)
        )
        
        if not can_manage:
            return Response(
                {'error': 'Permission denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if item has active checkouts
        active_checkouts = InventoryCheckout.objects.filter(
            item=item,
            status__in=['active', 'overdue']
        ).exists()
        
        if active_checkouts:
            return Response(
                {'error': 'Cannot delete item with active checkouts'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        item_name = item.name
        item.delete()
        
        return Response({
            'success': True,
            'message': f'Item "{item_name}" deleted successfully',
        })
        
    except InventoryItem.DoesNotExist:
        return Response(
            {'error': 'Item not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_checkout_list_api_view(request):
    """API endpoint for listing inventory checkouts"""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get query parameters
    status_filter = request.query_params.get('status')
    member_id = request.query_params.get('member')
    department_id = request.query_params.get('department')
    overdue_only = request.query_params.get('overdue', '').lower() == 'true'
    
    # Build queryset
    checkouts = InventoryCheckout.objects.filter(organization=organization)
    
    # Apply filters
    if status_filter:
        checkouts = checkouts.filter(status=status_filter)
    
    if member_id:
        checkouts = checkouts.filter(member_id=member_id)
    
    if department_id:
        checkouts = checkouts.filter(department_id=department_id)
    
    if overdue_only:
        checkouts = checkouts.filter(status='overdue')
    
    # Order by
    sort_by = request.query_params.get('sort', '-checkout_date')
    checkouts = checkouts.order_by(sort_by)
    
    # Paginate
    page_size = int(request.query_params.get('page_size', 50))
    page_number = int(request.query_params.get('page', 1))
    
    paginator = Paginator(checkouts, page_size)
    page_obj = paginator.get_page(page_number)
    
    serializer = InventoryCheckoutSerializer(page_obj, many=True, context={'request': request})
    
    return Response({
        'count': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': page_obj.number,
        'next': page_obj.next_page_number() if page_obj.has_next() else None,
        'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
        'checkouts': serializer.data
    })


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_checkout_create_api_view(request):
    """API endpoint for creating checkouts"""
    organization = get_user_organization(request.user)
    
    if not organization:
        return Response(
            {'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check permissions
    user = request.user
    can_checkout = (
        user.is_staff or 
        getattr(user, "is_owner", False) or 
        getattr(user, "is_admin", False) or 
        getattr(user, "is_pastor", False)
    )
    
    if not can_checkout:
        return Response(
            {'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Prepare the data
    data = request.data.copy()
    data['organization'] = str(organization.id)
    
    serializer = InventoryCheckoutSerializer(data=data, context={'request': request})
    
    if serializer.is_valid():
        # Check if item has enough stock
        item_id = data.get('item')
        quantity = int(data.get('quantity', 0))
        
        try:
            item = InventoryItem.objects.get(id=item_id, organization=organization)
            if item.quantity < quantity:
                return Response(
                    {'error': f'Only {item.quantity} available in stock'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        except InventoryItem.DoesNotExist:
            return Response(
                {'error': 'Item not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        checkout = serializer.save(
            created_by=request.user,
            approved_by=request.user,
            approved_at=timezone.now(),
            status='active'
        )
        
        # Update item quantity
        item.quantity -= checkout.quantity
        if item.quantity < 0:
            item.quantity = 0
        item.save()
        
        # Create transaction
        InventoryTransaction.objects.create(
            organization=organization,
            item=item,
            transaction_type='checkout',
            quantity=checkout.quantity,
            from_department=checkout.department,
            performed_by=request.user,
            notes=f"Checked out to {checkout.member.full_name}. Purpose: {checkout.purpose}",
            approved_by=request.user,
            approved_at=timezone.now(),
        )
        
        return Response({
            'success': True,
            'message': 'Item checked out successfully',
            'checkout': InventoryCheckoutSerializer(checkout, context={'request': request}).data
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)





@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_low_stock_alerts_api_view(request):
    """
    API endpoint for getting low stock alerts.
    
    Query Parameters:
    - threshold: Custom threshold percentage (default: organization's setting or 100%)
    - category: Filter by category ID
    - department: Filter by department ID
    - page: Page number for pagination
    - page_size: Items per page
    - sort: Sort by field (quantity, name, last_checked_out, etc.)
    """
    try:
        user = request.user
        organization = get_user_organization(user)
        
        if not organization:
            return Response(
                {'error': 'No organization assigned'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get query parameters
        threshold = request.query_params.get('threshold')
        category_id = request.query_params.get('category')
        department_id = request.query_params.get('department')
        search = request.query_params.get('search', '')
        sort = request.query_params.get('sort', 'quantity')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        
        # Build base queryset
        items = InventoryItem.objects.filter(
            organization=organization,
            is_active=True,
            alert_on_low=True
        ).select_related('category', 'department', 'vendor')
        
        # Apply low stock filter
        # Items are low stock if quantity <= reorder_level
        # Or if using percentage threshold
        if threshold and threshold.isdigit():
            # Use percentage threshold (e.g., threshold=20 means 20% of reorder level)
            threshold_percent = int(threshold) / 100
            items = items.filter(
                quantity__lte=F('reorder_level') * threshold_percent
            )
        else:
            # Default: quantity <= reorder_level
            items = items.filter(quantity__lte=F('reorder_level'))
        
        # Apply category filter
        if category_id:
            try:
                category = InventoryCategory.objects.get(
                    id=category_id,
                    organization=organization
                )
                items = items.filter(category=category)
            except InventoryCategory.DoesNotExist:
                pass
        
        # Apply department filter
        if department_id:
            items = items.filter(department_id=department_id)
        
        # Apply search filter
        if search:
            items = items.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search) |
                Q(sku__icontains=search) |
                Q(barcode__icontains=search)
            )
        
        # Apply sorting
        sort_mapping = {
            'quantity': 'quantity',
            'name': 'name',
            'value': F('quantity') * F('purchase_price'),
            'reorder_level': 'reorder_level',
            'last_checked_out': 'last_checked_out',
            'created_at': 'created_at',
        }
        
        if sort in sort_mapping:
            if sort == 'value':
                items = items.annotate(
                    total_value=F('quantity') * F('purchase_price')
                ).order_by('total_value')
            else:
                items = items.order_by(sort_mapping[sort])
        else:
            items = items.order_by('quantity')  # Default sort by quantity (lowest first)
        
        # Calculate statistics
        total_items = items.count()
        out_of_stock = items.filter(quantity=0).count()
        critical_stock = items.filter(
            quantity__gt=0,
            quantity__lte=F('reorder_level') * 0.25
        ).count()
        warning_stock = items.filter(
            quantity__gt=F('reorder_level') * 0.25,
            quantity__lte=F('reorder_level')
        ).count()
        
        # Calculate total value of low stock items
        low_stock_value = sum(
            item.quantity * (item.purchase_price or 0)
            for item in items
        )
        
        # Paginate results
        paginator = Paginator(items, page_size)
        page_obj = paginator.get_page(page)
        
        # Serialize data
        serializer = InventoryItemSerializer(
            page_obj, 
            many=True, 
            context={'request': request}
        )
        
        # Prepare response
        response_data = {
            'success': True,
            'count': total_items,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous_page': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'stats': {
                'total_low_stock': total_items,
                'out_of_stock': out_of_stock,
                'critical_stock': critical_stock,
                'warning_stock': warning_stock,
                'total_value': low_stock_value,
            },
            'items': serializer.data,
        }
        
        return Response(response_data)
        
    except Exception as e:
        print(f"Error in low_stock_alerts_api_view: {str(e)}")
        return Response(
            {'error': 'Failed to load low stock alerts'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# inventory/api_views.py
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db.models import Q, F
from django.utils import timezone

from .models import (
    InventoryCategory, InventoryVendor, InventoryItem,
    InventoryTransaction, InventoryCheckout
)
from .serializers import (
    InventoryCategorySerializer, InventoryVendorSerializer,
    InventoryTransactionSerializer
)


def get_user_organization(user):
    """Helper to get user's organization"""
    if hasattr(user, 'organization') and user.organization:
        return user.organization
    
    if hasattr(user, 'profile') and hasattr(user.profile, 'organization'):
        return user.profile.organization
    
    return None


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_category_list_api_view(request):
    """API endpoint for listing inventory categories"""
    try:
        organization = get_user_organization(request.user)
        
        if not organization:
            return Response(
                {'error': 'No organization assigned'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        print('🏷️ [API] Getting inventory categories for organization:', organization.slug)
        
        # Get all categories for the organization
        categories = InventoryCategory.objects.filter(organization=organization)
        
        # Apply filters if provided
        category_type = request.query_params.get('category_type')
        if category_type:
            categories = categories.filter(category_type=category_type)
        
        # Order by name
        categories = categories.order_by('category_type', 'name')
        
        serializer = InventoryCategorySerializer(categories, many=True, context={'request': request})
        
        print('✅ [API] Categories response:', {
            'count': len(serializer.data),
            'types': list(set(cat['category_type'] for cat in serializer.data))
        })
        
        return Response({
            'success': True,
            'count': len(serializer.data),
            'categories': serializer.data
        })
        
    except Exception as e:
        print('❌ [API] Error getting categories:', str(e))
        return Response(
            {'error': 'Failed to load categories'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_vendor_list_api_view(request):
    """API endpoint for listing inventory vendors"""
    try:
        organization = get_user_organization(request.user)
        
        if not organization:
            return Response(
                {'error': 'No organization assigned'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        print('🏢 [API] Getting inventory vendors for organization:', organization.slug)
        
        # Get all vendors for the organization
        vendors = InventoryVendor.objects.filter(organization=organization)
        
        # Apply search filter if provided
        search = request.query_params.get('search')
        if search:
            vendors = vendors.filter(
                Q(name__icontains=search) |
                Q(contact_person__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )
        
        # Order by name
        vendors = vendors.order_by('name')
        
        serializer = InventoryVendorSerializer(vendors, many=True, context={'request': request})
        
        print('✅ [API] Vendors response:', {
            'count': len(serializer.data)
        })
        
        return Response({
            'success': True,
            'count': len(serializer.data),
            'vendors': serializer.data
        })
        
    except Exception as e:
        print('❌ [API] Error getting vendors:', str(e))
        return Response(
            {'error': 'Failed to load vendors'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inventory_transaction_list_api_view(request):
    """API endpoint for listing inventory transactions"""
    try:
        organization = get_user_organization(request.user)
        
        if not organization:
            return Response(
                {'error': 'No organization assigned'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        print('📊 [API] Getting inventory transactions for organization:', organization.slug)
        
        # Get all transactions for the organization
        transactions = InventoryTransaction.objects.filter(organization=organization)
        
        # Apply filters
        item_id = request.query_params.get('item')
        if item_id:
            try:
                item = InventoryItem.objects.get(id=item_id, organization=organization)
                transactions = transactions.filter(item=item)
            except InventoryItem.DoesNotExist:
                return Response(
                    {'error': 'Item not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
        
        transaction_type = request.query_params.get('transaction_type')
        if transaction_type:
            transactions = transactions.filter(transaction_type=transaction_type)
        
        # Date range filters
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date:
            try:
                transactions = transactions.filter(created_at__date__gte=start_date)
            except ValueError:
                pass
        
        if end_date:
            try:
                transactions = transactions.filter(created_at__date__lte=end_date)
            except ValueError:
                pass
        
        # Order by most recent first
        transactions = transactions.order_by('-created_at')
        
        # Limit results if no specific filters
        if not item_id and not transaction_type:
            transactions = transactions[:100]  # Limit to 100 most recent
        
        serializer = InventoryTransactionSerializer(transactions, many=True, context={'request': request})
        
        print('✅ [API] Transactions response:', {
            'count': len(serializer.data),
            'types': list(set(t['transaction_type'] for t in serializer.data))
        })
        
        return Response({
            'success': True,
            'count': len(serializer.data),
            'transactions': serializer.data
        })
        
    except Exception as e:
        print('❌ [API] Error getting transactions:', str(e))
        return Response(
            {'error': 'Failed to load transactions'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

        

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def stock_adjustment_api_view(request):
    """API endpoint for adjusting stock"""
    try:
        organization = get_user_organization(request.user)
        
        if not organization:
            return Response(
                {'error': 'No organization assigned'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        print('📊 [API] Processing stock adjustment for organization:', organization.slug)
        
        # Validate required fields
        required_fields = ['item_id', 'adjustment_type', 'quantity', 'reason']
        for field in required_fields:
            if field not in request.data:
                return Response(
                    {'error': f'{field} is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        item_id = request.data['item_id']
        adjustment_type = request.data['adjustment_type']
        quantity = request.data['quantity']
        reason = request.data['reason']
        notes = request.data.get('notes', '')
        location = request.data.get('location', '')
        
        # Validate adjustment type
        valid_types = ['add', 'remove', 'set']
        if adjustment_type not in valid_types:
            return Response(
                {'error': f'Invalid adjustment type. Must be one of: {", ".join(valid_types)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate quantity
        try:
            quantity = int(quantity)
            if quantity < 0:
                return Response(
                    {'error': 'Quantity must be positive'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, TypeError):
            return Response(
                {'error': 'Quantity must be a valid number'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the item
        try:
            item = InventoryItem.objects.get(id=item_id, organization=organization)
        except InventoryItem.DoesNotExist:
            return Response(
                {'error': 'Item not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        print(f'📦 [API] Adjusting item: {item.name}, Type: {adjustment_type}, Quantity: {quantity}')
        
        # Calculate new quantity based on adjustment type
        old_quantity = item.quantity
        
        if adjustment_type == 'add':
            new_quantity = old_quantity + quantity
            transaction_type = 'add'
        elif adjustment_type == 'remove':
            if quantity > old_quantity:
                return Response(
                    {'error': f'Cannot remove {quantity} items. Only {old_quantity} available'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            new_quantity = old_quantity - quantity
            transaction_type = 'remove'
        else:  # 'set'
            new_quantity = quantity
            # Determine transaction type based on difference
            difference = new_quantity - old_quantity
            if difference > 0:
                transaction_type = 'add'
                quantity = difference
            elif difference < 0:
                transaction_type = 'remove'
                quantity = abs(difference)
            else:
                return Response(
                    {'error': 'New quantity is the same as current quantity'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Update item quantity
        item.quantity = new_quantity
        item.save(update_fields=['quantity', 'updated_at'])
        
        # Create transaction record
        transaction = InventoryTransaction.objects.create(
            organization=organization,
            item=item,
            transaction_type=transaction_type,
            quantity=quantity,
            performed_by=request.user,
            notes=f"{reason}. {notes}".strip(),
            reference_number=request.data.get('reference_number', ''),
            approved_by=request.user,
            approved_at=timezone.now(),
        )
        
        # Update location if provided
        if location:
            item.location = location
            item.save(update_fields=['location', 'updated_at'])
        
        # Prepare response
        response_data = {
            'success': True,
            'message': 'Stock adjusted successfully',
            'item': {
                'id': str(item.id),
                'name': item.name,
                'old_quantity': old_quantity,
                'new_quantity': new_quantity,
                'difference': new_quantity - old_quantity,
                'status': item.status,
                'is_low_stock': item.is_low_stock,
            },
            'transaction': {
                'id': str(transaction.id),
                'transaction_type': transaction.transaction_type,
                'quantity': transaction.quantity,
                'notes': transaction.notes,
                'created_at': transaction.created_at.isoformat(),
            }
        }
        
        print('✅ [API] Stock adjustment successful:', response_data)
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        print('❌ [API] Error adjusting stock:', str(e))
        return Response(
            {'error': 'Failed to adjust stock'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


#chat/api/views.py
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Q, Count, Subquery, OuterRef
from django.shortcuts import get_object_or_404
import uuid
from decimal import Decimal

# Use JWT Authentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated

from .models import Channel, ChannelMembership, DirectMessage, Message, ChatFile
from .models import Member
from django.contrib.auth import get_user_model
User = get_user_model()


# chat/api/views.py - UPDATED VERSION
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Q, Count, Subquery, OuterRef
from django.shortcuts import get_object_or_404
import uuid

# chat/api/views.py - COMPLETE UPDATED VERSION WITH uid
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Q, Count, Subquery, OuterRef
from django.shortcuts import get_object_or_404
import uuid
from decimal import Decimal

# Use JWT Authentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated

from .models import Channel, ChannelMembership, DirectMessage, Message, ChatFile
from .models import Member
from django.contrib.auth import get_user_model
User = get_user_model()




@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def chat_home_api_view(request):
    """
    Mobile API for chat home - matches your existing UI structure
    Returns data in the exact format your React Native app expects
    """
    user = request.user
    
    # Get user's organization
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get user display name (with fallbacks)
    user_display_name = None
    user_avatar = None
    
    # Try to get from member profile first
    try:
        member_profile = user.member_profile
        user_display_name = member_profile.full_name
        user_avatar = member_profile.photo.url if member_profile.photo else None
    except AttributeError:
        # Fallback 1: Use first_name + last_name from User model
        if user.first_name:
            user_display_name = f"{user.first_name} {user.last_name}".strip()
            if not user_display_name:
                user_display_name = user.first_name
        # Fallback 2: Use email prefix
        if not user_display_name:
            user_display_name = user.email.split('@')[0]
    
    print(f"🔍 [DEBUG] User display name: {user_display_name}")
    print(f"🔍 [DEBUG] User organization: {organization.name}")
    
    # ========== GET CHANNELS ==========
    channels = Channel.objects.filter(
        organization=organization,
        memberships__user=user
    ).annotate(
        unread_count=Subquery(
            Message.objects.filter(
                channel=OuterRef('pk'),
                created_at__gt=Subquery(
                    ChannelMembership.objects.filter(
                        channel=OuterRef('pk'),
                        user=user
                    ).values('last_read_at')[:1]
                )
            ).values('channel').annotate(count=Count('pk')).values('count')[:1]
        ) or 0,
        
        latest_message_content=Subquery(
            Message.objects.filter(
                channel=OuterRef('pk')
            ).order_by('-created_at').values('content')[:1]
        ),
        
        latest_message_time=Subquery(
            Message.objects.filter(
                channel=OuterRef('pk')
            ).order_by('-created_at').values('created_at')[:1]
        ),
        
        member_count=Count('memberships', distinct=True),
    ).order_by('name')
    
    channels_data = []
    for channel in channels:
        latest_preview = "No messages yet"
        if channel.latest_message_content:
            latest_preview = channel.latest_message_content[:100]
        
        channels_data.append({
            'id': str(channel.id),
            'name': channel.name,
            'display_name': channel.name.replace('-', ' ').title(),
            'description': channel.description or '',
            'unread_count': channel.unread_count or 0,
            'last_message': latest_preview,
            'last_message_time': channel.latest_message_time.isoformat() if channel.latest_message_time else None,
            'last_message_sender': None,
            'is_public': channel.is_public,
            'member_count': channel.member_count or 0,
        })
    
    print(f"✅ Found {len(channels_data)} channels for user")
    
    # ========== GET DIRECT MESSAGES ==========
    dm_threads = DirectMessage.objects.filter(
        organization=organization,
        participants=user
    ).annotate(
        unread_count=Subquery(
            Message.objects.filter(
                direct_message=OuterRef('pk'),
                created_at__gt=Subquery(
                    Message.objects.filter(
                        direct_message=OuterRef('pk'),
                        read_by=user
                    ).order_by('-created_at').values('created_at')[:1]
                )
            ).values('direct_message').annotate(count=Count('pk')).values('count')[:1]
        ) or 0,
        
        latest_message_content=Subquery(
            Message.objects.filter(
                direct_message=OuterRef('pk')
            ).order_by('-created_at').values('content')[:1]
        ),
        
        latest_message_time=Subquery(
            Message.objects.filter(
                direct_message=OuterRef('pk')
            ).order_by('-created_at').values('created_at')[:1]
        ),
    ).order_by('-updated_at')
    
    dms_data = []
    for dm in dm_threads:
        # Check if it's a group DM
        # Use hasattr to check if is_group exists, default to False
        is_group = getattr(dm, 'is_group', False)
        
        if not is_group:
            other_user = dm.participants.exclude(uid=user.uid).first()
            if not other_user:
                continue
            
            # Get other user's display name
            other_display_name = other_user.email.split('@')[0]
            other_avatar = None
            
            try:
                other_member = other_user.member_profile
                if other_member:
                    other_display_name = other_member.full_name
                    if other_member.photo:
                        other_avatar = request.build_absolute_uri(other_member.photo.url)
            except AttributeError:
                pass
            
            dms_data.append({
                'id': str(dm.id),
                'name': other_display_name,
                'avatar': other_avatar,
                'latest': dm.latest_message_content or "No messages yet",
                'updatedAt': int(dm.latest_message_time.timestamp() * 1000) if dm.latest_message_time else int(timezone.now().timestamp() * 1000),
                'unread': dm.unread_count or 0,
                'is_group': False,
                'user_id': str(other_user.uid),
                'user_name': other_display_name,
                'user_avatar': other_avatar,
            })
        else:
            # Handle group DMs if you have the field
            group_name = getattr(dm, 'group_name', f"Group ({dm.participants.count()})")
            dms_data.append({
                'id': str(dm.id),
                'name': group_name,
                'avatar': None,
                'latest': dm.latest_message_content or "No messages yet",
                'updatedAt': int(dm.latest_message_time.timestamp() * 1000) if dm.latest_message_time else int(timezone.now().timestamp() * 1000),
                'unread': dm.unread_count or 0,
                'is_group': True,
                'group_name': group_name,
            })
    
    print(f"✅ Found {len(dms_data)} DMs for user")
    
    # ========== GET OTHER USERS IN ORGANIZATION ==========
    # Get all ACTIVE users in the same organization (excluding current user)
    org_users = User.objects.filter(
        organization=organization,
        is_active=True
    ).exclude(uid=user.uid)
    
    print(f"🔍 Total users in org '{organization.name}': {User.objects.filter(organization=organization).count()}")
    print(f"🔍 Other users (excluding current): {org_users.count()}")
    
    members_data = []
    for org_user in org_users:
        # Get display name
        display_name = org_user.email.split('@')[0]
        avatar = None
        
        # Try to get from member profile
        try:
            member_profile = org_user.member_profile
            if member_profile:
                display_name = member_profile.full_name
                if member_profile.photo:
                    avatar = request.build_absolute_uri(member_profile.photo.url)
        except AttributeError:
            pass
        
        # Get role
        role = 'Member'
        if org_user.is_pastor:
            role = 'Pastor'
        elif org_user.is_hod:
            role = 'Head of Department'
        elif org_user.is_admin:
            role = 'Admin'
        elif org_user.is_owner:
            role = 'Owner'
        elif org_user.is_worker:
            role = 'Worker'
        elif org_user.is_volunteer:
            role = 'Volunteer'
        
        # Fallback to user's first_name + last_name
        if display_name == org_user.email.split('@')[0]:
            if org_user.first_name:
                name_parts = [org_user.first_name.strip()]
                if org_user.last_name and org_user.last_name.strip() and org_user.last_name != org_user.email:
                    name_parts.append(org_user.last_name.strip())
                name = " ".join(name_parts).strip()
                if name:
                    display_name = name
        
        members_data.append({
            'id': str(org_user.uid),
            'name': display_name,
            'avatar': avatar,
            'role': role,
            'email': org_user.email,
        })
    
    print(f"✅ Prepared {len(members_data)} users for chat list")
    
    # Calculate total unread
    total_unread = sum([c['unread_count'] for c in channels_data]) + sum([d['unread'] for d in dms_data])
    
    # Build response
    response_data = {
        'success': True,
        'channels': channels_data,
        'directMessages': dms_data,
        'organizationMembers': members_data,
        'total_unread': total_unread,
        'user': {
            'id': str(user.uid),
            'name': user_display_name,
            'avatar': request.build_absolute_uri(user_avatar) if user_avatar else None,
            'organization_name': organization.name,
        },
    }
    
    return Response(response_data)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def channel_create_api_view(request):
    """
    Create a new channel - FIXED VERSION
    """
    user = request.user
    organization = get_user_organization(user)
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    name = request.data.get('name', '').strip().lower()
    description = request.data.get('description', '').strip()
    is_public = request.data.get('is_public', True)
    is_read_only = request.data.get('is_read_only', False)
    
    if not name:
        return Response(
            {'success': False, 'error': 'Channel name is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate name format
    name = name.replace(' ', '-')
    
    # Check if channel already exists
    if Channel.objects.filter(organization=organization, name=name).exists():
        return Response(
            {'success': False, 'error': f'Channel #{name} already exists'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Create channel
        channel = Channel.objects.create(
            organization=organization,
            name=name,
            description=description,
            is_public=is_public,
            is_read_only=is_read_only,
            created_by=user
        )
        
        # Auto-join creator
        ChannelMembership.objects.create(
            channel=channel,
            user=user
        )
        
        # If public, auto-join all organization members
        if is_public:
            # Get all USERS in the organization (not Members)
            org_users = User.objects.filter(organization=organization, is_active=True)
            for org_user in org_users:
                ChannelMembership.objects.get_or_create(
                    channel=channel,
                    user=org_user
                )
        
        # Get creator name for welcome message
        creator_name = user.email.split('@')[0]
        try:
            if hasattr(user, 'member_profile') and user.member_profile:
                creator_name = user.member_profile.full_name
        except AttributeError:
            pass
        
        # Fallback to user's first_name + last_name
        if creator_name == user.email.split('@')[0]:
            if user.first_name:
                name_parts = [user.first_name.strip()]
                if user.last_name and user.last_name.strip() and user.last_name != user.email:
                    name_parts.append(user.last_name.strip())
                name = " ".join(name_parts).strip()
                if name:
                    creator_name = name
        
        # Send welcome message
        Message.objects.create(
            channel=channel,
            sender=user,
            content=f"Welcome to #{channel.name}! This channel was created by {creator_name}."
        )
        
        return Response({
            'success': True,
            'message': f'Channel #{channel.name} created successfully',
            'channel': {
                'id': str(channel.id),
                'name': channel.name,
                'display_name': channel.name.replace('-', ' ').title(),
                'description': channel.description,
                'is_public': channel.is_public,
                'is_read_only': channel.is_read_only,
                'created_at': channel.created_at.isoformat(),
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def channel_detail_api_view(request, channel_id):
    """Get channel details and messages"""
    try:
        channel = Channel.objects.get(id=channel_id, organization=request.user.organization)
    except Channel.DoesNotExist:
        return Response({'success': False, 'error': 'Channel not found'}, status=404)
    
    # Check if user is member
    if not ChannelMembership.objects.filter(channel=channel, user=request.user).exists():
        return Response({'success': False, 'error': 'Not a member of this channel'}, status=403)
    
    # Get paginated messages
    page = int(request.query_params.get('page', 1))
    limit = int(request.query_params.get('limit', 50))
    offset = (page - 1) * limit
    
    messages_qs = Message.objects.filter(channel=channel).select_related('sender').order_by('-created_at')
    total_messages = messages_qs.count()
    messages = messages_qs[offset:offset + limit]
    
    # Format messages
    messages_data = []
    for msg in messages:
        # Get sender display name
        sender_name = msg.sender.email.split('@')[0]
        sender_avatar = None
        
        try:
            member_profile = msg.sender.member_profile
            if member_profile:
                sender_name = member_profile.full_name
                if member_profile.photo:
                    sender_avatar = request.build_absolute_uri(member_profile.photo.url)
        except AttributeError:
            pass
        
        messages_data.append({
            'id': str(msg.id),
            'content': msg.content,
            'sender': {
                'id': str(msg.sender.uid),
                'name': sender_name,
                'avatar': sender_avatar,
            },
            'created_at': msg.created_at.isoformat(),
            'created_at_timestamp': int(msg.created_at.timestamp() * 1000),
        })
    
    # Get channel members (Users who are members)
    channel_memberships = ChannelMembership.objects.filter(channel=channel).select_related('user')
    members_data = []
    
    for membership in channel_memberships:
        member_user = membership.user
        
        # Get display name
        display_name = member_user.email.split('@')[0]
        avatar = None
        
        try:
            member_profile = member_user.member_profile
            if member_profile:
                display_name = member_profile.full_name
                if member_profile.photo:
                    avatar = request.build_absolute_uri(member_profile.photo.url)
        except AttributeError:
            pass
        
        members_data.append({
            'id': str(member_user.uid),
            'name': display_name,
            'avatar': avatar,
            'joined_at': membership.joined_at.isoformat(),
        })
    
    # Get channel info
    channel_data = {
        'id': str(channel.id),
        'name': channel.name,
        'display_name': channel.name.replace('-', ' ').title(),
        'description': channel.description or '',
        'is_public': channel.is_public,
        'is_read_only': channel.is_read_only,
        'member_count': len(members_data),
        'created_by': None,
        'created_at': channel.created_at.isoformat(),
    }
    
    # Get creator info if available
    if channel.created_by:
        creator_name = channel.created_by.email.split('@')[0]
        try:
            creator_profile = channel.created_by.member_profile
            if creator_profile:
                creator_name = creator_profile.full_name
        except AttributeError:
            pass
        channel_data['created_by'] = creator_name
    
    return Response({
        'success': True,
        'channel': channel_data,
        'messages': messages_data,
        'members': members_data,
        'pagination': {
            'page': page,
            'limit': limit,
            'has_more': (offset + limit) < total_messages,
            'total_messages': total_messages,
        },
        'permissions': {
            'can_post': not channel.is_read_only,
            'can_manage': request.user.is_admin or request.user.is_owner,
        }
    })



@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def send_channel_message_api_view(request, channel_id):
    """
    Send message to a channel
    """
    user = request.user
    organization = get_user_organization(user)
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        channel = Channel.objects.get(id=channel_id, organization=organization)
    except Channel.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Channel not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions
    if channel.is_read_only:
        if not (user.is_staff or user.is_superuser):
            return Response(
                {'success': False, 'error': 'This channel is read-only'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    
    # Check if user is member
    if not channel.is_public:
        if not ChannelMembership.objects.filter(channel=channel, user=user).exists():
            return Response(
                {'success': False, 'error': 'You are not a member of this channel'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    
    content = request.data.get('content', '').strip()
    if not content:
        return Response(
            {'success': False, 'error': 'Message content is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get reply_to message ID if provided
    reply_to_id = request.data.get('reply_to')
    reply_to_message = None
    
    if reply_to_id:
        try:
            reply_to_message = Message.objects.get(
                id=reply_to_id,
                channel=channel
            )
        except Message.DoesNotExist:
            # If reply_to message doesn't exist, just ignore it
            pass
    
    try:
        # Create message with reply_to reference
        message = Message.objects.create(
            channel=channel,
            sender=user,
            content=content,
            reply_to=reply_to_message  # Add this
        )
        
        # Mark as read by sender
        message.read_by.add(user)
        
        # Get sender info for response
        try:
            sender_info = {
                'id': str(user.uid),
                'name': user.member_profile.full_name,
                'avatar': request.build_absolute_uri(user.member_profile.photo.url) if user.member_profile.photo else None,
                'role': user.member_profile.family_role,
            }
        except AttributeError:
            sender_info = {
                'id': str(user.uid),
                'name': user.username,
                'avatar': None,
            }
        
        # Prepare response with reply_to info
        message_data = {
            'id': str(message.id),
            'content': message.content,
            'sender': sender_info,
            'created_at': message.created_at.isoformat(),
            'created_at_timestamp': int(message.created_at.timestamp() * 1000),
        }
        
        # Add reply_to to response if exists
        if message.reply_to:
            message_data['reply_to'] = str(message.reply_to.id)
        
        return Response({
            'success': True,
            'message': 'Message sent successfully',
            'message_id': str(message.id),
            'message': message_data,  # Use the updated message_data
            'target': {
                'type': 'channel',
                'id': str(channel.id),
                'name': channel.name,
            },
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )








@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def start_dm_api_view(request):
    """
    Start a new DM conversation - FIXED VERSION
    """
    user = request.user
    
    # Get user's organization from User model (same as chat_home_api_view)
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    target_user_id = request.data.get('user_id')
    if not target_user_id:
        return Response(
            {'success': False, 'error': 'User ID is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Use uid to find the user
        target_user = User.objects.get(uid=target_user_id)
    except User.DoesNotExist:
        return Response(
            {'success': False, 'error': 'User not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # SIMPLE CHECK: Just check if target_user has the same organization
    # NO MEMBER PROFILE CHECK NEEDED!
    if target_user.organization != organization:
        return Response(
            {'success': False, 'error': 'User is not in your organization'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get or create DM thread
    dm_thread = DirectMessage.get_or_create_dm(user, target_user, organization)
    
    # Get other user display name (SAME LOGIC AS chat_home_api_view)
    display_name = target_user.email.split('@')[0]
    avatar = None
    
    # Try to get from member profile
    try:
        member_profile = target_user.member_profile
        if member_profile:
            display_name = member_profile.full_name
            if member_profile.photo:
                avatar = request.build_absolute_uri(member_profile.photo.url)
    except AttributeError:
        pass  # No member profile, that's OK!
    
    # Get role (same as chat_home_api_view)
    role = 'Member'
    if target_user.is_pastor:
        role = 'Pastor'
    elif target_user.is_hod:
        role = 'Head of Department'
    elif target_user.is_admin:
        role = 'Admin'
    elif target_user.is_owner:
        role = 'Owner'
    elif target_user.is_worker:
        role = 'Worker'
    elif target_user.is_volunteer:
        role = 'Volunteer'
    
    # Fallback to user's first_name + last_name
    if display_name == target_user.email.split('@')[0]:
        if target_user.first_name:
            name_parts = [target_user.first_name.strip()]
            if target_user.last_name and target_user.last_name.strip() and target_user.last_name != target_user.email:
                name_parts.append(target_user.last_name.strip())
            name = " ".join(name_parts).strip()
            if name:
                display_name = name
    
    other_user_info = {
        'id': str(target_user.uid),
        'name': display_name,
        'avatar': avatar,
        'role': role,
        'email': target_user.email,
    }
    
    return Response({
        'success': True,
        'message': 'Direct message thread created',
        'dm_thread': {
            'id': str(dm_thread.id),
            'created_at': dm_thread.created_at.isoformat(),
            'updated_at': dm_thread.updated_at.isoformat(),
        },
        'other_user': other_user_info,
    })


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def dm_detail_api_view(request, dm_id):
    """
    Get DM thread details and messages - FIXED VERSION with reply_to
    """
    user = request.user
    
    # Get user's organization from User model
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        dm_thread = DirectMessage.objects.get(id=dm_id, organization=organization)
    except DirectMessage.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Conversation not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user is participant
    if not dm_thread.participants.filter(uid=user.uid).exists():
        return Response(
            {'success': False, 'error': 'You are not a participant in this conversation'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get messages with pagination
    page = int(request.query_params.get('page', 1))
    limit = int(request.query_params.get('limit', 50))
    offset = (page - 1) * limit
    
    # Get messages (oldest first for chat UI) with select_related for reply_to
    messages = Message.objects.filter(
        direct_message=dm_thread
    ).select_related('sender', 'reply_to').order_by('created_at')[offset:offset + limit]
    
    # Get other participant(s)
    other_participants = dm_thread.participants.exclude(uid=user.uid)
    participants_data = []
    
    for participant in other_participants:
        # Get display name
        display_name = participant.email.split('@')[0]
        avatar = None
        
        # Try to get from member profile
        try:
            member_profile = participant.member_profile
            if member_profile:
                display_name = member_profile.full_name
                if member_profile.photo:
                    avatar = request.build_absolute_uri(member_profile.photo.url)
        except AttributeError:
            pass
        
        # Get role
        role = 'Member'
        if participant.is_pastor:
            role = 'Pastor'
        elif participant.is_hod:
            role = 'Head of Department'
        elif participant.is_admin:
            role = 'Admin'
        elif participant.is_owner:
            role = 'Owner'
        elif participant.is_worker:
            role = 'Worker'
        elif participant.is_volunteer:
            role = 'Volunteer'
        
        # Fallback to user's first_name + last_name
        if display_name == participant.email.split('@')[0]:
            if participant.first_name:
                name_parts = [participant.first_name.strip()]
                if participant.last_name and participant.last_name.strip() and participant.last_name != participant.email:
                    name_parts.append(participant.last_name.strip())
                name = " ".join(name_parts).strip()
                if name:
                    display_name = name
        
        participants_data.append({
            'id': str(participant.uid),
            'name': display_name,
            'avatar': avatar,
            'role': role,
            'email': participant.email,
        })
    
    # Format messages WITH reply_to
    messages_data = []
    for msg in messages:
        # Get sender info with fallbacks
        sender_info = None
        if msg.sender:
            # Get display name
            display_name = msg.sender.email.split('@')[0]
            avatar = None
            
            # Try to get from member profile
            try:
                member_profile = msg.sender.member_profile
                if member_profile:
                    display_name = member_profile.full_name
                    if member_profile.photo:
                        avatar = request.build_absolute_uri(member_profile.photo.url)
            except AttributeError:
                pass
            
            # Get role
            role = 'Member'
            if msg.sender.is_pastor:
                role = 'Pastor'
            elif msg.sender.is_hod:
                role = 'Head of Department'
            elif msg.sender.is_admin:
                role = 'Admin'
            elif msg.sender.is_owner:
                role = 'Owner'
            elif msg.sender.is_worker:
                role = 'Worker'
            elif msg.sender.is_volunteer:
                role = 'Volunteer'
            
            # Fallback to user's first_name + last_name
            if display_name == msg.sender.email.split('@')[0]:
                if msg.sender.first_name:
                    name_parts = [msg.sender.first_name.strip()]
                    if msg.sender.last_name and msg.sender.last_name.strip() and msg.sender.last_name != msg.sender.email:
                        name_parts.append(msg.sender.last_name.strip())
                    name = " ".join(name_parts).strip()
                    if name:
                        display_name = name
            
            sender_info = {
                'id': str(msg.sender.uid),
                'name': display_name,
                'avatar': avatar,
                'role': role,
            }
        
        # Build message data
        message_data = {
            'id': str(msg.id),
            'content': msg.content,
            'sender': sender_info,
            'created_at': msg.created_at.isoformat(),
            'created_at_timestamp': int(msg.created_at.timestamp() * 1000),
        }
        
        # ADD reply_to if it exists
        if msg.reply_to:
            message_data['reply_to'] = str(msg.reply_to.id)
            
            # Optionally include replied message preview data
            try:
                replied_sender_name = msg.reply_to.sender.member_profile.full_name if hasattr(msg.reply_to.sender, 'member_profile') else msg.reply_to.sender.username
                message_data['reply_to_preview'] = {
                    'content': msg.reply_to.content[:100],  # First 100 chars
                    'sender_name': replied_sender_name,
                    'sender_id': str(msg.reply_to.sender.uid)
                }
            except:
                pass
        
        messages_data.append(message_data)
    
    # Get thread info
    # Check if is_group exists, default to False
    is_group = getattr(dm_thread, 'is_group', False)
    
    thread_info = {
        'id': str(dm_thread.id),
        'is_group': is_group,
        'participants': participants_data,
        'created_at': dm_thread.created_at.isoformat(),
        'updated_at': dm_thread.updated_at.isoformat(),
    }
    
    return Response({
        'success': True,
        'dm_thread': thread_info,
        'messages': messages_data,
        'pagination': {
            'page': page,
            'limit': limit,
            'has_more': Message.objects.filter(direct_message=dm_thread).count() > (offset + limit),
            'total_messages': Message.objects.filter(direct_message=dm_thread).count(),
        }
    })

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def send_dm_message_api_view(request, dm_id):
    """
    Send message to a DM thread
    """
    user = request.user
    organization = get_user_organization(user)
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        dm_thread = DirectMessage.objects.get(id=dm_id, organization=organization)
    except DirectMessage.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Conversation not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user is participant
    if not dm_thread.participants.filter(uid=user.uid).exists():
        return Response(
            {'success': False, 'error': 'You are not a participant in this conversation'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    content = request.data.get('content', '').strip()
    if not content:
        return Response(
            {'success': False, 'error': 'Message content is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get reply_to message ID if provided
    reply_to_id = request.data.get('reply_to')
    reply_to_message = None
    
    if reply_to_id:
        try:
            reply_to_message = Message.objects.get(
                id=reply_to_id,
                direct_message=dm_thread
            )
        except Message.DoesNotExist:
            # If reply_to message doesn't exist, just ignore it
            pass
    
    try:
        # Create message with reply_to reference
        message = Message.objects.create(
            direct_message=dm_thread,
            sender=user,
            content=content,
            reply_to=reply_to_message
        )
        
        # Mark as read by sender
        message.read_by.add(user)
        
        # Get sender info for response
        try:
            sender_info = {
                'id': str(user.uid),
                'name': user.member_profile.full_name,
                'avatar': request.build_absolute_uri(user.member_profile.photo.url) if user.member_profile.photo else None,
                'role': user.member_profile.family_role,
            }
        except AttributeError:
            sender_info = {
                'id': str(user.uid),
                'name': user.username,
                'avatar': None,
            }
        
        # Prepare response with reply_to info
        message_data = {
            'id': str(message.id),
            'content': message.content,
            'sender': sender_info,
            'created_at': message.created_at.isoformat(),
            'created_at_timestamp': int(message.created_at.timestamp() * 1000),
        }
        
        # Add reply_to to response if exists
        if message.reply_to:
            message_data['reply_to'] = str(message.reply_to.id)
            # Also include the replied message content for preview
            try:
                message_data['reply_to_message'] = {
                    'id': str(message.reply_to.id),
                    'content': message.reply_to.content,
                    'sender_name': message.reply_to.sender.member_profile.full_name if hasattr(message.reply_to.sender, 'member_profile') else message.reply_to.sender.username
                }
            except:
                pass
        
        return Response({
            'success': True,
            'message': 'Message sent successfully',
            'message_id': str(message.id),
            'message': message_data,  # Use the updated message_data
            'target': {
                'type': 'dm',
                'id': str(dm_thread.id),
                'is_group': False,
            },
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_messages_read_api_view(request):
    """
    Mark messages as read
    """
    user = request.user
    organization = get_user_organization(user)
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    message_type = request.data.get('type')  # 'channel' or 'dm'
    target_id = request.data.get('target_id')
    
    if not message_type or not target_id:
        return Response(
            {'success': False, 'error': 'Type and target ID are required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        if message_type == 'channel':
            channel = Channel.objects.get(id=target_id, organization=organization)
            
            # Update last read time
            membership, _ = ChannelMembership.objects.get_or_create(
                channel=channel,
                user=user
            )
            membership.last_read_at = timezone.now()
            membership.save()
            
        elif message_type == 'dm':
            dm_thread = DirectMessage.objects.get(id=target_id, organization=organization)
            
            # Mark all messages in DM as read for this user
            messages = Message.objects.filter(direct_message=dm_thread)
            for message in messages:
                message.read_by.add(user)
        
        else:
            return Response(
                {'success': False, 'error': 'Invalid type. Use "channel" or "dm"'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({
            'success': True,
            'message': f'Messages marked as read for {message_type}',
        })
        
    except (Channel.DoesNotExist, DirectMessage.DoesNotExist):
        return Response(
            {'success': False, 'error': 'Target not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_message_api_view(request, message_id):
    """
    Delete a message
    """
    user = request.user
    organization = get_user_organization(user)
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        message = Message.objects.get(id=message_id)
        
        # Check if user owns the message or is admin
        if message.sender != user and not (user.is_staff or user.is_superuser):
            return Response(
                {'success': False, 'error': 'You can only delete your own messages'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        message.delete()
        
        return Response({
            'success': True,
            'message': 'Message deleted'
        })
        
    except Message.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Message not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )