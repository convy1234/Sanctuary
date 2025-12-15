from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from church.models import Invitation

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "uid",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "organization",
        ]

    def get_organization(self, obj):
        org = obj.organization
        if not org:
            return None
        return {"id": str(org.id), "name": org.name, "slug": org.slug}


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT login serializer that uses email as the username field."""

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        if not user.is_active:
            raise serializers.ValidationError("User account is inactive.")

        data["user"] = UserSerializer(user).data
        return data


class InvitationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = [
            "id",
            "email",
            "organization",
            "role",
            "expires_at",
            "note",
            "token",
            "as_owner",
        ]
        read_only_fields = ["id", "token"]

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        email = attrs.get("email")
        organization = attrs.get("organization")
        existing = Invitation.objects.filter(
            email=email,
            organization=organization,
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).first()
        if existing:
            raise serializers.ValidationError(
                {"email": "An active invitation has already been sent to this email."}
            )
        request = self.context.get("request")
        if attrs.get("as_owner") and request and not request.user.is_superuser:
            raise serializers.ValidationError(
                {"as_owner": "Only superusers can send owner invitations."}
            )
        if not attrs.get("role"):
            raise serializers.ValidationError({"role": "Role is required."})
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        invited_by = getattr(request, "user", None)
        return Invitation.objects.create(invited_by=invited_by, **validated_data)


class InvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        token = attrs.get("token")
        try:
            invitation = Invitation.objects.select_related("organization").get(
                token=token
            )
        except Invitation.DoesNotExist as exc:
            raise serializers.ValidationError({"token": "Invalid invitation token."}) from exc

        if invitation.is_used:
            raise serializers.ValidationError({"token": "This invitation was already used."})
        if invitation.is_expired:
            raise serializers.ValidationError({"token": "This invitation has expired."})

        attrs["invitation"] = invitation
        return attrs

    def create(self, validated_data):
        invitation: Invitation = validated_data["invitation"]
        password = validated_data["password"]
        first_name = validated_data.get("first_name", "")
        last_name = validated_data.get("last_name", "")

        user, _created = User.objects.get_or_create(
            email=invitation.email,
            defaults={
                "organization": invitation.organization,
                "is_active": True,
                "first_name": first_name,
                "last_name": last_name,
            },
        )

        # Keep organization in sync with the invitation.
        user.organization = invitation.organization
        if invitation.as_owner:
            user.is_owner = True
            user.is_staff = True
        user.first_name = first_name
        user.last_name = last_name
        user.is_active = True
        user.set_password(password)

        role_flags = {
            "admin": "is_admin",
            "pastor": "is_pastor",
            "hod": "is_hod",
            "worker": "is_worker",
            "volunteer": "is_volunteer",
        }
        selected_flag = role_flags.get(invitation.role)
        if selected_flag:
            setattr(user, selected_flag, True)

        user.save()

        invitation.mark_accepted()
        return user
        