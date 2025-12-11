# apps/accounts/serializers.py
from django.contrib.auth import get_user_model
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """
    Basic serializer for reading user info (safe fields only).
    """
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "is_platform_admin", "two_factor_enabled")
        read_only_fields = ("id", "is_platform_admin", "two_factor_enabled")


class UserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a user via invite-accept flow (server-side).
    Password write-only and validated.
    """
    password = serializers.CharField(write_only=True, min_length=8, help_text=_("Minimum 8 characters"))

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "password")
        read_only_fields = ("id",)

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user
