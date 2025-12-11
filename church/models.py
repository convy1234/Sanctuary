# sanctuary/church/models.py
import uuid
import secrets
from django.db import models
from django.conf import settings
from django.utils import timezone

def default_expires():
    return timezone.now() + timezone.timedelta(hours=72)


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="owned_organizations")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Invite(models.Model):
    ROLE_CHOICES = [
        ("org_owner", "Organization owner"),
        ("admin", "Admin"),
        ("hod", "Head of Department"),
        ("manager", "Manager"),
        ("staff", "Staff"),
        ("member", "Member"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    inviter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_invites")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invites")
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default="staff")
    token = models.CharField(max_length=128, unique=True, db_index=True)
    expires_at = models.DateTimeField(default=default_expires)
    accepted_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="used_invites")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Invite {self.email} → {self.organization} ({self.role})"

    @classmethod
    def create_invite(cls, email, inviter, organization, role="staff", expiry_hours=72):
        token = secrets.token_urlsafe(32)
        expires = timezone.now() + timezone.timedelta(hours=expiry_hours)
        return cls.objects.create(email=email.lower().strip(), inviter=inviter, organization=organization, role=role, token=token, expires_at=expires)

    def is_valid(self):
        return (self.accepted_at is None) and (self.expires_at > timezone.now())
    
    def save(self, *args, **kwargs):
        # Generate token if it doesn't exist
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        
        # Set expires_at if not set
        if not self.expires_at:
            from django.utils import timezone
            self.expires_at = timezone.now() + timezone.timedelta(hours=72)
        
        super().save(*args, **kwargs)


# Membership (append to sanctuary/church/models.py)

class Membership(models.Model):
    ROLE_CHOICES = [
        ("org_owner", "Organization owner"),
        ("admin", "Admin"),
        ("hod", "Head of Department"),
        ("manager", "Manager"),
        ("staff", "Staff"),
        ("volunteer", "Volunteer"),
        ("viewer", "Viewer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="members")
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default="staff")
    is_primary_admin = models.BooleanField(default=False)  # e.g., the owner/primary admin
    scopes = models.JSONField(default=dict, blank=True, help_text="Optional scoped privileges (manager_scopes).")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "organization")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user.email} @ {self.organization.slug} ({self.role})"


# sanctuary/church/models.py (add these models)
class OrganizationApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_name = models.CharField(max_length=255)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_person = models.CharField(max_length=255)
    church_denomination = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=500, blank=True)
    about = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    applied_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.organization_name} - {self.status}"


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=50, blank=True)
    transaction_id = models.CharField(max_length=255, blank=True, db_index=True)
    payment_data = models.JSONField(default=dict, blank=True)  # Store payment provider response
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.organization.name} - {self.amount} ({self.status})"
    
