from django.contrib import admin

from .models import Invitation, Organization, OrganizationSubscription, SubscriptionPlan


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    readonly_fields = ("created_at",)


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "organization", "role", "as_owner", "invited_by", "expires_at", "accepted_at")
    list_filter = ("organization", "role", "accepted_at", "as_owner")
    search_fields = ("email", "token")
    readonly_fields = ("token", "created_at", "updated_at", "accepted_at")


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "billing_period", "base_price", "price_per_user", "included_users", "capacity_min", "capacity_max", "is_active")
    list_filter = ("billing_period", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")


@admin.register(OrganizationSubscription)
class OrganizationSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "status", "price_override", "started_at")
    list_filter = ("status", "plan")
    search_fields = ("organization__name", "organization__slug", "plan__name", "plan__slug")
    readonly_fields = ("created_at", "updated_at", "started_at")
