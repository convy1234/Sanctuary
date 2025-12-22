import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class InventoryCategory(models.Model):
    """Category for inventory items"""

    CATEGORY_TYPES = [
        ("worship", "Worship Supplies"),
        ("event", "Event Equipment"),
        ("office", "Office Supplies"),
        ("maintenance", "Maintenance"),
        ("kitchen", "Kitchen Supplies"),
        ("technology", "Technology"),
        ("furniture", "Furniture"),
        ("seasonal", "Seasonal Decorations"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "church.Organization", on_delete=models.CASCADE, related_name="inventory_categories"
    )
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES, default="other")
    color_code = models.CharField(max_length=7, default="#6c757d", help_text="Hex color for UI display")
    description = models.TextField(blank=True)

    class Meta:
        app_label = "church"
        ordering = ["category_type", "name"]
        verbose_name_plural = "Inventory Categories"
        unique_together = ["organization", "name"]

    def __str__(self):
        return f"{self.name} ({self.organization.slug})"


class InventoryVendor(models.Model):
    """Vendors for purchasing inventory items"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "church.Organization", on_delete=models.CASCADE, related_name="inventory_vendors"
    )
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        app_label = "church"
        ordering = ["name"]
        unique_together = ["organization", "name"]

    def __str__(self):
        return f"{self.name} ({self.organization.slug})"


class InventoryItem(models.Model):
    """Main inventory item model"""

    ITEM_TYPES = [
        ("consumable", "Consumable (Communion, candles, etc.)"),
        ("equipment", "Equipment (Sound, projectors, etc.)"),
        ("asset", "Capital Asset (Expensive, long-term)"),
        ("furniture", "Furniture"),
        ("supply", "General Supply"),
        ("resource", "Resource (Books, media)"),
    ]

    CONDITION_CHOICES = [
        ("new", "New"),
        ("excellent", "Excellent"),
        ("good", "Good"),
        ("fair", "Fair"),
        ("poor", "Poor"),
        ("repair", "Needs Repair"),
        ("retired", "Retired/Disposed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("church.Organization", on_delete=models.CASCADE, related_name="inventory_items")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    department = models.ForeignKey(
        "church.Department", on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_items"
    )
    category = models.ForeignKey(
        InventoryCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="items"
    )
    item_type = models.CharField(max_length=20, choices=ITEM_TYPES, default="supply")
    sku = models.CharField(max_length=100, blank=True, db_index=True)
    asset_tag = models.CharField(max_length=100, blank=True, null=True, unique=True)
    barcode = models.CharField(max_length=50, blank=True, null=True, unique=True)
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reorder_level = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reorder_quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    alert_on_low = models.BooleanField(default=True)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default="good")
    location = models.CharField(max_length=200, blank=True)
    storage_instructions = models.TextField(blank=True)
    image = models.ImageField(upload_to="inventory_items/%Y/%m/", blank=True, null=True)
    vendor = models.ForeignKey(
        InventoryVendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="items"
    )
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    replacement_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_audited = models.DateField(null=True, blank=True)
    last_checked_out = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_inventory_items"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "church"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["sku"]),
            models.Index(fields=["barcode"]),
            models.Index(fields=["department"]),
            models.Index(fields=["item_type"]),
            models.Index(fields=["condition"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["organization", "quantity"]),
        ]

    def __str__(self):
        dept_code = self.department.code if self.department and hasattr(self.department, "code") else "N/A"
        return f"{self.name} ({dept_code})"

    def save(self, *args, **kwargs):
        if not self.barcode and not self.pk:
            super().save(*args, **kwargs)
            self.barcode = f"INV-{self.organization.slug.upper()}-{self.pk:06d}"
        if not self.sku:
            category_code = self.category.name[:3].upper() if self.category else "GEN"
            dept_code = self.department.code[:3].upper() if self.department and hasattr(self.department, "code") else "GEN"
            self.sku = f"{dept_code}-{category_code}-{self.pk:06d}"
        super().save(*args, **kwargs)

    @property
    def total_value(self):
        if self.purchase_price and self.quantity:
            return Decimal(self.purchase_price) * Decimal(self.quantity)
        return Decimal("0.00")

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_level if self.alert_on_low else False

    @property
    def status(self):
        if not self.is_active:
            return "inactive"
        if self.quantity <= 0:
            return "out_of_stock"
        if self.is_low_stock:
            return "low_stock"
        return "in_stock"


class InventoryTransaction(models.Model):
    """Track all inventory movements"""

    TRANSACTION_TYPES = [
        ("add", "Stock Added"),
        ("remove", "Stock Removed"),
        ("transfer", "Department Transfer"),
        ("checkout", "Checked Out"),
        ("return", "Returned"),
        ("adjust", "Audit Adjustment"),
        ("write_off", "Write Off"),
        ("damage", "Damaged/Lost"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "church.Organization", on_delete=models.CASCADE, related_name="inventory_transactions"
    )
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField()
    from_department = models.ForeignKey(
        "church.Department", related_name="transactions_from", null=True, blank=True, on_delete=models.SET_NULL
    )
    to_department = models.ForeignKey(
        "church.Department", related_name="transactions_to", null=True, blank=True, on_delete=models.SET_NULL
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="performed_inventory_transactions",
    )
    voucher = models.ForeignKey(
        "church.Voucher",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_transactions",
        help_text="Related voucher for purchase",
    )
    notes = models.TextField(blank=True)
    reference_number = models.CharField(max_length=50, blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    requires_approval = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_inventory_transactions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "church"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["transaction_type"]),
            models.Index(fields=["item", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.item.name} ({self.quantity})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and self.approved_by:
            self.update_item_stock()

    def update_item_stock(self):
        if self.transaction_type in ["add", "return"]:
            self.item.quantity += self.quantity
        elif self.transaction_type in ["remove", "checkout", "write_off", "damage"]:
            self.item.quantity = max(0, self.item.quantity - self.quantity)
        self.item.save(update_fields=["quantity", "updated_at"])


class InventoryCheckout(models.Model):
    """Track items checked out by members/staff"""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("overdue", "Overdue"),
        ("returned", "Returned"),
        ("lost", "Lost"),
        ("damaged", "Damaged"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("church.Organization", on_delete=models.CASCADE, related_name="inventory_checkouts")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="checkouts")
    member = models.ForeignKey(
        "church.Member", on_delete=models.PROTECT, related_name="inventory_checkouts", help_text="Member checking out item"
    )
    department = models.ForeignKey("church.Department", on_delete=models.PROTECT, related_name="checkouts")
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    purpose = models.CharField(max_length=200, blank=True)
    event_name = models.CharField(max_length=100, blank=True)
    checkout_date = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    expected_return_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    returned_quantity = models.IntegerField(default=0)
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_condition = models.CharField(max_length=20, choices=InventoryItem.CONDITION_CHOICES, blank=True)
    return_notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_checkouts"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_inventory_checkouts"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    class Meta:
        app_label = "church"
        ordering = ["-checkout_date"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["member", "status"]),
        ]

    def __str__(self):
        return f"{self.item.name} -> {self.member.full_name}"

    @property
    def is_overdue(self):
        return self.due_date and self.status == "active" and timezone.now().date() > self.due_date

    @property
    def days_overdue(self):
        return (timezone.now().date() - self.due_date).days if self.is_overdue else 0

    def save(self, *args, **kwargs):
        if self.due_date and self.status == "active" and timezone.now().date() > self.due_date:
            self.status = "overdue"
        if self.status == "active":
            self.item.last_checked_out = timezone.now().date()
            self.item.save(update_fields=["last_checked_out"])
        super().save(*args, **kwargs)


class InventoryAudit(models.Model):
    """Inventory audit/stock count"""

    AUDIT_TYPES = [
        ("full", "Full Inventory Audit"),
        ("spot", "Spot Check"),
        ("cycle", "Cycle Count"),
        ("department", "Department Audit"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("church.Organization", on_delete=models.CASCADE, related_name="inventory_audits")
    name = models.CharField(max_length=200)
    audit_type = models.CharField(max_length=20, choices=AUDIT_TYPES)
    department = models.ForeignKey(
        "church.Department", on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_audits"
    )
    auditor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="conducted_inventory_audits"
    )
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="participated_inventory_audits", blank=True)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    total_items = models.IntegerField(default=0)
    items_checked = models.IntegerField(default=0)
    discrepancies_found = models.IntegerField(default=0)
    accuracy_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    notes = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "church"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} - {self.start_date.strftime('%Y-%m-%d')}"


class InventoryAuditItem(models.Model):
    """Individual items in an audit"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit = models.ForeignKey(InventoryAudit, on_delete=models.CASCADE, related_name="audit_items")
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    expected_quantity = models.IntegerField()
    counted_quantity = models.IntegerField()
    difference = models.IntegerField(default=0)
    notes = models.TextField(blank=True)
    adjusted = models.BooleanField(default=False)
    counted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    counted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "church"
        unique_together = ["audit", "item"]

    def __str__(self):
        return f"{self.item.name} - Expected: {self.expected_quantity}, Counted: {self.counted_quantity}"

    def save(self, *args, **kwargs):
        self.difference = self.counted_quantity - self.expected_quantity
        super().save(*args, **kwargs)


class InventoryNotification(models.Model):
    """Notifications for inventory events"""

    NOTIFICATION_TYPES = [
        ("low_stock", "Low Stock Alert"),
        ("overdue", "Overdue Checkout"),
        ("audit", "Audit Required"),
        ("maintenance", "Maintenance Due"),
        ("system", "System Notification"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "church.Organization", on_delete=models.CASCADE, related_name="inventory_notifications"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inventory_notifications"
    )
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    related_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, null=True, blank=True)
    related_checkout = models.ForeignKey(InventoryCheckout, on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    is_important = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "church"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notification_type}: {self.title}"


__all__ = [
    "InventoryCategory",
    "InventoryVendor",
    "InventoryItem",
    "InventoryTransaction",
    "InventoryCheckout",
    "InventoryAudit",
    "InventoryAuditItem",
    "InventoryNotification",
]
