# church/serializers.py - COMPLETE VERSION
from rest_framework import serializers
from .models import Member, Campus, Family, Department, Organization
from accounts.serializers import UserSerializer

class SimpleMemberSerializer(serializers.ModelSerializer):
    """Lightweight serializer for lists."""
    full_name = serializers.ReadOnlyField()
    
    class Meta:
        model = Member
        fields = ['id', 'full_name', 'phone', 'email', 'status', 'photo']

class CampusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campus
        fields = ['id', 'name', 'address', 'phone', 'email', 'is_active']

class FamilySerializer(serializers.ModelSerializer):
    members = SimpleMemberSerializer(many=True, read_only=True)
    family_head_name = serializers.CharField(source='family_head.full_name', read_only=True)
    
    class Meta:
        model = Family
        fields = ['id', 'family_name', 'address', 'phone', 'email', 
                 'family_head', 'family_head_name', 'members']

class DepartmentSerializer(serializers.ModelSerializer):  # ✅ ADD THIS
    leader_name = serializers.CharField(source='leader.full_name', read_only=True)
    member_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Department
        fields = ['id', 'name', 'description', 'leader', 'leader_name', 
                 'member_count', 'is_active']
    
    def get_member_count(self, obj):
        return obj.members.count()

class OrganizationStatsSerializer(serializers.Serializer):
    """Serializer for organization dashboard statistics."""
    total_members = serializers.IntegerField()
    active_members = serializers.IntegerField()
    new_members = serializers.IntegerField()
    inactive_members = serializers.IntegerField()
    visitor_count = serializers.IntegerField()
    transferred_count = serializers.IntegerField()
    deceased_count = serializers.IntegerField()
    families = serializers.IntegerField()
    departments = serializers.IntegerField()
    campuses = serializers.IntegerField()

# Keep your existing MemberSerializer below this line
class MemberSerializer(serializers.ModelSerializer):
    """Serializer for Member model - optimized for mobile."""
    full_name = serializers.ReadOnlyField()
    age = serializers.ReadOnlyField()
    user = UserSerializer(read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    
    # ✅ EXPLICIT FIELD DEFINITIONS FOR OPTIONAL FIELDS
    gender = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True
    )
    email = serializers.EmailField(
        allow_blank=True, 
        required=False, 
        allow_null=True
    )
    phone = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True,
        max_length=20
    )
    marital_status = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True
    )
    occupation = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True,
        max_length=200
    )
    blood_type = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True
    )
    address = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True
    )
    baptism_status = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True
    )
    notes = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True
    )
    
    # Address fields
    residential_country = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True,
        max_length=100
    )
    residential_state = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True,
        max_length=100
    )
    residential_city = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True,
        max_length=100
    )
    origin_country = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True,
        max_length=100
    )
    origin_state = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True,
        max_length=100
    )
    origin_city = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True,
        max_length=100
    )
    
    # Emergency contact fields
    next_of_kin_name = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True,
        max_length=200
    )
    next_of_kin_phone = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True,
        max_length=20
    )
    next_of_kin_relationship = serializers.CharField(
        allow_blank=True, 
        required=False, 
        allow_null=True,
        max_length=100
    )
    
    # Date fields - can be null
    date_of_birth = serializers.DateField(
        required=False, 
        allow_null=True,
        format='%Y-%m-%d',
        input_formats=['%Y-%m-%d', 'iso-8601']
    )
    join_date = serializers.DateField(
        required=False, 
        allow_null=True,
        format='%Y-%m-%d',
        input_formats=['%Y-%m-%d', 'iso-8601']
    )
    baptism_date = serializers.DateField(
        required=False, 
        allow_null=True,
        format='%Y-%m-%d',
        input_formats=['%Y-%m-%d', 'iso-8601']
    )
    
    # Relationship fields
    campus = serializers.PrimaryKeyRelatedField(
        queryset=Campus.objects.all(), 
        required=False, 
        allow_null=True
    )
    family = serializers.PrimaryKeyRelatedField(
        queryset=Family.objects.all(), 
        required=False, 
        allow_null=True
    )
    
    # Required fields (no changes needed)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    status = serializers.CharField(max_length=20)
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all()
    )
    
    class Meta:
        model = Member
        fields = [
            'id', 'full_name', 'first_name', 'last_name', 'gender',
            'date_of_birth', 'age', 'phone', 'email', 'status',
            'marital_status', 'occupation', 'blood_type',
            'next_of_kin_name', 'next_of_kin_phone', 'next_of_kin_relationship',
            'address', 'residential_city', 'residential_state', 'residential_country',
            'origin_city', 'origin_state', 'origin_country',
            'baptism_status', 'baptism_date', 'join_date',
            'notes', 'photo', 'organization', 'organization_name',
            'campus', 'family', 'family_role', 'departments',
            'created_at', 'updated_at', 'user'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'full_name', 'age']
    
    def validate(self, data):
        """Custom validation - UPDATED TO BE MORE FLEXIBLE."""
        # Ensure required fields are present
        required_fields = ['first_name', 'last_name', 'organization']
        for field in required_fields:
            if field not in data or not data[field]:
                raise serializers.ValidationError({field: f"This field is required."})
        
        # Email validation (optional but must be valid if provided)
        if 'email' in data and data['email']:
            from django.core.validators import validate_email
            try:
                validate_email(data['email'])
            except:
                raise serializers.ValidationError({'email': 'Enter a valid email address.'})
        
        # Phone validation (optional but must be valid if provided)
        if 'phone' in data and data['phone']:
            import re
            cleaned = re.sub(r'\D', '', str(data['phone']))
            if len(cleaned) < 10:
                raise serializers.ValidationError({
                    'phone': 'The phone number entered is not valid (must be at least 10 digits).'
                })
        
        return data
    
    def validate_phone(self, value):
        """Validate phone number - UPDATED TO ACCEPT EMPTY/NULL."""
        if not value:  # Accept empty or null
            return value
            
        # Remove any non-numeric characters
        import re
        cleaned = re.sub(r'\D', '', str(value))
        
        # Basic validation - at least 10 digits
        if len(cleaned) < 10:
            raise serializers.ValidationError(
                "The phone number entered is not valid (must be at least 10 digits)."
            )
        
        return cleaned
    
    def validate_date_of_birth(self, value):
        """Validate date of birth - UPDATED TO ACCEPT EMPTY/NULL."""
        if not value:  # Accept empty or null
            return value
            
        from datetime import date
        if value > date.today():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        
        return value
    
    def create(self, validated_data):
        """Create member with departments."""
        departments_data = validated_data.pop('departments', [])
        member = Member.objects.create(**validated_data)
        
        if departments_data:
            member.departments.set(departments_data)
        
        return member
    
    def update(self, instance, validated_data):
        """Update member with departments."""
        departments_data = validated_data.pop('departments', None)
        
        # Update all fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        if departments_data is not None:
            instance.departments.set(departments_data)
        
        return instance
    



# inventory/serializers.py
from rest_framework import serializers
from .models import (
    InventoryCategory, InventoryVendor, InventoryItem,
    InventoryTransaction, InventoryCheckout, InventoryAudit,
    InventoryAuditItem
)
from church.models import Department, Member, Organization
from django.utils import timezone


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'slug']





class MemberSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Member
        fields = ['id', 'full_name', 'email', 'phone', 'status']
    
    def get_full_name(self, obj):
        return obj.full_name


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