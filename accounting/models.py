import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class VoucherTemplate(models.Model):
    """Customizable template for voucher forms."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "church.Organization", on_delete=models.CASCADE, related_name="voucher_templates"
    )

    name = models.CharField(max_length=200, help_text="Template name (e.g., 'Funds Requisition Form')")
    is_default = models.BooleanField(default=False, help_text="Use as default template for organization")
    church_name = models.CharField(max_length=200, default="Layers Of Truth")
    church_motto = models.CharField(
        max_length=500, blank=True, default="Unveiling Christ, Communicating Eternal Life."
    )
    form_title = models.CharField(max_length=200, default="Funds Requisition Form")
    description = models.TextField(
        blank=True, default="This form is used to request for funding already approved by the department."
    )
    warning_text = models.TextField(
        blank=True, default="YOU MUST BE THE LEADER OF A COMMUNITY / DEPARTMENT TO REQUEST FUNDING."
    )
    logo = models.ImageField(upload_to="voucher_logos/", null=True, blank=True)
    show_urgent_items = models.BooleanField(default=True)
    show_important_items = models.BooleanField(default=True)
    show_permissible_items = models.BooleanField(default=True)
    signature_label = models.CharField(max_length=200, default="Department Leader Signature")
    date_label = models.CharField(max_length=200, default="Date")
    phone_label = models.CharField(max_length=200, default="Phone Number")
    footer_text = models.TextField(blank=True, help_text="Text to display at bottom of form")
    finance_section_title = models.CharField(max_length=200, default="CHURCH OFFICE USE ONLY")
    finance_office_name = models.CharField(max_length=200, default="Finance Office")
    default_usage_commitment = models.TextField(
        default="I promise that the items (or services) purchased are to be used exclusively for the organization."
    )
    default_maintenance_commitment = models.TextField(
        default="I promise to keep all items in as good condition as possible at the approved location."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_voucher_templates"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "church"
        ordering = ["name"]
        unique_together = ["organization", "name"]

    def __str__(self):
        return f"{self.name} ({self.organization.slug})"

    def save(self, *args, **kwargs):
        if self.is_default:
            VoucherTemplate.objects.filter(organization=self.organization, is_default=True).exclude(
                id=self.id
            ).update(is_default=False)
        super().save(*args, **kwargs)
class Voucher(models.Model):
    """Simple voucher system for funds/equipment requests."""

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Cash"),
        ("transfer", "Bank Transfer"),
        ("cheque", "Cheque"),
        ("cash_transfer", "Cash or Transfer"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("paid", "Paid"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("church.Organization", on_delete=models.CASCADE, related_name="vouchers")
    voucher_number = models.CharField(max_length=20, unique=True, editable=False, help_text="Auto-generated number")
    title = models.CharField(max_length=255, default="Funds Requisition Form", help_text="Title of the request")
    template = models.ForeignKey(
        VoucherTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="vouchers"
    )

    date_prepared = models.DateField(default=timezone.now, help_text="Today's Date")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submitted_vouchers"
    )
    requester_name_department = models.CharField(max_length=255, help_text="Your Name & Department")
    purpose = models.TextField(help_text="Reason(s) for purchasing the items / services")
    urgent_items = models.TextField(blank=True, help_text="URGENT items with prices (one per line)")
    important_items = models.TextField(blank=True, help_text="IMPORTANT items with prices (one per line)")
    permissible_items = models.TextField(blank=True, help_text="PERMISSIBLE items with prices (one per line)")
    amount_in_words = models.CharField(max_length=500, help_text="Total amount requested in words")
    amount_in_figures = models.DecimalField(
        max_digits=15, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True
    )
    currency = models.CharField(max_length=10, default="NGN", help_text="Currency (e.g., NGN, USD)", blank=True)
    payable_to = models.CharField(max_length=255, help_text="Funds are payable to (Name/Bank Account)")
    payee_phone = models.CharField(max_length=20, help_text="Phone Number of Payee")
    payment_method = models.CharField(
        max_length=50, choices=PAYMENT_METHOD_CHOICES, default="transfer", help_text="Preferred mode of payment", blank=True
    )
    needed_by = models.DateField(help_text="When is the requested fund needed", null=True, blank=True)
    usage_commitment = models.TextField(
        default="I promise that the items (or services) purchased are to be used exclusively for the organization."
    )
    maintenance_commitment = models.TextField(
        default="I promise to keep all items in as good condition as possible at the approved location."
    )
    requester_signature = models.CharField(max_length=255, blank=True, help_text="Department Leader Signature (name)")
    requester_signed_date = models.DateField(null=True, blank=True)
    requester_signature_image = models.ImageField(
        upload_to="voucher_signatures/%Y/%m/%d/", null=True, blank=True, help_text="Signature image"
    )
    requester_phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    funds_approved = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    funds_denied = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    approved_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_vouchers"
    )
    approved_date = models.DateField(null=True, blank=True)
    finance_remarks = models.TextField(blank=True)
    finance_signature = models.CharField(max_length=255, blank=True)
    paid_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    paid_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        app_label = "church"
        ordering = ["-date_prepared", "-created_at"]
        indexes = [
            models.Index(fields=["voucher_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["requested_by", "date_prepared"]),
        ]

    def __str__(self):
        return f"{self.voucher_number}: {self.purpose[:50]}..."

    def save(self, *args, **kwargs):
        if not self.voucher_number:
            org_prefix = self.organization.slug.upper()[:3] if self.organization else "VCH"
            last_voucher = (
                Voucher.objects.filter(organization=self.organization, voucher_number__startswith=f"{org_prefix}-")
                .order_by("voucher_number")
                .last()
            )
            if last_voucher and last_voucher.voucher_number:
                try:
                    last_num = int(last_voucher.voucher_number.split("-")[1])
                    next_num = last_num + 1
                except (IndexError, ValueError):
                    next_num = 1
            else:
                next_num = 1
            self.voucher_number = f"{org_prefix}-{next_num:04d}"
        super().save(*args, **kwargs)

    @property
    def total_items_count(self):
        count = 0
        for field in [self.urgent_items, self.important_items, self.permissible_items]:
            if field:
                lines = [line.strip() for line in field.split("\n") if line.strip()]
                count += len(lines)
        return count

    @property
    def is_overdue(self):
        if self.needed_by and self.status not in ["paid", "completed", "cancelled"]:
            return timezone.now().date() > self.needed_by
        return False

    @property
    def is_approved(self):
        """Check if voucher is approved."""
        return self.status == "approved"

    @property
    def is_paid(self):
        """Check if voucher is paid."""
        return self.status == "paid"

    @property
    def is_pending(self):
        """Check if voucher is pending approval."""
        return self.status in ["draft", "submitted"]

    @property
    def is_rejected(self):
        """Check if voucher is rejected."""
        return self.status == "rejected"

    @property
    def is_completed(self):
        """Check if voucher is completed."""
        return self.status == "completed"

    @property
    def is_cancelled(self):
        """Check if voucher is cancelled."""
        return self.status == "cancelled"

    @property
    def is_submitted(self):
        """Check if voucher is submitted."""
        return self.status == "submitted"

    @property
    def is_draft(self):
        """Check if voucher is draft."""
        return self.status == "draft"

    @property
    def can_edit(self):
        """Check if voucher can be edited."""
        return self.status in ["draft", "submitted"]

    @property
    def can_submit(self):
        """Check if voucher can be submitted."""
        return self.status == "draft"

    @property
    def can_approve(self):
        """Check if voucher can be approved."""
        return self.status in ["submitted", "draft"]

    @property
    def can_reject(self):
        """Check if voucher can be rejected."""
        return self.status in ["submitted", "draft"]

    @property
    def can_mark_as_paid(self):
        """Check if voucher can be marked as paid."""
        return self.status == "approved"

    @property
    def can_complete(self):
        """Check if voucher can be completed."""
        return self.status == "paid"

    @property
    def can_cancel(self):
        """Check if voucher can be cancelled."""
        return self.status not in ["completed", "cancelled"]

    @property
    def formatted_voucher_number(self):
        """Get formatted voucher number with organization prefix."""
        return self.voucher_number

    @property
    def display_status(self):
        """Get display status with colors/indicators."""
        status_map = {
            "draft": ("Draft", "secondary"),
            "submitted": ("Submitted", "info"),
            "approved": ("Approved", "success"),
            "rejected": ("Rejected", "danger"),
            "paid": ("Paid", "primary"),
            "completed": ("Completed", "success"),
            "cancelled": ("Cancelled", "dark"),
        }
        return status_map.get(self.status, (self.get_status_display(), "secondary"))

    @property
    def has_finance_approval(self):
        """Check if voucher has finance approval."""
        return self.approved_by is not None and self.approved_date is not None

    @property
    def has_payment_info(self):
        """Check if voucher has payment information."""
        return self.paid_date is not None and self.paid_amount is not None

    @property
    def remaining_balance(self):
        """Calculate remaining balance if approved amount differs from requested."""
        if self.approved_amount and self.amount_in_figures:
            return self.amount_in_figures - self.approved_amount
        return Decimal(0)

    @property
    def needs_attention(self):
        """Check if voucher needs attention (overdue or pending)."""
        return self.is_overdue or (self.is_pending and self.needed_by and timezone.now().date() >= self.needed_by)

    def submit_for_approval(self):
        if self.status == "draft":
            self.status = "submitted"
            self.save()
            return True
        return False

    def approve(self, user, approved_amount=None, remarks=""):
        if self.status in ["submitted", "draft"]:
            self.status = "approved"
            self.approved_by = user
            self.approved_date = timezone.now().date()
            self.finance_remarks = remarks

            if approved_amount is not None:
                if isinstance(approved_amount, str):
                    try:
                        approved_amount = Decimal(approved_amount)
                    except Exception:
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

    def reject(self, user, reason=""):
        if self.status in ["submitted", "draft"]:
            self.status = "rejected"
            self.funds_denied = self.amount_in_figures
            self.finance_remarks = reason
            self.save()
            return True
        return False

    def mark_as_paid(self, amount=None, reference=""):
        if self.status == "approved":
            self.status = "paid"
            self.paid_date = timezone.now().date()
            self.paid_amount = amount if amount is not None else (self.approved_amount or self.amount_in_figures)
            self.payment_reference = reference
            self.save()
            return True
        return False

    def mark_as_completed(self):
        if self.status == "paid":
            self.status = "completed"
            self.save()
            return True
        return False

    def cancel(self, reason=""):
        if self.status not in ["completed", "cancelled"]:
            previous_status = self.status
            self.status = "cancelled"
            if reason:
                self.finance_remarks = f"{self.finance_remarks}\nCancelled: {reason}".strip()
            self.save()
            return True, previous_status
        return False, None


class VoucherAttachment(models.Model):
    """Supporting documents for vouchers."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="vouchers/attachments/%Y/%m/%d/")
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField()
    description = models.CharField(max_length=500, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "church"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.file_name} ({self.voucher.voucher_number})"


class VoucherComment(models.Model):
    """Internal comments/notes on vouchers."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="voucher_comments"
    )
    comment = models.TextField()
    is_internal = models.BooleanField(default=True, help_text="Internal notes not visible to requester")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "church"
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author} on {self.voucher.voucher_number}"


__all__ = ["VoucherTemplate", "Voucher", "VoucherAttachment", "VoucherComment"]
