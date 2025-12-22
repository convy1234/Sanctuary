from django.db.models import Q, Sum, Count
from django.contrib import messages
from django.core.paginator import Paginator
import json
from datetime import datetime
from .models import VoucherTemplate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods


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


