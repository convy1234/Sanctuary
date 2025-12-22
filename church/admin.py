from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from import_export.admin import ImportExportModelAdmin
from .models import (
    Organization, SubscriptionPlan, OrganizationSubscription,
    Invitation, Member, Campus, Family, Department,
    VoucherTemplate, Voucher, VoucherAttachment, VoucherComment
)


# ========== Inline Models ==========
class OrganizationSubscriptionInline(admin.StackedInline):
    """Inline display for Organization's subscription."""
    model = OrganizationSubscription
    extra = 0
    max_num = 1
    can_delete = False
    verbose_name = "Subscription"
    verbose_name_plural = "Subscription"
    fields = ('plan', 'status', 'price_override', 'started_at', 'ends_at')
    readonly_fields = ('started_at',)


class MemberInline(admin.TabularInline):
    """Inline display for Organization's members."""
    model = Member
    extra = 0
    fields = ('full_name', 'email', 'phone', 'status')
    readonly_fields = ('full_name',)
    
    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = "Name"


class CampusInline(admin.TabularInline):
    """Inline display for Organization's campuses."""
    model = Campus
    extra = 0
    fields = ('name', 'is_active', 'phone', 'email')


class FamilyInline(admin.TabularInline):
    """Inline display for Organization's families."""
    model = Family
    extra = 0
    fields = ('family_name', 'family_head', 'phone', 'email')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "family_head":
            if request._obj_ is not None:
                kwargs["queryset"] = Member.objects.filter(
                    organization=request._obj_
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class DepartmentInline(admin.TabularInline):
    """Inline display for Organization's departments."""
    model = Department
    extra = 0
    fields = ('name', 'leader', 'is_active')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "leader":
            if request._obj_ is not None:
                kwargs["queryset"] = Member.objects.filter(
                    organization=request._obj_
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class VoucherTemplateInline(admin.TabularInline):
    """Inline display for Organization's voucher templates."""
    model = VoucherTemplate
    extra = 0
    fields = ('name', 'is_default', 'form_title', 'created_at')
    readonly_fields = ('created_at',)


class VoucherInline(admin.TabularInline):
    """Inline display for Organization's vouchers."""
    model = Voucher
    extra = 0
    fields = ('voucher_number', 'title', 'requested_by', 'status', 'date_prepared', 'amount_in_figures')
    readonly_fields = ('voucher_number', 'date_prepared')
    show_change_link = True


# ========== Voucher Inline Models ==========
class VoucherAttachmentInline(admin.TabularInline):
    """Inline display for Voucher attachments."""
    model = VoucherAttachment
    extra = 0
    fields = ('file', 'file_name', 'description', 'uploaded_at')
    readonly_fields = ('file_name', 'file_type', 'file_size', 'uploaded_at')


class VoucherCommentInline(admin.TabularInline):
    """Inline display for Voucher comments."""
    model = VoucherComment
    extra = 0
    fields = ('author', 'comment', 'is_internal', 'created_at')
    readonly_fields = ('created_at',)


# ========== Main Admin Classes ==========
@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Admin interface for Organization model."""
    list_display = ('name', 'slug', 'created_by', 'created_at', 'member_count', 'subscription_status', 'voucher_count')
    list_filter = ('created_at',)
    search_fields = ('name', 'slug', 'created_by__email')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at',)
    
    inlines = [
        OrganizationSubscriptionInline,
        CampusInline,
        FamilyInline,
        DepartmentInline,
        VoucherTemplateInline,
        VoucherInline,
        MemberInline,
    ]
    
    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = "Members"
    
    def subscription_status(self, obj):
        if hasattr(obj, 'subscription'):
            return obj.subscription.status
        return "No Subscription"
    subscription_status.short_description = "Subscription"
    
    def voucher_count(self, obj):
        return obj.vouchers.count()
    voucher_count.short_description = "Vouchers"
    
    def get_form(self, request, obj=None, **kwargs):
        request._obj_ = obj
        return super().get_form(request, obj, **kwargs)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    """Admin interface for SubscriptionPlan model."""
    list_display = ('name', 'slug', 'billing_period', 'base_price', 'price_per_user', 
                   'included_users', 'is_active', 'subscription_count')
    list_filter = ('is_active', 'billing_period', 'created_at')
    search_fields = ('name', 'slug', 'description')
    list_editable = ('is_active',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'is_active')
        }),
        ('Pricing', {
            'fields': ('billing_period', 'base_price', 'price_per_user')
        }),
        ('User Capacity', {
            'fields': ('included_users', 'capacity_min', 'capacity_max')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def subscription_count(self, obj):
        return obj.subscriptions.count()
    subscription_count.short_description = "Active Subs"


@admin.register(OrganizationSubscription)
class OrganizationSubscriptionAdmin(admin.ModelAdmin):
    """Admin interface for OrganizationSubscription model."""
    list_display = ('organization', 'plan', 'status', 'started_at', 'ends_at', 
                   'price_override', 'current_price_display')
    list_filter = ('status', 'plan', 'started_at')
    search_fields = ('organization__name', 'organization__slug', 'plan__name')
    readonly_fields = ('created_at', 'updated_at', 'started_at')
    raw_id_fields = ('organization', 'plan')
    
    fieldsets = (
        ('Subscription Details', {
            'fields': ('organization', 'plan', 'status')
        }),
        ('Pricing', {
            'fields': ('price_override',)
        }),
        ('Dates', {
            'fields': ('started_at', 'ends_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def current_price_display(self, obj):
        return f"${obj.current_price():.2f}"
    current_price_display.short_description = "Current Price"


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    """Admin interface for Invitation model."""
    list_display = ('email', 'organization', 'role', 'invited_by', 'status', 
                   'created_at', 'expires_at')
    list_filter = ('role', 'organization', 'created_at', 'expires_at')
    search_fields = ('email', 'organization__name', 'token')
    readonly_fields = ('token', 'created_at', 'updated_at', 'status')
    raw_id_fields = ('organization', 'invited_by')
    
    fieldsets = (
        ('Invitation Details', {
            'fields': ('email', 'organization', 'role', 'invited_by', 'as_owner')
        }),
        ('Status', {
            'fields': ('token', 'expires_at', 'accepted_at', 'note')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def status(self, obj):
        if obj.is_used:
            return format_html('<span style="color: green;">✓ Used</span>')
        elif obj.is_expired:
            return format_html('<span style="color: red;">✗ Expired</span>')
        else:
            return format_html('<span style="color: orange;">● Pending</span>')
    status.short_description = "Status"
    
    actions = ['resend_invitation']
    
    def resend_invitation(self, request, queryset):
        count = queryset.count()
        self.message_user(request, f"{count} invitation(s) marked for resending.")
    resend_invitation.short_description = "Resend selected invitations"


# ========== Church Models Admin ==========
class MemberDepartmentInline(admin.TabularInline):
    """Inline for Member's departments."""
    model = Member.departments.through
    extra = 1
    verbose_name = "Department"
    verbose_name_plural = "Departments"


@admin.register(Member)
class MemberAdmin(ImportExportModelAdmin):
    """Admin interface for Member model."""
    list_display = ('full_name', 'organization', 'phone', 'email', 'status', 
                   'age_display', 'created_at')
    list_filter = ('status', 'gender', 'marital_status', 'organization', 'created_at')
    search_fields = ('first_name', 'last_name', 'email', 'phone', 'address')
    readonly_fields = ('created_at', 'updated_at', 'age_display')
    raw_id_fields = ('organization', 'user', 'family', 'spouse', 'campus', 'created_by')
    inlines = [MemberDepartmentInline]
    
    fieldsets = (
        ('Personal Information', {
            'fields': (
                ('first_name', 'last_name'),
                'gender',
                'date_of_birth',
                'photo',
                'age_display'
            )
        }),
        ('Contact Information', {
            'fields': (
                'phone',
                'email',
                'address',
                ('residential_country', 'residential_state', 'residential_city'),
                ('origin_country', 'origin_state', 'origin_city')
            )
        }),
        ('Church Information', {
            'fields': (
                'organization',
                'status',
                'campus',
                'join_date'
            )
        }),
        ('Family Information', {
            'fields': (
                'family',
                'family_role',
                'spouse',
                'marital_status'
            )
        }),
        ('Professional & Medical', {
            'fields': (
                'occupation',
                'blood_type'
            )
        }),
        ('Spiritual Information', {
            'fields': (
                'baptism_status',
                'baptism_date'
            )
        }),
        ('Emergency Contact', {
            'fields': (
                'next_of_kin_name',
                'next_of_kin_phone',
                'next_of_kin_relationship'
            )
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('System Fields', {
            'fields': ('user', 'created_by'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def age_display(self, obj):
        age = obj.age
        if age is not None:
            return f"{age} years"
        return "Not specified"
    age_display.short_description = "Age"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'family', 'campus', 'user'
        )


@admin.register(Campus)
class CampusAdmin(ImportExportModelAdmin):
    """Admin interface for Campus model."""
    list_display = ('name', 'organization', 'is_active', 'phone', 'email', 'member_count')
    list_filter = ('is_active', 'organization')
    search_fields = ('name', 'address', 'phone', 'email')
    raw_id_fields = ('organization',)
    
    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = "Members"


@admin.register(Family)
class FamilyAdmin(ImportExportModelAdmin):
    """Admin interface for Family model."""
    list_display = ('family_name', 'organization', 'family_head', 'phone', 
                   'email', 'member_count')
    list_filter = ('organization',)
    search_fields = ('family_name', 'address', 'phone', 'email')
    raw_id_fields = ('organization', 'family_head')
    
    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = "Members"
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "family_head":
            if 'object_id' in request.resolver_match.kwargs:
                family_id = request.resolver_match.kwargs['object_id']
                try:
                    family = Family.objects.get(id=family_id)
                    kwargs["queryset"] = Member.objects.filter(
                        organization=family.organization
                    )
                except Family.DoesNotExist:
                    pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Department)
class DepartmentAdmin(ImportExportModelAdmin):
    """Admin interface for Department model."""
    list_display = ('name', 'organization', 'leader', 'is_active', 'member_count')
    list_filter = ('is_active', 'organization')
    search_fields = ('name', 'description')
    raw_id_fields = ('organization', 'leader')
    
    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = "Members"
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "leader":
            if 'object_id' in request.resolver_match.kwargs:
                dept_id = request.resolver_match.kwargs['object_id']
                try:
                    department = Department.objects.get(id=dept_id)
                    kwargs["queryset"] = Member.objects.filter(
                        organization=department.organization
                    )
                except Department.DoesNotExist:
                    pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ========== Voucher Models Admin ==========
@admin.register(VoucherTemplate)
class VoucherTemplateAdmin(admin.ModelAdmin):
    """Admin interface for VoucherTemplate model."""
    list_display = ('name', 'organization', 'is_default', 'form_title', 'created_at', 'voucher_count')
    list_filter = ('is_default', 'organization', 'created_at')
    search_fields = ('name', 'form_title', 'church_name', 'organization__name')
    list_editable = ('is_default',)
    raw_id_fields = ('organization', 'created_by')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('organization', 'name', 'is_default')
        }),
        ('Header & Logo', {
            'fields': ('logo', 'church_name', 'church_motto', 'form_title')
        }),
        ('Instructions', {
            'fields': ('description', 'warning_text')
        }),
        ('Form Configuration', {
            'fields': (
                'show_urgent_items',
                'show_important_items',
                'show_permissible_items'
            )
        }),
        ('Signature Section', {
            'fields': ('signature_label', 'date_label', 'phone_label')
        }),
        ('Footer & Finance Section', {
            'fields': ('footer_text', 'finance_section_title', 'finance_office_name')
        }),
        ('Default Commitments', {
            'fields': ('default_usage_commitment', 'default_maintenance_commitment')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def voucher_count(self, obj):
        return obj.vouchers.count()
    voucher_count.short_description = "Vouchers"


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    """Admin interface for Voucher model."""
    list_display = (
        'voucher_number', 'organization', 'title', 'requester_name_department',
        'status', 'amount_in_figures', 'date_prepared', 'days_open', 'is_overdue_display'
    )  # Changed 'status_display' to 'status'
    list_filter = ('status', 'organization', 'date_prepared', 'payment_method')
    search_fields = ('voucher_number', 'title', 'purpose', 'requester_name_department', 'payable_to')
    readonly_fields = (
        'voucher_number', 'created_at', 'updated_at', 'days_open', 
        'is_overdue', 'total_items_count'  # Removed 'status_display' from readonly_fields
    )
    raw_id_fields = ('organization', 'requested_by', 'approved_by', 'template')
    list_editable = ('status',)  # This is now valid since 'status' is in list_display
    inlines = [VoucherAttachmentInline, VoucherCommentInline]
    
    fieldsets = (
        ('Voucher Information', {
            'fields': (
                'voucher_number',
                'organization',
                'title',
                'template',
                'status',
                'version'
            )
        }),
        ('Requester Information', {
            'fields': (
                'date_prepared',
                'requested_by',
                'requester_name_department'
            )
        }),
        ('Request Details', {
            'fields': (
                'purpose',
                'urgent_items',
                'important_items',
                'permissible_items',
                'total_items_count'
            )
        }),
        ('Financial Information', {
            'fields': (
                'amount_in_words',
                'amount_in_figures',
                'currency',
                'payable_to',
                'payee_phone',
                'payment_method',
                'needed_by'
            )
        }),
        ('Commitments', {
            'fields': (
                'usage_commitment',
                'maintenance_commitment'
            )
        }),
        ('Requester Signature', {
            'fields': (
                'requester_signature',
                'requester_signed_date',
                'requester_signature_image',
                'requester_phone'
            )
        }),
        ('Finance Office Section', {
            'fields': (
                'funds_approved',
                'funds_denied',
                'approved_amount',
                'approved_by',
                'approved_date',
                'finance_remarks',
                'finance_signature'
            )
        }),
        ('Payment Information', {
            'fields': (
                'paid_amount',
                'paid_date',
                'payment_reference'
            )
        }),
        ('Status Information', {
            'fields': (
                'days_open',
                'is_overdue'
                # Removed 'status_display'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    # Keep this method for display purposes, but don't put it in list_display
    def status_display(self, obj):
        status_colors = {
            'draft': 'gray',
            'submitted': 'blue',
            'approved': 'orange',
            'rejected': 'red',
            'paid': 'green',
            'completed': 'darkgreen',
            'cancelled': 'darkred',
        }
        color = status_colors.get(obj.status, 'black')
        return format_html(f'<span style="color: {color}; font-weight: bold;">{obj.get_status_display()}</span>')
    status_display.short_description = "Status Display"
    
    def is_overdue_display(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color: red;">⚠ OVERDUE</span>')
        return ""
    is_overdue_display.short_description = "Overdue"
    
    def days_open(self, obj):
        return obj.days_open
    days_open.short_description = "Days Open"
    
    actions = ['submit_for_approval', 'approve_selected', 'mark_as_paid', 'reject_selected']
    
    def submit_for_approval(self, request, queryset):
        count = 0
        for voucher in queryset.filter(status='draft'):
            if voucher.submit_for_approval():
                count += 1
        self.message_user(request, f"{count} voucher(s) submitted for approval.")
    submit_for_approval.short_description = "Submit selected for approval"
    
    def approve_selected(self, request, queryset):
        count = 0
        for voucher in queryset.filter(status__in=['draft', 'submitted']):
            if voucher.approve(request.user):
                count += 1
        self.message_user(request, f"{count} voucher(s) approved.")
    approve_selected.short_description = "Approve selected vouchers"
    
    def mark_as_paid(self, request, queryset):
        count = 0
        for voucher in queryset.filter(status='approved'):
            if voucher.mark_as_paid():
                count += 1
        self.message_user(request, f"{count} voucher(s) marked as paid.")
    mark_as_paid.short_description = "Mark selected as paid"
    
    def reject_selected(self, request, queryset):
        count = 0
        for voucher in queryset.filter(status__in=['draft', 'submitted']):
            if voucher.reject(request.user, "Rejected via admin action"):
                count += 1
        self.message_user(request, f"{count} voucher(s) rejected.")
    reject_selected.short_description = "Reject selected vouchers"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'organization', 'requested_by', 'approved_by', 'template'
        )


@admin.register(VoucherAttachment)
class VoucherAttachmentAdmin(admin.ModelAdmin):
    """Admin interface for VoucherAttachment model."""
    list_display = ('file_name', 'voucher', 'file_type', 'file_size', 'uploaded_by', 'uploaded_at')
    list_filter = ('file_type', 'uploaded_at', 'voucher__organization')
    search_fields = ('file_name', 'description', 'voucher__voucher_number')
    readonly_fields = ('file_name', 'file_type', 'file_size', 'uploaded_at')
    raw_id_fields = ('voucher', 'uploaded_by')
    
    fieldsets = (
        ('File Information', {
            'fields': (
                'voucher',
                'file',
                'file_name',
                'file_type',
                'file_size'
            )
        }),
        ('Description', {
            'fields': ('description',)
        }),
        ('Upload Information', {
            'fields': ('uploaded_by', 'uploaded_at')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('voucher', 'uploaded_by')


@admin.register(VoucherComment)
class VoucherCommentAdmin(admin.ModelAdmin):
    """Admin interface for VoucherComment model."""
    list_display = ('voucher', 'author', 'comment_preview', 'is_internal', 'created_at')
    list_filter = ('is_internal', 'created_at', 'voucher__organization')
    search_fields = ('comment', 'voucher__voucher_number', 'author__email')
    readonly_fields = ('created_at',)
    raw_id_fields = ('voucher', 'author')
    
    fieldsets = (
        ('Comment Details', {
            'fields': (
                'voucher',
                'author',
                'comment',
                'is_internal'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def comment_preview(self, obj):
        if len(obj.comment) > 50:
            return f"{obj.comment[:50]}..."
        return obj.comment
    comment_preview.short_description = "Comment"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('voucher', 'author')


# ========== Admin Site Customization ==========
admin.site.site_header = "Church Management System"
admin.site.site_title = "CMS Admin"
admin.site.index_title = "Administration Dashboard"
