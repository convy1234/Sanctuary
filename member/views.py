from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse, HttpResponseNotFound
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q  # ADD THIS IMPORT
from django.views.decorators.http import require_http_methods

from .models import Member, Campus, Department, Family
from church.views import get_user_organization

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets, filters
from rest_framework_simplejwt.authentication import JWTAuthentication
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import MemberSerializer, DepartmentSerializer, FamilySerializer, CampusSerializer

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
    family_id = request.GET.get('family')
    department_id = request.GET.get('department')
    
    # Build queryset (same logic for both)
    members = Member.objects.filter(organization=organization)
    
    if status_filter:
        members = members.filter(status=status_filter)
    
    if search:
        members = members.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search) |
            Q(family__family_name__icontains=search)
        )
    
    if family_id:
        members = members.filter(family_id=family_id)
    
    if department_id:
        members = members.filter(departments__id=department_id)
    
    members = members.distinct()
    families = Family.objects.filter(organization=organization)
    departments = Department.objects.filter(organization=organization)
    active_count = members.filter(status='active').count()
    new_count = members.filter(status='new').count()
    visitor_count = members.filter(status='visitor').count()
    
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
    return render(
        request,
        'members/list.html',
        {
            'members': members,
            'families': families,
            'departments': departments,
            'active_count': active_count,
            'new_count': new_count,
            'visitor_count': visitor_count,
            'organization': organization,
        },
    )

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
        user.is_staff
        or getattr(user, "is_owner", False)
        or getattr(user, "is_admin", False)
        or getattr(user, "is_pastor", False)
    )

    if not can_delete:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({'error': 'Permission denied'}, status=403)
        return HttpResponseForbidden("Permission denied")

    if request.method in ["DELETE", "POST"]:
        soft_delete = request.POST.get("soft_delete", False) or (
            request.headers.get("x-requested-with") == "XMLHttpRequest"
            and request.GET.get("soft_delete", "false").lower() == "true"
        )

        member_name = member.full_name
        member_email = member.email

        if soft_delete:
            member.status = "inactive"
            member.save()
            message = f"Member '{member_name}' has been deactivated."
            success_message = "Member deactivated successfully"
        else:
            member.delete()
            message = f"Member '{member_name}' has been permanently deleted."
            success_message = "Member deleted successfully"

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": message,
                    "soft_delete": soft_delete,
                    "deleted_member": {
                        "id": str(member.id) if soft_delete else member_id,
                        "name": member_name,
                        "email": member_email,
                    },
                }
            )

        messages.success(request, success_message)
        return redirect("member_list")

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "member": {
                    "id": str(member.id),
                    "full_name": member.full_name,
                    "email": member.email,
                    "status": member.status,
                    "join_date": member.join_date.isoformat() if member.join_date else None,
                    "member_since": member.created_at.strftime("%Y-%m-%d"),
                },
                "warning": "This action cannot be undone for hard delete.",
                "soft_delete_note": "Soft delete will change status to inactive instead of deleting.",
            }
        )

    return render(request, "members/delete_confirm.html", {"member": member})

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


# ----------------- Helpers for member API -----------------
def format_date_for_model(date_value):
    """Helper to convert various date formats to YYYY-MM-DD."""
    if not date_value:
        return None
    from datetime import datetime

    if isinstance(date_value, str):
        formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S",
        ]
        for fmt in formats:
            try:
                date_obj = datetime.strptime(date_value, fmt)
                return date_obj.strftime("%Y-%m-%d")
            except ValueError:
                continue
    if isinstance(date_value, datetime):
        return date_value.strftime("%Y-%m-%d")
    return None


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def member_create_api_view(request):
    organization = get_user_organization(request.user)
    if not organization:
        return Response({"error": "No organization assigned"}, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    can_create = user.is_staff or getattr(user, "is_owner", False) or getattr(user, "is_admin", False) or getattr(user, "is_pastor", False)
    if not can_create:
        return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

    data = request.data.copy()
    data["organization"] = str(organization.id)

    date_fields = ["date_of_birth", "join_date", "baptism_date"]
    for field in date_fields:
        if field in data and data[field]:
            formatted_date = format_date_for_model(data[field])
            data[field] = formatted_date if formatted_date else None
        elif field in data and data[field] == "":
            data[field] = None

    phone_fields = ["phone", "next_of_kin_phone"]
    for field in phone_fields:
        if field in data and data[field]:
            phone = "".join(filter(str.isdigit, str(data[field])))
            data[field] = phone if phone else ""
        elif field in data and data[field] == "":
            data[field] = ""

    serializer = MemberSerializer(data=data, context={"request": request})
    if serializer.is_valid():
        member = serializer.save(created_by=request.user)
        return Response(
            {
                "success": True,
                "message": "Member created successfully",
                "member_id": str(member.id),
                "member": MemberSerializer(member, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )

    errors = {}
    for field, error_list in serializer.errors.items():
        if isinstance(error_list, list):
            errors[field] = error_list[0] if error_list else "Invalid value"
        else:
            errors[field] = str(error_list)
    return Response({"success": False, "message": "Validation failed", "errors": errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PUT", "PATCH"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def member_update_api_view(request, member_id):
    try:
        organization = get_user_organization(request.user)
        if not organization:
            return Response({"error": "No organization assigned"}, status=status.HTTP_400_BAD_REQUEST)

        member = Member.objects.get(id=member_id, organization=organization)
        user = request.user
        can_edit = user.is_staff or getattr(user, "is_owner", False) or getattr(user, "is_admin", False) or getattr(user, "is_pastor", False)
        if not can_edit:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data.copy()
        data["organization"] = str(organization.id)

        date_fields = ["date_of_birth", "join_date", "baptism_date"]
        for field in date_fields:
            if field in data and data[field]:
                formatted_date = format_date_for_model(data[field])
                data[field] = formatted_date if formatted_date else None
            elif field in data and data[field] == "":
                data[field] = None

        phone_fields = ["phone", "next_of_kin_phone"]
        for field in phone_fields:
            if field in data and data[field]:
                phone = "".join(filter(str.isdigit, str(data[field])))
                data[field] = phone if phone else ""
            elif field in data and data[field] == "":
                data[field] = ""

        string_fields = [
            "email",
            "gender",
            "marital_status",
            "occupation",
            "address",
            "residential_city",
            "residential_state",
            "residential_country",
            "origin_city",
            "origin_state",
            "origin_country",
            "blood_type",
            "next_of_kin_name",
            "next_of_kin_relationship",
            "baptism_status",
            "notes",
            "family_role",
        ]
        for field in string_fields:
            if field in data and data[field] == "":
                data[field] = ""

        for field in ["campus", "family"]:
            if field in data and data[field] == "":
                data[field] = None

        is_partial = request.method == "PATCH"
        serializer = MemberSerializer(member, data=data, partial=is_partial, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "message": "Member updated successfully", "member": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Member.DoesNotExist:
        return Response({"error": "Member not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def member_delete_api_view(request, member_id):
    try:
        organization = get_user_organization(request.user)
        if not organization:
            return Response({"error": "No organization assigned"}, status=status.HTTP_400_BAD_REQUEST)

        member = Member.objects.get(id=member_id, organization=organization)
        user = request.user
        can_delete = user.is_staff or getattr(user, "is_owner", False) or getattr(user, "is_admin", False) or getattr(user, "is_pastor", False)
        if not can_delete:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        soft_delete = request.query_params.get("soft_delete", "false").lower() == "true"
        member_name = member.full_name

        if soft_delete:
            member.status = "inactive"
            member.save()
            return Response(
                {
                    "success": True,
                    "message": f"Member '{member_name}' has been deactivated.",
                    "soft_delete": True,
                    "deleted_member": {"id": str(member.id), "name": member_name, "email": member.email},
                }
            )
        member.delete()
        return Response(
            {
                "success": True,
                "message": f"Member '{member_name}' has been permanently deleted.",
                "soft_delete": False,
                "deleted_member": {"id": member_id, "name": member_name, "email": member.email},
            }
        )

    except Member.DoesNotExist:
        return Response({"error": "Member not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def member_statistics_api_view(request):
    organization = get_user_organization(request.user)
    if not organization:
        return Response({"error": "No organization assigned"}, status=status.HTTP_400_BAD_REQUEST)

    stats = {
        "total_members": Member.objects.filter(organization=organization).count(),
        "active_members": Member.objects.filter(organization=organization, status="active").count(),
        "new_members": Member.objects.filter(organization=organization, status="new").count(),
        "inactive_members": Member.objects.filter(organization=organization, status="inactive").count(),
        "visitor_count": Member.objects.filter(organization=organization, status="visitor").count(),
        "transferred_count": Member.objects.filter(organization=organization, status="transferred").count(),
        "deceased_count": Member.objects.filter(organization=organization, status="deceased").count(),
        "families": Family.objects.filter(organization=organization).count(),
        "departments": Department.objects.filter(organization=organization).count(),
        "campuses": Campus.objects.filter(organization=organization).count(),
    }
    return Response(stats)
