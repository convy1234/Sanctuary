from rest_framework import serializers
from accounts.serializers import UserSerializer
from church.serializers import DepartmentSerializer, OrganizationSerializer
from .models import (
    InventoryCategory,
    InventoryVendor,
    InventoryItem, InventoryTransaction, InventoryCheckout, InventoryAudit, InventoryAuditItem)
from member.serializers import MemberSerializer
from church.models import Department, Member, Organization
from django.utils import timezone

class InventoryCategorySerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    category_type_display = serializers.CharField(source='get_category_type_display', read_only=True)
    
    class Meta:
        model = InventoryCategory
        fields = [
            'id', 'organization', 'name', 'category_type', 
            'category_type_display', 'color_code', 'description',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        # Set organization from request context
        validated_data['organization'] = self.context['request'].user.organization
        return super().create(validated_data)


class InventoryVendorSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    
    class Meta:
        model = InventoryVendor
        fields = [
            'id', 'organization', 'name', 'contact_person', 'email',
            'phone', 'website', 'account_number', 'notes', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        validated_data['organization'] = self.context['request'].user.organization
        return super().create(validated_data)


class InventoryItemSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)
    category = InventoryCategorySerializer(read_only=True)
    vendor = InventoryVendorSerializer(read_only=True)
    
    # For write operations
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        write_only=True,
        source='department',
        required=False,
        allow_null=True
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=InventoryCategory.objects.all(),
        write_only=True,
        source='category',
        required=False,
        allow_null=True
    )
    vendor_id = serializers.PrimaryKeyRelatedField(
        queryset=InventoryVendor.objects.all(),
        write_only=True,
        source='vendor',
        required=False,
        allow_null=True
    )
    
    # Computed fields
    total_value = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    status = serializers.CharField(read_only=True)
    item_type_display = serializers.CharField(source='get_item_type_display', read_only=True)
    condition_display = serializers.CharField(source='get_condition_display', read_only=True)
    
    # Image handling
    image_url = serializers.SerializerMethodField()
    image = serializers.ImageField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = InventoryItem
        fields = [
            'id', 'organization', 'name', 'description', 'sku', 'barcode',
            'asset_tag', 'quantity', 'reorder_level', 'reorder_quantity',
            'alert_on_low', 'location', 'condition', 'condition_display',
            'item_type', 'item_type_display', 'storage_instructions',
            'purchase_price', 'total_value', 'purchase_date',
            'warranty_expiry', 'replacement_cost', 'is_active',
            'last_audited', 'last_checked_out', 'notes', 'is_low_stock',
            'status', 'image', 'image_url',
            
            # Relationships (read)
            'department', 'category', 'vendor',
            
            # Relationships (write)
            'department_id', 'category_id', 'vendor_id',
            
            # Timestamps
            'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = [
            'id', 'organization', 'total_value', 'is_low_stock', 'status',
            'last_audited', 'last_checked_out', 'created_at', 'updated_at',
            'created_by', 'image_url'
        ]
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None
    
    def create(self, validated_data):
        # Set organization and created_by from request context
        request = self.context.get('request')
        if request and request.user:
            validated_data['organization'] = request.user.organization
            validated_data['created_by'] = request.user
        
        # Generate SKU if not provided
        if not validated_data.get('sku'):
            # Generate a simple SKU
            from django.utils.text import slugify
            name_slug = slugify(validated_data['name'])[:20].upper()
            validated_data['sku'] = f"ITEM-{name_slug}-{timezone.now().strftime('%y%m%d')}"
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Handle image clearing
        if 'image' in validated_data and validated_data['image'] is None:
            instance.image.delete(save=False)
        return super().update(instance, validated_data)


class InventoryTransactionSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    item = InventoryItemSerializer(read_only=True)
    from_department = DepartmentSerializer(read_only=True)
    to_department = DepartmentSerializer(read_only=True)
    performed_by = serializers.StringRelatedField()
    approved_by = serializers.StringRelatedField()
    
    # For write operations
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=InventoryItem.objects.all(),
        write_only=True,
        source='item'
    )
    from_department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        write_only=True,
        source='from_department',
        required=False,
        allow_null=True
    )
    to_department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        write_only=True,
        source='to_department',
        required=False,
        allow_null=True
    )
    
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    
    class Meta:
        model = InventoryTransaction
        fields = [
            'id', 'organization', 'movement_number', 'transaction_type',
            'transaction_type_display', 'source_type', 'source_type_display',
            'item', 'item_id', 'quantity', 'from_department', 'from_department_id',
            'to_department', 'to_department_id', 'reference_number',
            'unit_price', 'total_value', 'movement_date', 'notes',
            'performed_by', 'approved_by', 'approved_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'organization', 'movement_number', 'total_value',
            'performed_by', 'approved_by', 'approved_at',
            'created_at', 'updated_at'
        ]
    
    def create(self, validated_data):
        # Set organization and performed_by from request context
        request = self.context.get('request')
        if request and request.user:
            validated_data['organization'] = request.user.organization
            validated_data['performed_by'] = request.user
            
            # Auto-approve if user has permission
            user = request.user
            can_approve = (
                user.is_staff or 
                getattr(user, "is_owner", False) or 
                getattr(user, "is_admin", False) or 
                getattr(user, "is_pastor", False)
            )
            if can_approve:
                validated_data['approved_by'] = request.user
                validated_data['approved_at'] = timezone.now()
        
        return super().create(validated_data)


class InventoryCheckoutSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    item = InventoryItemSerializer(read_only=True)
    member = MemberSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)
    created_by = serializers.StringRelatedField()
    approved_by = serializers.StringRelatedField()
    
    # For write operations
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=InventoryItem.objects.all(),
        write_only=True,
        source='item'
    )
    member_id = serializers.PrimaryKeyRelatedField(
        queryset=Member.objects.all(),
        write_only=True,
        source='member'
    )
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        write_only=True,
        source='department'
    )
    
    # Computed fields
    is_overdue = serializers.BooleanField(read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    returned_condition_display = serializers.CharField(source='get_returned_condition_display', read_only=True)
    
    class Meta:
        model = InventoryCheckout
        fields = [
            'id', 'organization', 'item', 'item_id', 'member', 'member_id',
            'department', 'department_id', 'quantity', 'purpose', 'event_name',
            'checkout_date', 'due_date', 'expected_return_date', 'status',
            'status_display', 'returned_quantity', 'returned_at',
            'returned_condition', 'returned_condition_display', 'return_notes',
            'approved_by', 'approved_at', 'is_overdue', 'days_overdue',
            'created_by', 'created_at', 'updated_at', 'notes'
        ]
        read_only_fields = [
            'id', 'organization', 'is_overdue', 'days_overdue',
            'returned_quantity', 'returned_at', 'returned_condition',
            'return_notes', 'approved_by', 'approved_at', 'created_by',
            'created_at', 'updated_at'
        ]
    
    def create(self, validated_data):
        # Set organization and created_by from request context
        request = self.context.get('request')
        if request and request.user:
            validated_data['organization'] = request.user.organization
            validated_data['created_by'] = request.user
            
            # Auto-approve if user has permission
            user = request.user
            can_approve = (
                user.is_staff or 
                getattr(user, "is_owner", False) or 
                getattr(user, "is_admin", False) or 
                getattr(user, "is_pastor", False)
            )
            if can_approve:
                validated_data['approved_by'] = request.user
                validated_data['approved_at'] = timezone.now()
                validated_data['status'] = 'active'
            else:
                validated_data['status'] = 'active'  # Or 'pending' if you want approval workflow
        
        return super().create(validated_data)
    
    def validate(self, data):
        # Check if item has enough stock
        item = data.get('item')
        quantity = data.get('quantity', 0)
        
        if item and quantity > item.quantity:
            raise serializers.ValidationError(
                f"Only {item.quantity} available in stock. Requested: {quantity}"
            )
        
        # Validate due date is not in the past
        due_date = data.get('due_date')
        if due_date and due_date < timezone.now().date():
            raise serializers.ValidationError("Due date cannot be in the past")
        
        return data


class InventoryAuditSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)
    auditor = serializers.StringRelatedField()
    verified_by = serializers.StringRelatedField()
    
    # For write operations
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        write_only=True,
        source='department',
        required=False,
        allow_null=True
    )
    
    audit_type_display = serializers.CharField(source='get_audit_type_display', read_only=True)
    
    class Meta:
        model = InventoryAudit
        fields = [
            'id', 'organization', 'audit_number', 'name', 'description',
            'audit_type', 'audit_type_display', 'department', 'department_id',
            'auditor', 'participants', 'start_date', 'end_date',
            'total_items', 'items_checked', 'discrepancies_found',
            'accuracy_percentage', 'notes', 'is_completed',
            'verified_by', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'organization', 'audit_number', 'total_items',
            'items_checked', 'discrepancies_found', 'accuracy_percentage',
            'verified_by', 'created_at', 'updated_at'
        ]
    
    def create(self, validated_data):
        # Set organization and auditor from request context
        request = self.context.get('request')
        if request and request.user:
            validated_data['organization'] = request.user.organization
            validated_data['auditor'] = request.user
        
        return super().create(validated_data)


class InventoryAuditItemSerializer(serializers.ModelSerializer):
    audit = InventoryAuditSerializer(read_only=True)
    item = InventoryItemSerializer(read_only=True)
    counted_by = serializers.StringRelatedField()
    
    # For write operations
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=InventoryItem.objects.all(),
        write_only=True,
        source='item'
    )
    
    discrepancy_type_display = serializers.CharField(source='get_discrepancy_type_display', read_only=True)
    
    class Meta:
        model = InventoryAuditItem
        fields = [
            'id', 'audit', 'item', 'item_id', 'expected_quantity',
            'counted_quantity', 'difference', 'discrepancy_type',
            'discrepancy_type_display', 'discrepancy_value', 'notes',
            'adjusted', 'counted_by', 'counted_at'
        ]
        read_only_fields = [
            'id', 'difference', 'discrepancy_value', 'counted_by',
            'counted_at'
        ]