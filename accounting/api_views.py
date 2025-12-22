from django.db.models import Q, Sum, Count
from django.contrib import messages
from django.core.paginator import Paginator
import json
from rest_framework_simplejwt.authentication import JWTAuthentication
from datetime import datetime
from .models import VoucherTemplate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view, authentication_classes, permission_classes

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from church.views import get_user_organization
from church.models import Voucher
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




