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
