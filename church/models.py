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
    


class VoucherTemplate(models.Model):
    """Customizable template for voucher forms."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'Organization',
        on_delete=models.CASCADE,
        related_name='voucher_templates'
    )
    
    # Basic Information
    name = models.CharField(max_length=200, help_text="Template name (e.g., 'Funds Requisition Form')")
    is_default = models.BooleanField(default=False, help_text="Use as default template for organization")
    
    # Header Information
    church_name = models.CharField(max_length=200, default="Layers Of Truth")
    church_motto = models.CharField(max_length=500, blank=True, 
                                    default="Unveiling Christ, Communicating Eternal Life.")
    form_title = models.CharField(max_length=200, default="Funds Requisition Form")
    
    # Instructions
    description = models.TextField(
        blank=True,
        default="This form is used to request for funding already approved by the department."
    )
    warning_text = models.TextField(
        blank=True,
        default="YOU MUST BE THE LEADER OF A COMMUNITY / DEPARTMENT TO REQUEST FUNDING."
    )
    
    # Logo
    logo = models.ImageField(upload_to='voucher_logos/', null=True, blank=True)
    
    # Form Fields Configuration
    show_urgent_items = models.BooleanField(default=True)
    show_important_items = models.BooleanField(default=True)
    show_permissible_items = models.BooleanField(default=True)
    
    # Signature Section Labels
    signature_label = models.CharField(max_length=200, default="Department Leader Signature")
    date_label = models.CharField(max_length=200, default="Date")
    phone_label = models.CharField(max_length=200, default="Phone Number")
    
    # Footer Section
    footer_text = models.TextField(blank=True, help_text="Text to display at bottom of form")
    
    # Finance Office Section
    finance_section_title = models.CharField(max_length=200, default="CHURCH OFFICE USE ONLY")
    finance_office_name = models.CharField(max_length=200, default="Finance Office")
    
    # Default Commitments
    default_usage_commitment = models.TextField(
        default="I promise that the items (or services) purchased are to be used exclusively for the organization."
    )
    default_maintenance_commitment = models.TextField(
        default="I promise to keep all items in as good condition as possible at the approved location."
    )
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_voucher_templates'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['organization', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.organization.slug})"
    
    def save(self, *args, **kwargs):
        """Ensure only one default template per organization."""
        if self.is_default:
            # Set all other templates for this organization to not default
            VoucherTemplate.objects.filter(
                organization=self.organization, 
                is_default=True
            ).exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)





class Voucher(models.Model):
    """Simple voucher system for funds/equipment requests."""
    
    PRIORITY_CHOICES = [
        ('urgent', 'URGENT'),
        ('important', 'IMPORTANT'),
        ('permissible', 'PERMISSIBLE'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('transfer', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('cash_transfer', 'Cash or Transfer'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'Organization',
        on_delete=models.CASCADE,
        related_name='vouchers'
    )
    
    # Voucher Information
    voucher_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text="Auto-generated voucher number (e.g., VCH-001)"
    )
    title = models.CharField(
        max_length=255,
        default="Funds Requisition Form",
        help_text="Title of the voucher request"
    )

    template = models.ForeignKey(
        VoucherTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vouchers',
        help_text="Template used for this voucher"
    )
    
    # Requester Information (From Page 1)
    date_prepared = models.DateField(default=timezone.now, help_text="Today's Date")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='submitted_vouchers',
        help_text="User submitting the request"
    )
    requester_name_department = models.CharField(
        max_length=255,
        help_text="Your Name & Department"
    )
    
    # Request Details
    purpose = models.TextField(
        help_text="Reason(s) for purchasing the items / services"
    )
    
    # Items List (From the URGENT/IMPORTANT/PERMISSIBLE sections)
    urgent_items = models.TextField(
        blank=True,
        help_text="URGENT items with prices (one per line)"
    )
    important_items = models.TextField(
        blank=True,
        help_text="IMPORTANT items with prices (one per line)"
    )
    permissible_items = models.TextField(
        blank=True,
        help_text="PERMISSIBLE items with prices (one per line)"
    )
    
    # Financial Information
    amount_in_words = models.CharField(
        max_length=500,
        help_text="Total amount requested in words"
    )
    amount_in_figures = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True,      # ADD THIS
        blank=True,  
        help_text="Total amount requested in figures"
    )
    currency = models.CharField(
        max_length=10,
        default='NGN',
        help_text="Currency (e.g., NGN, USD)",
        blank=True  
    )
    
    # Payment Information
    payable_to = models.CharField(
        max_length=255,
        help_text="Funds are payable to (Name/Bank Account)"
    )
    payee_phone = models.CharField(
        max_length=20,
        help_text="Phone Number of Payee"
    )
    payment_method = models.CharField(
        max_length=50,
        choices=PAYMENT_METHOD_CHOICES,
        default='transfer',
        help_text="Preferred mode of payment",
        blank=True
    )
    
    # Timeline
    needed_by = models.DateField(
        help_text="When is the requested fund needed",
        null=True,
        blank=True
    )
    
    # Promises/Commitments
    usage_commitment = models.TextField(
        default="I promise that the items (or services) purchased are to be used exclusively for the organization.",
        help_text="Commitment to proper usage"
    )
    maintenance_commitment = models.TextField(
        default="I promise to keep all items in as good condition as possible at the approved location.",
        help_text="Commitment to maintenance"
    )
    
    # Requester Signature Section
    requester_signature = models.CharField(
        max_length=255,
        blank=True,
        help_text="Department Leader Signature (name)"
    )
    requester_signed_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date signed by requester"
    )
    requester_signature_image = models.ImageField(
        upload_to='voucher_signatures/%Y/%m/%d/',
        null=True,
        blank=True,
        help_text="Signature image (drawn/uploaded)"
    )
    requester_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Phone Number for verification"
    )
    
    # CHURCH OFFICE USE ONLY (Page 2)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    
    funds_approved = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Funds Approved"
    )
    funds_denied = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Funds Denied"
    )
    approved_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Final approved amount"
    )
    
    # Approval Information
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_vouchers',
        help_text="Finance/Admin who approved"
    )
    approved_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date approved"
    )
    finance_remarks = models.TextField(
        blank=True,
        help_text="Remarks from Finance Office"
    )
    finance_signature = models.CharField(
        max_length=255,
        blank=True,
        help_text="Signature from Finance Office"
    )
    
    # Payment Execution
    paid_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Amount actually paid"
    )
    paid_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date payment was made"
    )
    payment_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Payment reference/transaction ID"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)
    
    class Meta:
        ordering = ['-date_prepared', '-created_at']
        indexes = [
            models.Index(fields=['voucher_number']),
            models.Index(fields=['status']),
            models.Index(fields=['requested_by', 'date_prepared']),
        ]
    
    def __str__(self):
        return f"{self.voucher_number}: {self.purpose[:50]}..."
    
    def save(self, *args, **kwargs):
        """Auto-generate voucher number on creation."""
        if not self.voucher_number:
            # Get organization prefix
            org_prefix = self.organization.slug.upper()[:3] if self.organization else 'VCH'
            
            # Get the next sequence number for this organization
            last_voucher = Voucher.objects.filter(
                organization=self.organization,
                voucher_number__startswith=f"{org_prefix}-"
            ).order_by('voucher_number').last()
            
            if last_voucher and last_voucher.voucher_number:
                try:
                    last_num = int(last_voucher.voucher_number.split('-')[1])
                    next_num = last_num + 1
                except (IndexError, ValueError):
                    next_num = 1
            else:
                next_num = 1
            
            self.voucher_number = f"{org_prefix}-{next_num:04d}"
        
        super().save(*args, **kwargs)
    
    @property
    def total_items_count(self):
        """Count total items across all priorities."""
        count = 0
        for field in [self.urgent_items, self.important_items, self.permissible_items]:
            if field:
                # Count lines that contain actual items (not empty lines)
                lines = [line.strip() for line in field.split('\n') if line.strip()]
                count += len(lines)
        return count
    
    @property
    def is_approved(self):
        return self.status == 'approved'
    
    @property
    def is_paid(self):
        return self.status == 'paid'
    
    @property
    def is_pending(self):
        return self.status in ['draft', 'submitted']
    
    @property
    def days_open(self):
        """Days since voucher was created."""
        return (timezone.now().date() - self.date_prepared).days
    
    @property
    def is_overdue(self):
        """Check if needed_by date has passed without payment."""
        if self.needed_by and self.status not in ['paid', 'completed', 'cancelled']:
            return timezone.now().date() > self.needed_by
        return False
    
    def get_all_items(self):
        """Return all items grouped by priority."""
        items = []
        
        if self.urgent_items:
            for line in self.urgent_items.split('\n'):
                if line.strip():
                    items.append({
                        'priority': 'urgent',
                        'description': line.strip(),
                        'priority_display': 'URGENT'
                    })
        
        if self.important_items:
            for line in self.important_items.split('\n'):
                if line.strip():
                    items.append({
                        'priority': 'important',
                        'description': line.strip(),
                        'priority_display': 'IMPORTANT'
                    })
        
        if self.permissible_items:
            for line in self.permissible_items.split('\n'):
                if line.strip():
                    items.append({
                        'priority': 'permissible',
                        'description': line.strip(),
                        'priority_display': 'PERMISSIBLE'
                    })
        
        return items
    
    def submit_for_approval(self):
        """Submit the voucher for approval."""
        if self.status == 'draft':
            self.status = 'submitted'
            self.save()
            return True
        return False
    
    def approve(self, user, approved_amount=None, remarks=''):
        """Approve the voucher."""
        if self.status in ['submitted', 'draft']:
            self.status = 'approved'
            self.approved_by = user
            self.approved_date = timezone.now().date()
            self.finance_remarks = remarks
            
            if approved_amount is not None:
                from decimal import Decimal
                if isinstance(approved_amount, str):
                    try:
                        approved_amount = Decimal(approved_amount)
                    except:
                        approved_amount = Decimal(0)
                elif isinstance(approved_amount, (int, float)):
                    approved_amount = Decimal(str(approved_amount))

                self.approved_amount = approved_amount
                if approved_amount < self.amount_in_figures:
                    self.funds_denied = self.amount_in_figures - approved_amount
                    self.funds_approved = approved_amount
                else:
                    self.funds_approved = self.amount_in_figures
                    self.funds_denied = Decimal(0)
            else:
                self.funds_approved = self.amount_in_figures
                self.funds_denied = Decimal(0)

            self.save()
            return True
        return False
    
    def reject(self, user, reason=''):
        """Reject the voucher."""
        if self.status in ['submitted', 'draft']:
            self.status = 'rejected'
            self.funds_denied = self.amount_in_figures
            self.finance_remarks = reason
            self.save()
            return True
        return False
    
    def mark_as_paid(self, amount=None, reference=''):
        """Mark voucher as paid."""
        if self.status == 'approved':
            self.status = 'paid'
            self.paid_date = timezone.now().date()
            
            if amount is not None:
                self.paid_amount = amount
            else:
                self.paid_amount = self.approved_amount or self.amount_in_figures
            
            self.payment_reference = reference
            self.save()
            return True
        return False


class VoucherAttachment(models.Model):
    """Supporting documents for vouchers."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voucher = models.ForeignKey(
        Voucher,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    
    file = models.FileField(
        upload_to='vouchers/attachments/%Y/%m/%d/',
        help_text="Supporting document (quote, receipt, etc.)"
    )
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField()
    description = models.CharField(max_length=500, blank=True)
    
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.file_name} ({self.voucher.voucher_number})"


class VoucherComment(models.Model):
    """Internal comments/notes on vouchers."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voucher = models.ForeignKey(
        Voucher,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='voucher_comments'
    )
    comment = models.TextField()
    is_internal = models.BooleanField(
        default=True,
        help_text="Internal notes not visible to requester"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"Comment by {self.author} on {self.voucher.voucher_number}"





# inventory/models.py
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


class InventoryCategory(models.Model):
    """Category for inventory items"""
    CATEGORY_TYPES = [
        ('worship', 'Worship Supplies'),
        ('event', 'Event Equipment'),
        ('office', 'Office Supplies'),
        ('maintenance', 'Maintenance'),
        ('kitchen', 'Kitchen Supplies'),
        ('technology', 'Technology'),
        ('furniture', 'Furniture'),
        ('seasonal', 'Seasonal Decorations'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='inventory_categories')
    
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES, default='other')
    color_code = models.CharField(max_length=7, default='#6c757d', 
                                 help_text="Hex color for UI display")
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['category_type', 'name']
        verbose_name_plural = "Inventory Categories"
        unique_together = ['organization', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.organization.slug})"


class InventoryVendor(models.Model):
    """Vendors for purchasing inventory items"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='inventory_vendors')
    
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['organization', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.organization.slug})"


class InventoryItem(models.Model):
    """Main inventory item model"""
    ITEM_TYPES = [
        ('consumable', 'Consumable (Communion, candles, etc.)'),
        ('equipment', 'Equipment (Sound, projectors, etc.)'),
        ('asset', 'Capital Asset (Expensive, long-term)'),
        ('furniture', 'Furniture'),
        ('supply', 'General Supply'),
        ('resource', 'Resource (Books, media)'),
    ]
    
    CONDITION_CHOICES = [
        ('new', 'New'),
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('repair', 'Needs Repair'),
        ('retired', 'Retired/Disposed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='inventory_items')
    
    # Core Identification
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Classification
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, 
                                   null=True, blank=True, related_name='inventory_items')
    category = models.ForeignKey(InventoryCategory, on_delete=models.SET_NULL, 
                                null=True, blank=True, related_name='items')
    item_type = models.CharField(max_length=20, choices=ITEM_TYPES, default='supply')
    
    # Identification Codes
    sku = models.CharField(max_length=100, blank=True, db_index=True,
                          help_text="Stock Keeping Unit")
    asset_tag = models.CharField(max_length=100, blank=True, null=True, unique=True,
                                help_text="For tracking capital assets")
    barcode = models.CharField(max_length=50, blank=True, null=True, unique=True,
                              help_text="Barcode/QR code identifier")
    
    # Stock Information
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reorder_level = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reorder_quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    alert_on_low = models.BooleanField(default=True)
    
    # Physical Attributes
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='good')
    location = models.CharField(max_length=200, blank=True,
                               help_text="Specific location (Room, Shelf, Bin)")
    storage_instructions = models.TextField(blank=True,
                                           help_text="Special storage requirements")
    image = models.ImageField(upload_to='inventory_items/%Y/%m/', blank=True, null=True)
    
    # Financial Information
    vendor = models.ForeignKey(InventoryVendor, on_delete=models.SET_NULL, 
                              null=True, blank=True, related_name='items')
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, 
                                        null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    replacement_cost = models.DecimalField(max_digits=10, decimal_places=2, 
                                          null=True, blank=True)
    
    # Tracking & Metadata
    is_active = models.BooleanField(default=True)
    last_audited = models.DateField(null=True, blank=True)
    last_checked_out = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    # System Fields
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, 
                                  on_delete=models.SET_NULL, 
                                  null=True, related_name='created_inventory_items')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['barcode']),
            models.Index(fields=['department']),
            models.Index(fields=['item_type']),
            models.Index(fields=['condition']),
            models.Index(fields=['is_active']),
            models.Index(fields=['organization', 'quantity']),
        ]
    
    def __str__(self):
        dept_code = self.department.code if self.department else "N/A"
        return f"{self.name} ({dept_code})"
    
    def save(self, *args, **kwargs):
        # Auto-generate barcode if not provided
        if not self.barcode and not self.pk:
            super().save(*args, **kwargs)  # Save to get ID first
            self.barcode = f"INV-{self.organization.slug.upper()}-{self.pk:06d}"
        
        # Auto-generate SKU if not provided
        if not self.sku:
            category_code = self.category.name[:3].upper() if self.category else "GEN"
            dept_code = self.department.code[:3].upper() if self.department else "GEN"
            self.sku = f"{dept_code}-{category_code}-{self.pk:06d}"
        
        super().save(*args, **kwargs)
    
    @property
    def total_value(self):
        """Total value of current stock"""
        if self.purchase_price and self.quantity:
            return Decimal(self.purchase_price) * Decimal(self.quantity)
        return Decimal('0.00')
    
    @property
    def is_low_stock(self):
        """Check if item is low on stock"""
        return self.quantity <= self.reorder_level if self.alert_on_low else False
    
    @property
    def status(self):
        """Get item status"""
        if not self.is_active:
            return 'inactive'
        if self.quantity <= 0:
            return 'out_of_stock'
        if self.is_low_stock:
            return 'low_stock'
        return 'in_stock'


class InventoryTransaction(models.Model):
    """Track all inventory movements"""
    TRANSACTION_TYPES = [
        ('add', 'Stock Added'),
        ('remove', 'Stock Removed'),
        ('transfer', 'Department Transfer'),
        ('checkout', 'Checked Out'),
        ('return', 'Returned'),
        ('adjust', 'Audit Adjustment'),
        ('write_off', 'Write Off'),
        ('damage', 'Damaged/Lost'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='inventory_transactions')
    
    # Transaction Details
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, 
                            related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField()
    
    # Department Information
    from_department = models.ForeignKey('Department', related_name='transactions_from', 
                                       null=True, blank=True, on_delete=models.SET_NULL)
    to_department = models.ForeignKey('Department', related_name='transactions_to', 
                                     null=True, blank=True, on_delete=models.SET_NULL)
    
    # User Information
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, 
                                    null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='performed_inventory_transactions')
    
    # Reference to voucher if this is a purchase
    voucher = models.ForeignKey('Voucher', on_delete=models.SET_NULL, 
                               null=True, blank=True, related_name='inventory_transactions',
                               help_text="Related voucher for purchase")
    
    # Metadata
    notes = models.TextField(blank=True)
    reference_number = models.CharField(max_length=50, blank=True,
                                       help_text="PO Number, Receipt #, etc.")
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # System Fields
    created_at = models.DateTimeField(auto_now_add=True)
    requires_approval = models.BooleanField(default=False)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, 
                                   null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='approved_inventory_transactions')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['item', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.item.name} ({self.quantity})"
    
    def save(self, *args, **kwargs):
        """Update item quantity when transaction is created"""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Update item quantity
        if is_new and self.approved_by:  # Only update if approved
            self.update_item_stock()
    
    def update_item_stock(self):
        """Update the item's stock based on transaction"""
        if self.transaction_type in ['add', 'return']:
            self.item.quantity += self.quantity
        elif self.transaction_type in ['remove', 'checkout', 'write_off', 'damage']:
            self.item.quantity = max(0, self.item.quantity - self.quantity)
        elif self.transaction_type == 'adjust':
            # For adjustments, we're setting the quantity directly
            pass
        
        self.item.save(update_fields=['quantity', 'updated_at'])


class InventoryCheckout(models.Model):
    """Track items checked out by members/staff"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('overdue', 'Overdue'),
        ('returned', 'Returned'),
        ('lost', 'Lost'),
        ('damaged', 'Damaged'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='inventory_checkouts')
    
    # Checkout Details
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, 
                            related_name='checkouts')
    member = models.ForeignKey('Member', on_delete=models.PROTECT,
                             related_name='inventory_checkouts',
                             help_text="Church member checking out item")
    department = models.ForeignKey('Department', on_delete=models.PROTECT,
                                  related_name='checkouts')
    
    # Checkout Information
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    purpose = models.CharField(max_length=200, blank=True,
                              help_text="What will this be used for?")
    event_name = models.CharField(max_length=100, blank=True,
                                 help_text="Related church event")
    
    # Dates
    checkout_date = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    expected_return_date = models.DateField(null=True, blank=True)
    
    # Return Information
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    returned_quantity = models.IntegerField(default=0)
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_condition = models.CharField(max_length=20, choices=InventoryItem.CONDITION_CHOICES, 
                                         blank=True)
    return_notes = models.TextField(blank=True)
    
    # Approval
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, 
                                   null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='approved_inventory_checkouts')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # System Fields
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, 
                                  on_delete=models.SET_NULL, null=True,
                                  related_name='created_inventory_checkouts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-checkout_date']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
            models.Index(fields=['member', 'status']),
        ]
    
    def __str__(self):
        return f"{self.item.name} → {self.member.full_name}"
    
    @property
    def is_overdue(self):
        """Check if checkout is overdue"""
        if self.due_date and self.status == 'active':
            return timezone.now().date() > self.due_date
        return False
    
    @property
    def days_overdue(self):
        """Number of days overdue"""
        if self.is_overdue:
            return (timezone.now().date() - self.due_date).days
        return 0
    
    def save(self, *args, **kwargs):
        """Auto-update status if overdue"""
        if self.due_date and self.status == 'active':
            if timezone.now().date() > self.due_date:
                self.status = 'overdue'
        
        # Update item's last checked out date
        if self.status == 'active':
            self.item.last_checked_out = timezone.now().date()
            self.item.save(update_fields=['last_checked_out'])
        
        super().save(*args, **kwargs)


class InventoryAudit(models.Model):
    """Inventory audit/stock count"""
    AUDIT_TYPES = [
        ('full', 'Full Inventory Audit'),
        ('spot', 'Spot Check'),
        ('cycle', 'Cycle Count'),
        ('department', 'Department Audit'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='inventory_audits')
    
    # Audit Details
    name = models.CharField(max_length=200)
    audit_type = models.CharField(max_length=20, choices=AUDIT_TYPES)
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, 
                                  null=True, blank=True, related_name='inventory_audits')
    
    # Participants
    auditor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                               null=True, related_name='conducted_inventory_audits')
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, 
                                         related_name='participated_inventory_audits',
                                         blank=True)
    
    # Dates
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    
    # Results
    total_items = models.IntegerField(default=0)
    items_checked = models.IntegerField(default=0)
    discrepancies_found = models.IntegerField(default=0)
    accuracy_percentage = models.DecimalField(max_digits=5, decimal_places=2, 
                                             default=100.00)
    
    # Metadata
    notes = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    
    # System Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.name} - {self.start_date.strftime('%Y-%m-%d')}"


class InventoryAuditItem(models.Model):
    """Individual items in an audit"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit = models.ForeignKey(InventoryAudit, on_delete=models.CASCADE, related_name='audit_items')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    
    # Counts
    expected_quantity = models.IntegerField()
    counted_quantity = models.IntegerField()
    difference = models.IntegerField(default=0)
    
    # Notes
    notes = models.TextField(blank=True)
    adjusted = models.BooleanField(default=False)
    
    # System
    counted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                  null=True, blank=True)
    counted_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        unique_together = ['audit', 'item']
    
    def __str__(self):
        return f"{self.item.name} - Expected: {self.expected_quantity}, Counted: {self.counted_quantity}"
    
    def save(self, *args, **kwargs):
        """Calculate difference"""
        self.difference = self.counted_quantity - self.expected_quantity
        super().save(*args, **kwargs)


class InventoryNotification(models.Model):
    """Notifications for inventory events"""
    NOTIFICATION_TYPES = [
        ('low_stock', 'Low Stock Alert'),
        ('overdue', 'Overdue Checkout'),
        ('audit', 'Audit Required'),
        ('maintenance', 'Maintenance Due'),
        ('system', 'System Notification'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='inventory_notifications')
    
    # Notification Details
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                            related_name='inventory_notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    # Related Items
    related_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE,
                                    null=True, blank=True)
    related_checkout = models.ForeignKey(InventoryCheckout, on_delete=models.CASCADE,
                                        null=True, blank=True)
    
    # Status
    is_read = models.BooleanField(default=False)
    is_important = models.BooleanField(default=False)
    
    # System
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.notification_type}: {self.title}"
