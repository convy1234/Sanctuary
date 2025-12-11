# sanctuary/accounts/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone  # ADD THIS IMPORT
from .forms import LoginForm, RegistrationForm

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    # Check for invite token in session
    invite_token = request.session.get('invite_token')
    invite = None
    if invite_token:
        try:
            from church.models import Invite
            invite = Invite.objects.get(token=invite_token)
            if not invite.is_valid():
                # Clear invalid token
                del request.session['invite_token']
                invite = None
        except Invite.DoesNotExist:
            del request.session['invite_token']
    
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            
            # If there's a valid invite token, automatically accept it
            if invite_token and invite:
                from church.models import Membership
                membership, created = Membership.objects.get_or_create(
                    user=user,
                    organization=invite.organization,
                    defaults={'role': invite.role}
                )
                
                # Update invite
                invite.accepted_at = timezone.now()  # This now works
                invite.used_by = user
                invite.save()
                
                messages.success(
                    request, 
                    f'Account created and you have joined {invite.organization.name}!'
                )
                # Clear the session token
                del request.session['invite_token']
            else:
                messages.success(request, 'Account created successfully!')
            
            return redirect('dashboard')
    else:
        form = RegistrationForm()
    
    return render(request, 'auth/register.html', {
        'form': form, 
        'has_invite': invite is not None,
        'invite_organization': invite.organization.name if invite else None
    })

# Also update the other functions in accounts/views.py if needed
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, email=email, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.email}!')
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()
    
    return render(request, 'auth/login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('home')

@login_required
def dashboard_view(request):
    """Main Dashboard - Shows all organizations user owns/manages"""
    
    # Get user's memberships
    memberships = Membership.objects.filter(user=request.user).select_related('organization')
    
    # Get organizations where user is owner/primary admin
    owned_organizations = memberships.filter(
        role='org_owner', 
        is_primary_admin=True
    )
    
    # Get organizations where user is admin (but not primary owner)
    admin_organizations = memberships.filter(
        role='admin'
    ).exclude(is_primary_admin=True)
    
    # Get other memberships (staff, member, etc.)
    other_memberships = memberships.exclude(
        role__in=['org_owner', 'admin']
    )
    
    # Get platform-wide stats for the user
    total_organizations = owned_organizations.count() + admin_organizations.count()
    total_members_across_all_orgs = 0
    total_invites_across_all_orgs = 0
    
    # Prepare organization data with recent invites
    owned_orgs_data = []
    for membership in owned_organizations:
        org = membership.organization
        recent_invites = org.invites.all().order_by('-created_at')[:3]
        
        org_data = {
            'membership': membership,
            'organization': org,
            'member_count': org.members.count(),
            'invite_count': org.invites.count(),
            'recent_invites': recent_invites,
        }
        owned_orgs_data.append(org_data)
        
        total_members_across_all_orgs += org.members.count()
        total_invites_across_all_orgs += org.invites.count()
    
    # Prepare admin organizations data
    admin_orgs_data = []
    for membership in admin_organizations:
        org = membership.organization
        org_data = {
            'membership': membership,
            'organization': org,
            'member_count': org.members.count(),
        }
        admin_orgs_data.append(org_data)
    
    # Prepare other memberships data
    other_memberships_data = []
    for membership in other_memberships:
        org = membership.organization
        org_data = {
            'membership': membership,
            'organization': org,
        }
        other_memberships_data.append(org_data)
    
    context = {
        'owned_orgs_data': owned_orgs_data,
        'admin_orgs_data': admin_orgs_data,
        'other_memberships_data': other_memberships_data,
        'total_organizations': total_organizations,
        'total_members_across_all_orgs': total_members_across_all_orgs,
        'total_invites_across_all_orgs': total_invites_across_all_orgs,
        'has_organizations': total_organizations > 0,
    }

    return render(request, 'organization/dashboard.html', context)

# sanctuary/accounts/views.py (add these)
from django.contrib.admin.views.decorators import staff_member_required
from church.models import Organization, OrganizationApplication, Payment, Invite, Membership
from django.db.models import Count, Sum
from datetime import datetime, timedelta

@staff_member_required
def admin_dashboard_view(request):
    """Advanced admin dashboard with analytics"""
    # Get date ranges
    today = timezone.now().date()
    last_week = today - timedelta(days=7)
    last_month = today - timedelta(days=30)
    
    # Statistics
    stats = {
        'total_organizations': Organization.objects.count(),
        'active_organizations': Organization.objects.annotate(
            member_count=Count('members')
        ).filter(member_count__gt=0).count(),
        'total_users': User.objects.count(),
        'total_payments': Payment.objects.count(),
        'revenue_total': Payment.objects.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or 0,
        'revenue_this_month': Payment.objects.filter(
            status='completed',
            paid_at__gte=last_month
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'pending_applications': OrganizationApplication.objects.filter(status='pending').count(),
        'active_invites': Invite.objects.filter(accepted_at__isnull=True).count(),
    }
    
    # Recent activity
    recent_organizations = Organization.objects.order_by('-created_at')[:5]
    recent_payments = Payment.objects.select_related('organization').order_by('-created_at')[:10]
    recent_applications = OrganizationApplication.objects.order_by('-applied_at')[:10]
    
    context = {
        'stats': stats,
        'recent_organizations': recent_organizations,
        'recent_payments': recent_payments,
        'recent_applications': recent_applications,
        'today': today,
    }
    
    return render(request, 'admin/dashboard.html', context)

@staff_member_required
def admin_organizations_view(request):
    """Admin view to manage all organizations"""
    organizations = Organization.objects.annotate(
        member_count=Count('members'),
        payment_count=Count('payments'),
        total_paid=Sum('payments__amount', filter=models.Q(payments__status='completed'))
    ).order_by('-created_at')
    
    context = {
        'organizations': organizations,
    }
    
    return render(request, 'admin/organizations.html', context)

@staff_member_required  
def admin_billing_view(request):
    """Admin billing and payment management"""
    payments = Payment.objects.select_related('organization').order_by('-created_at')
    
    # Summary stats
    summary = {
        'total_revenue': payments.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or 0,
        'pending_payments': payments.filter(status='pending').count(),
        'failed_payments': payments.filter(status='failed').count(),
    }
    
    context = {
        'payments': payments,
        'summary': summary,
    }
    
    return render(request, 'admin/billing.html', context)