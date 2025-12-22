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
from church.views import get_user_organization

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

from church.models import Department
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

from member.models import Member
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
