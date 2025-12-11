# sanctuary/church/forms.py
from django import forms
from .models import OrganizationApplication

class OrganizationApplicationForm(forms.ModelForm):
    class Meta:
        model = OrganizationApplication
        fields = [
            'organization_name', 'contact_person', 'contact_email',
            'contact_phone', 'church_denomination', 'location', 'about'
        ]
        widgets = {
            'organization_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Church/Organization Name'
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your Name'
            }),
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email address'
            }),
            'contact_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone number'
            }),
            'church_denomination': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Denomination (optional)'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City, State'
            }),
            'about': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Tell us about your church...',
                'rows': 4
            }),
        }