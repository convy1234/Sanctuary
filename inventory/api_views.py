
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