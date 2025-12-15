import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from church.models import Organization


class UserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom User model using email instead of username."""

    username = None
    uid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(_("Email Address"), unique=True, db_index=True)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Roles
    is_owner = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    is_pastor = models.BooleanField(default=False)
    is_hod = models.BooleanField(default=False)
    is_worker = models.BooleanField(default=False)
    is_volunteer = models.BooleanField(default=False)

    objects = UserManager()

    def levels(self):
        levels = []
        if self.is_owner:
            levels.append("org_owner")
        if self.is_admin:
            levels.append("admin")
        if self.is_pastor:
            levels.append("pastor")
        if self.is_hod:
            levels.append("hod")
        if self.is_worker:
            levels.append("worker")
        if self.is_volunteer:
            levels.append("volunteer")
        return levels

    def __str__(self):
        org = self.organization.slug if self.organization else "no-org"
        return f"{self.email} @ {org}"
