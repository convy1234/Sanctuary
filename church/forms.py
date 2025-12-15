from django import forms

from .models import SubscriptionPlan


class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "name",
            "slug",
            "description",
            "billing_period",
            "base_price",
            "price_per_user",
            "included_users",
            "capacity_min",
            "capacity_max",
            "is_active",
        ]
