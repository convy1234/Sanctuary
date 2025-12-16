import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


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
        billable_users = user_count if user_count is not None else included
        extra_users = max(0, billable_users - included)
        return base + extra_users * per_user

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

    def mark_accepted(self) -> None:
        self.accepted_at = timezone.now()
        self.save(update_fields=["accepted_at", "updated_at"])

    def __str__(self) -> str:
        return f"{self.email} -> {self.organization.slug}"
    





    # In church/models.py or members/models.py
import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from phonenumber_field.modelfields import PhoneNumberField  # Need to install: pip install django-phonenumber-field

class Member(models.Model):
    """Comprehensive church member profile."""
    
    # Personal Information
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='member_profile',
        null=True,
        blank=True
    )
    organization = models.ForeignKey(
        'Organization',
        on_delete=models.CASCADE,
        related_name='members'
    )
    
    # Basic Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('prefer_not_to_say', 'Prefer not to say'),
    ]
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True)
    
    date_of_birth = models.DateField(null=True, blank=True)
    photo = models.ImageField(upload_to='members/photos/', null=True, blank=True)
    
    # Contact Information
    phone = PhoneNumberField(blank=True)  # Or use CharField if you don't want to install phonenumber_field
    email = models.EmailField(blank=True)
    
    # Church Information
    STATUS_CHOICES = [
        ('new', 'New'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('visitor', 'Visitor'),
        ('transferred', 'Transferred'),
        ('deceased', 'Deceased'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    
    campus = models.ForeignKey(
        'Campus',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='members'
    )
    
    join_date = models.DateField(null=True, blank=True)
    
    # Family Information
    family = models.ForeignKey(
        'Family',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='members'
    )
    
    FAMILY_ROLE_CHOICES = [
        ('head', 'Family Head'),
        ('spouse', 'Spouse'),
        ('child', 'Child'),
        ('parent', 'Parent'),
        ('sibling', 'Sibling'),
        ('other', 'Other'),
    ]
    family_role = models.CharField(max_length=20, choices=FAMILY_ROLE_CHOICES, blank=True)
    
    spouse = models.OneToOneField(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='married_to'
    )
    
    # Address Information
    address = models.TextField(blank=True)
    
    MARITAL_STATUS_CHOICES = [
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
        ('separated', 'Separated'),
    ]
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, blank=True)
    
    # Professional Information
    occupation = models.CharField(max_length=200, blank=True)
    
    # Medical Information
    BLOOD_TYPE_CHOICES = [
        ('a_positive', 'A+'),
        ('a_negative', 'A-'),
        ('b_positive', 'B+'),
        ('b_negative', 'B-'),
        ('ab_positive', 'AB+'),
        ('ab_negative', 'AB-'),
        ('o_positive', 'O+'),
        ('o_negative', 'O-'),
        ('unknown', 'Unknown'),
    ]
    blood_type = models.CharField(max_length=20, choices=BLOOD_TYPE_CHOICES, blank=True)
    
    # Emergency Contact
    next_of_kin_name = models.CharField(max_length=200, blank=True, null=True)
    next_of_kin_phone = PhoneNumberField(blank=True, null=True)
    next_of_kin_relationship = models.CharField(max_length=100, blank=True, null=True)

    # Location Details
    residential_country = models.CharField(max_length=100, blank=True, null=True)
    residential_state = models.CharField(max_length=100, blank=True, null=True)
    residential_city = models.CharField(max_length=100, blank=True, null=True)

    origin_country = models.CharField(max_length=100, blank=True, null=True)
    origin_state = models.CharField(max_length=100, blank=True, null=True)
    origin_city = models.CharField(max_length=100, blank=True, null=True)
    
    # Additional Information
    notes = models.TextField(blank=True)
    
    # Service/Department Information
    departments = models.ManyToManyField(
        'Department',
        related_name='members',
        blank=True
    )
    
    # Spiritual Information
    BAPTISM_STATUS_CHOICES = [
        ('not_baptized', 'Not Baptized'),
        ('water_baptized', 'Water Baptized'),
        ('spirit_baptized', 'Spirit Baptized'),
        ('both', 'Both Water and Spirit Baptized'),
    ]
    baptism_status = models.CharField(max_length=30, choices=BAPTISM_STATUS_CHOICES, blank=True)
    
    baptism_date = models.DateField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_members'
    )
    
    class Meta:
        ordering = ['last_name', 'first_name']
        unique_together = ['organization', 'email']  # Email unique per organization
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.organization.slug})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        if self.date_of_birth:
            from datetime import date
            today = date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None


class Campus(models.Model):
    """Church campus/branch location."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='campuses')
    name = models.CharField(max_length=100)
    address = models.TextField(blank=True)
    phone = PhoneNumberField(blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = "Campuses"
        unique_together = ['organization', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.organization.slug})"


class Family(models.Model):
    """Family unit for grouping members."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='families')
    family_name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    phone = PhoneNumberField(blank=True)
    email = models.EmailField(blank=True)
    family_head = models.ForeignKey(
        'Member',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_families'
    )
    
    class Meta:
        verbose_name_plural = "Families"
        unique_together = ['organization', 'family_name']
    
    def __str__(self):
        return f"{self.family_name} Family ({self.organization.slug})"


class Department(models.Model):
    """Church departments/groups (Choir, Ushers, Children's Church, etc.)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    leader = models.ForeignKey(
        'Member',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='led_departments'
    )
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['organization', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.organization.slug})"