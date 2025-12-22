import uuid

from django.conf import settings
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField


class Campus(models.Model):
    """Church campus/branch location."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "church.Organization", on_delete=models.CASCADE, related_name="campuses"
    )
    name = models.CharField(max_length=100)
    address = models.TextField(blank=True)
    phone = PhoneNumberField(blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "church"
        verbose_name_plural = "Campuses"
        unique_together = ["organization", "name"]

    def __str__(self):
        return f"{self.name} ({self.organization.slug})"


class Member(models.Model):
    """Comprehensive church member profile."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member_profile",
        null=True,
        blank=True,
    )
    organization = models.ForeignKey(
        "church.Organization", on_delete=models.CASCADE, related_name="members"
    )

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
        ("prefer_not_to_say", "Prefer not to say"),
    ]
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True)

    date_of_birth = models.DateField(null=True, blank=True)
    photo = models.ImageField(upload_to="members/photos/", null=True, blank=True)
    phone = PhoneNumberField(blank=True)
    email = models.EmailField(blank=True)

    STATUS_CHOICES = [
        ("new", "New"),
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("visitor", "Visitor"),
        ("transferred", "Transferred"),
        ("deceased", "Deceased"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")

    campus = models.ForeignKey(
        "church.Campus",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )

    join_date = models.DateField(null=True, blank=True)

    family = models.ForeignKey(
        "church.Family",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )

    FAMILY_ROLE_CHOICES = [
        ("head", "Family Head"),
        ("spouse", "Spouse"),
        ("child", "Child"),
        ("parent", "Parent"),
        ("sibling", "Sibling"),
        ("other", "Other"),
    ]
    family_role = models.CharField(max_length=20, choices=FAMILY_ROLE_CHOICES, blank=True)

    spouse = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="married_to",
    )

    address = models.TextField(blank=True)

    MARITAL_STATUS_CHOICES = [
        ("single", "Single"),
        ("married", "Married"),
        ("divorced", "Divorced"),
        ("widowed", "Widowed"),
        ("separated", "Separated"),
    ]
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, blank=True)

    occupation = models.CharField(max_length=200, blank=True)

    BLOOD_TYPE_CHOICES = [
        ("a_positive", "A+"),
        ("a_negative", "A-"),
        ("b_positive", "B+"),
        ("b_negative", "B-"),
        ("ab_positive", "AB+"),
        ("ab_negative", "AB-"),
        ("o_positive", "O+"),
        ("o_negative", "O-"),
        ("unknown", "Unknown"),
    ]
    blood_type = models.CharField(max_length=20, choices=BLOOD_TYPE_CHOICES, blank=True)

    next_of_kin_name = models.CharField(max_length=200, blank=True, null=True)
    next_of_kin_phone = PhoneNumberField(blank=True, null=True)
    next_of_kin_relationship = models.CharField(max_length=100, blank=True, null=True)

    residential_country = models.CharField(max_length=100, blank=True, null=True)
    residential_state = models.CharField(max_length=100, blank=True, null=True)
    residential_city = models.CharField(max_length=100, blank=True, null=True)

    origin_country = models.CharField(max_length=100, blank=True, null=True)
    origin_state = models.CharField(max_length=100, blank=True, null=True)
    origin_city = models.CharField(max_length=100, blank=True, null=True)

    notes = models.TextField(blank=True)

    departments = models.ManyToManyField("church.Department", related_name="members", blank=True)

    BAPTISM_STATUS_CHOICES = [
        ("not_baptized", "Not Baptized"),
        ("water_baptized", "Water Baptized"),
        ("spirit_baptized", "Spirit Baptized"),
        ("both", "Both Water and Spirit Baptized"),
    ]
    baptism_status = models.CharField(max_length=30, choices=BAPTISM_STATUS_CHOICES, blank=True)

    baptism_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_members",
    )

    class Meta:
        app_label = "church"
        ordering = ["last_name", "first_name"]
        unique_together = ["organization", "email"]

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


class Family(models.Model):
    """Family unit for grouping members."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "church.Organization", on_delete=models.CASCADE, related_name="families"
    )
    family_name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    phone = PhoneNumberField(blank=True)
    email = models.EmailField(blank=True)
    family_head = models.ForeignKey(
        "church.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="headed_families",
    )

    class Meta:
        app_label = "church"
        verbose_name_plural = "Families"
        unique_together = ["organization", "family_name"]

    def __str__(self):
        return f"{self.family_name} Family ({self.organization.slug})"


class Department(models.Model):
    """Church departments/groups (Choir, Ushers, Children's Church, etc.)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "church.Organization", on_delete=models.CASCADE, related_name="departments"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    leader = models.ForeignKey(
        "church.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_departments",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "church"
        unique_together = ["organization", "name"]

    def __str__(self):
        return f"{self.name} ({self.organization.slug})"


__all__ = ["Member", "Family", "Department", "Campus"]
