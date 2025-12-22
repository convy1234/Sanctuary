import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField  # Need to install: pip install django-phonenumber-field

# Domain models now live in dedicated apps but keep the `church` app label for migrations/tables.
from member.models import Member, Family, Department, Campus
from accounting.models import VoucherTemplate, Voucher, VoucherAttachment, VoucherComment



def generate_invite_token() -> str:
    """Generate a short, URL-safe invite token."""
    return secrets.token_urlsafe(32)


def default_invite_expiry():
    """Default invite expiry (7 days from now)."""
    return timezone.now() + timedelta(days=7)


class Organization(models.Model):
    """A minimal organization that owns user accounts."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organizations_created",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.slug


class SubscriptionPlan(models.Model):
    """Subscription catalog entry."""

    BILLING_CHOICES = (
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)

    billing_period = models.CharField(max_length=20, choices=BILLING_CHOICES, default="monthly")
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_per_user = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    included_users = models.PositiveIntegerField(default=0)
    capacity_min = models.PositiveIntegerField(default=0)
    capacity_max = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.billing_period})"

    def clean(self):
        super().clean()
        if self.capacity_max is not None and self.capacity_max < self.capacity_min:
            raise ValidationError({"capacity_max": "Max capacity must be greater than or equal to the minimum."})
        if self.base_price < 0 or self.price_per_user < 0:
            raise ValidationError("Prices cannot be negative.")


class OrganizationSubscription(models.Model):
    """Subscription assigned to an organization with seat/price overrides."""

    STATUS_CHOICES = (
        ("trialing", "Trialing"),
        ("active", "Active"),
        ("past_due", "Past due"),
        ("canceled", "Canceled"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        Organization, related_name="subscription", on_delete=models.CASCADE
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        related_name="subscriptions",
        on_delete=models.PROTECT,
    )
    price_override = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    started_at = models.DateTimeField(auto_now_add=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def current_price(self, user_count: int | None = None) -> float:
        """Calculate current billable amount using provided user count."""
        plan = self.plan
        base = float(self.price_override) if self.price_override is not None else float(plan.base_price)
        per_user = float(plan.price_per_user)
        included = plan.included_users
        if user_count is None and self.organization_id:
            user_count = self.organization.user_set.count()
        billable_users = user_count if user_count is not None else included
        extra_users = max(0, billable_users - included)
        return base + extra_users * per_user

    @property
    def is_active(self) -> bool:
        return self.status in {"trialing", "active"} and (self.ends_at is None or self.ends_at > timezone.now())

    def __str__(self) -> str:
        return f"{self.organization.slug} -> {self.plan.slug}"


class Invitation(models.Model):
    """Invite-only onboarding gatekeeper."""

    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("pastor", "Pastor"),
        ("hod", "Head of Department"),
        ("worker", "Worker"),
        ("volunteer", "Volunteer"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    organization = models.ForeignKey(
        Organization,
        related_name="invitations",
        on_delete=models.CASCADE,
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="worker")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_invitations",
    )
    as_owner = models.BooleanField(default=False)
    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_invite_token,
        editable=False,
    )
    expires_at = models.DateTimeField(default=default_invite_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("email", "organization", "token")

    @property
    def is_used(self) -> bool:
        return self.accepted_at is not None

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_active(self) -> bool:
        return not self.is_used and not self.is_expired

    def mark_accepted(self) -> None:
        self.accepted_at = timezone.now()
        self.save(update_fields=["accepted_at", "updated_at"])

    def clean(self):
        super().clean()
        if not self.pk and self.expires_at and self.expires_at <= timezone.now():
            raise ValidationError({"expires_at": "Expiration must be set to a future time."})

    def __str__(self) -> str:
        return f"{self.email} -> {self.organization.slug}"
