# sanctuary/church/serializers.py
from django.utils import timezone
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import Invite, Organization, Membership, OrganizationApplication

User = get_user_model()


# Add this OrganizationSerializer class
class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ('id', 'name', 'slug', 'owner', 'created_at')
        read_only_fields = ('id', 'created_at')


class InviteSerializer(serializers.ModelSerializer):
    inviter = serializers.StringRelatedField(read_only=True)
    organization = serializers.SlugRelatedField(slug_field="slug", queryset=Organization.objects.all())

    class Meta:
        model = Invite
        fields = ("id", "email", "inviter", "organization", "role", "token", "expires_at", "accepted_at", "created_at")
        read_only_fields = ("id", "token", "expires_at", "accepted_at", "created_at", "inviter")


class InviteCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    organization = serializers.SlugRelatedField(slug_field="slug", queryset=Organization.objects.all())
    role = serializers.ChoiceField(choices=[c[0] for c in Invite.ROLE_CHOICES])

    def create(self, validated_data):
        inviter = self.context["request"].user
        email = validated_data["email"]
        organization = validated_data["organization"]
        role = validated_data["role"]
        invite = Invite.create_invite(email=email, inviter=inviter, organization=organization, role=role)
        return invite


class AcceptInviteSerializer(serializers.Serializer):
    token = serializers.CharField()
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_token(self, value):
        try:
            invite = Invite.objects.get(token=value)
        except Invite.DoesNotExist:
            raise serializers.ValidationError("Invalid invite token.")
        if not invite.is_valid():
            raise serializers.ValidationError("Invite token expired or already used.")
        return value

    def save(self, **kwargs):
        token = self.validated_data["token"]
        first_name = self.validated_data.get("first_name", "")
        last_name = self.validated_data.get("last_name", "")
        password = self.validated_data["password"]

        invite = Invite.objects.get(token=token)
        
        # Create or get user
        user_qs = User.objects.filter(email__iexact=invite.email)
        if user_qs.exists():
            user = user_qs.first()
            # update name if missing
            if not user.first_name and first_name:
                user.first_name = first_name
            if not user.last_name and last_name:
                user.last_name = last_name
            if password:
                user.set_password(password)
            user.save()
        else:
            user = User.objects.create(
                email=invite.email,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
            )
            user.set_password(password)
            user.save()

        # Create membership
        membership, created = Membership.objects.get_or_create(
            user=user,
            organization=invite.organization,
            defaults={'role': invite.role}
        )
        
        # Update invite
        invite.accepted_at = timezone.now()
        invite.used_by = user
        invite.save()

        return {"user": user, "invite": invite, "membership": membership}


class MembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    organization_slug = serializers.SlugRelatedField(source="organization", slug_field="slug", read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "user", "user_email", "organization", "organization_slug", "role", "is_primary_admin", "scopes", "created_at")
        read_only_fields = ("id", "user_email", "organization_slug", "created_at")


class OrganizationApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationApplication
        fields = '__all__'
        read_only_fields = ('status', 'applied_at', 'reviewed_at')


class OrganizationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ('id', 'name', 'slug')
    
    def create(self, validated_data):
        # Generate slug from name if not provided
        if 'slug' not in validated_data:
            from django.utils.text import slugify
            validated_data['slug'] = slugify(validated_data['name'])
        
        # Get the user from context (should be the platform admin approving)
        request = self.context.get('request')
        user = request.user if request else None
        
        organization = Organization.objects.create(**validated_data)
        
        # Create membership for the user if exists
        if user:
            Membership.objects.create(
                user=user,
                organization=organization,
                role='org_owner',
                is_primary_admin=True
            )
        
        return organization