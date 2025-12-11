# sanctuary/church/admin.py
from django.contrib import admin
from django import forms
from django.contrib import messages
from django.utils import timezone
from .models import Invite, Organization, Membership, OrganizationApplication, Payment
import secrets


class InviteAdminForm(forms.ModelForm):
    class Meta:
        model = Invite
        fields = '__all__'


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    form = InviteAdminForm
    list_display = ('email', 'organization', 'role', 'expires_at', 'accepted_at', 'is_valid')
    list_filter = ('role', 'accepted_at', 'expires_at')
    search_fields = ('email', 'organization__name', 'token')
    readonly_fields = ('token', 'created_at', 'accepted_at')
    
    def save_model(self, request, obj, form, change):
        # Generate token if not set
        if not obj.token:
            obj.token = secrets.token_urlsafe(32)
        
        # Save the model
        super().save_model(request, obj, form, change)
        
        # Send email after saving (for new invites only)
        if not change:  # Only for new invites, not edits
            try:
                # Import here to avoid circular imports
                from .views import send_invite_email
                send_invite_email(obj)
                self.message_user(request, f"Invite sent to {obj.email}")
            except Exception as e:
                self.message_user(
                    request, 
                    f"Invite saved but email failed to send: {str(e)}", 
                    level=messages.ERROR
                )
    
    def is_valid(self, obj):
        return obj.is_valid()
    is_valid.boolean = True
    is_valid.short_description = 'Valid'


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'owner', 'created_at')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'role', 'is_primary_admin', 'created_at')
    list_filter = ('role', 'is_primary_admin')
    search_fields = ('user__email', 'organization__name')


@admin.register(OrganizationApplication)
class OrganizationApplicationAdmin(admin.ModelAdmin):
    list_display = ('organization_name', 'contact_person', 'contact_email', 'status', 'applied_at')
    list_filter = ('status', 'applied_at')
    search_fields = ('organization_name', 'contact_person', 'contact_email')
    readonly_fields = ('applied_at', 'reviewed_at')
    
    actions = ['approve_applications', 'reject_applications']
    
    def approve_applications(self, request, queryset):
        updated = queryset.update(status='approved', reviewed_at=timezone.now())
        self.message_user(request, f'{updated} application(s) approved.')
    approve_applications.short_description = "Approve selected applications"
    
    def reject_applications(self, request, queryset):
        updated = queryset.update(status='rejected', reviewed_at=timezone.now())
        self.message_user(request, f'{updated} application(s) rejected.')
    reject_applications.short_description = "Reject selected applications"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('organization', 'amount', 'status', 'paid_at', 'created_at')
    list_filter = ('status', 'paid_at')
    search_fields = ('organization__name', 'transaction_id')
    readonly_fields = ('created_at', 'paid_at')