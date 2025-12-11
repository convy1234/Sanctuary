# sanctuary/church/views.py
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from .models import (
    Invite, Organization, OrganizationApplication, 
    Membership, Payment
)
from .serializers import (
    InviteSerializer, InviteCreateSerializer, AcceptInviteSerializer,
    OrganizationApplicationSerializer, OrganizationCreateSerializer,
    OrganizationSerializer  # This was missing
)





# accounts/views.py - ADD THIS VIEW
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate

@api_view(['POST'])
@permission_classes([AllowAny])
def api_login_view(request):
    """Mobile login API - returns token"""
    email = request.data.get('email')
    password = request.data.get('password')
    
    user = authenticate(request, username=email, password=password)
    
    if user is not None:
        # Get or create token for mobile
        token, created = Token.objects.get_or_create(user=user)
        
        return Response({
            'token': token.key,
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
        })
    
    return Response({'error': 'Invalid credentials'}, status=400)


from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
# church/views.py - Update UserProfileView
class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        try:
            # Get user's organization memberships
            memberships = Membership.objects.filter(user=user).select_related('organization')
            organizations = []
            
            for membership in memberships:
                org = membership.organization
                organizations.append({
                    'id': str(org.id),
                    'name': org.name,
                    'slug': org.slug,  # Use actual field from your model
                    'role': membership.role,
                    'is_primary_admin': membership.is_primary_admin,
                    'member_since': membership.created_at.strftime('%Y-%m-%d') if membership.created_at else None,
                })
            
            # Determine primary role based on your Membership.ROLE_CHOICES
            roles = [m.role for m in memberships]
            primary_role = 'member'  # default
            
            # Check for admin roles based on your ROLE_CHOICES
            if 'org_owner' in roles or user.is_staff:
                primary_role = 'admin'
            elif 'admin' in roles:
                primary_role = 'admin'
            elif 'hod' in roles:  # Head of Department
                primary_role = 'hod'
            elif 'manager' in roles:
                primary_role = 'manager'
            elif 'staff' in roles:
                primary_role = 'staff'
            elif 'volunteer' in roles:
                primary_role = 'volunteer'
            elif 'viewer' in roles:
                primary_role = 'viewer'
            
            user_data = {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_staff': user.is_staff,
                'is_active': user.is_active,
                'primary_role': primary_role,
                'date_joined': user.date_joined.strftime('%Y-%m-%d') if user.date_joined else None,
            }
            
            # Add phone if exists in your User model
            if hasattr(user, 'phone') and user.phone:
                user_data['phone'] = user.phone
            
            return Response({
                'user': user_data,
                'organizations': organizations,
                'primary_organization': organizations[0] if organizations else None,
            })
            
        except Exception as e:
            # Log error
            import traceback
            print(f"Error in UserProfileView: {str(e)}")
            print(traceback.format_exc())
            
            # Return basic user info even if there's an error
            return Response({
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_staff': user.is_staff,
                    'is_active': user.is_active,
                    'primary_role': 'member',
                },
                'organizations': [],
                'error': str(e)
            }, status=200)




# Add this to church/views.py as well
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout_view(request):
    """Logout API for mobile app"""
    try:
        # Delete the token
        Token.objects.filter(user=request.user).delete()
        return Response({'message': 'Logged out successfully'})
    except Exception as e:
        return Response({'error': str(e)}, status=400)



class IsOrgAdmin(permissions.BasePermission):
    """
    Placeholder permission: allow only staff users for now.
    Replace with membership role check logic later.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff


def send_invite_email(invite: Invite):
    from django.conf import settings
    from django.core.mail import send_mail
    
    print(f"=== DEBUG: Sending invite email to {invite.email} ===")
    
    # Get the base URL from settings
    frontend_base = getattr(settings, "SITE_URL", "http://localhost:8000")
    
    # Build the correct link - use invites/accept/ as per your URL pattern
    link = f"{frontend_base.rstrip('/')}/invites/accept/?token={invite.token}"
    
    print(f"DEBUG: Email link: {link}")
    print(f"DEBUG: From email: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'Not set')}")

    subject = f"You've been invited to join {invite.organization.name} on Sanctuary"
    message = (
        f"Hello,\n\n"
        f"You have been invited by {invite.inviter} to join {invite.organization.name} as {invite.get_role_display()}.\n\n"
        f"Click the link to accept the invite and set your password:\n\n{link}\n\n"
        f"This link will expire on {invite.expires_at}.\n\n"
        "If you weren't expecting this, you can ignore this email.\n"
    )
    
    try:
        send_mail(
            subject=subject, 
            message=message, 
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None), 
            recipient_list=[invite.email], 
            fail_silently=False
        )
        print(f"=== DEBUG: Email sent successfully to {invite.email} ===")
        return True
    except Exception as e:
        print(f"=== DEBUG: Failed to send email to {invite.email}: {str(e)} ===")
        raise


class InviteCreateView(generics.CreateAPIView):
    serializer_class = InviteCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgAdmin]

    def perform_create(self, serializer):
        invite = serializer.save()
        send_invite_email(invite)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        invite_obj = Invite.objects.filter(token=serializer.instance.token).first()
        out = InviteSerializer(invite_obj, context={"request": request}).data
        return Response(out, status=status.HTTP_201_CREATED)


class AcceptInviteView(generics.GenericAPIView):
    serializer_class = AcceptInviteSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        user = result["user"]
        invite = result["invite"]
        
        # Create Membership for the user
        membership, created = Membership.objects.get_or_create(
            user=user,
            organization=invite.organization,
            defaults={'role': invite.role}
        )
        
        # Send welcome email
        self.send_welcome_email(user, invite.organization)
        
        return Response({
            "message": "Account created successfully",
            "user_email": user.email,
            "organization": invite.organization.name,
            "role": membership.role,
            "membership_id": str(membership.id)
        }, status=status.HTTP_201_CREATED)
    
    def send_welcome_email(self, user, organization):
        subject = f"Welcome to {organization.name} on {getattr(settings, 'PLATFORM_NAME', 'Sanctuary')}"
        message = f"""
        Hi {user.first_name or 'there'},
        
        Welcome to {organization.name} on {getattr(settings, 'PLATFORM_NAME', 'Sanctuary')}!
        
        Your account has been successfully created.
        You can now access the platform and contribute to your organization.
        
        Login: {getattr(settings, 'SITE_URL', 'http://localhost:3000')}/login/
        
        If you have any questions, please contact your organization administrator.
        
        Best regards,
        {getattr(settings, 'PLATFORM_NAME', 'Sanctuary')} Team
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[user.email],
            fail_silently=False
        )


class OrganizationApplicationView(generics.CreateAPIView):
    """Allow organizations to apply for an account"""
    serializer_class = OrganizationApplicationSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = serializer.save()
        
        # Send email to admin
        admin_subject = f"New Organization Application: {application.organization_name}"
        admin_message = f"""
        New organization application received:
        
        Organization: {application.organization_name}
        Contact: {application.contact_person}
        Email: {application.contact_email}
        Phone: {application.contact_phone}
        
        Log in to the admin panel to review this application.
        """
        
        admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@example.com')
        send_mail(
            subject=admin_subject,
            message=admin_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[admin_email],
            fail_silently=False
        )
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class OrganizationCreateView(generics.CreateAPIView):
    """Create organization after application is approved"""
    serializer_class = OrganizationCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgAdmin]
    
    def create(self, request, *args, **kwargs):
        # Check if there's a pending application
        application_id = request.data.get('application_id')
        if application_id:
            try:
                application = OrganizationApplication.objects.get(
                    id=application_id, 
                    status='pending'
                )
                # Update application status
                application.status = 'approved'
                application.reviewed_at = timezone.now()
                application.save()
                
                # Use organization name from application
                request.data['name'] = application.organization_name
                
                # Store contact email for later use
                request.data['_contact_email'] = application.contact_email
            except OrganizationApplication.DoesNotExist:
                pass
        
        response = super().create(request, *args, **kwargs)
        
        # If we have contact email, create an invite for them
        contact_email = request.data.get('_contact_email')
        if contact_email and response.status_code == 201:
            organization = Organization.objects.get(id=response.data['id'])
            
            # Create invite for the contact person
            invite = Invite.create_invite(
                email=contact_email,
                inviter=request.user,
                organization=organization,
                role='org_owner'
            )
            
            # Send invite email
            send_invite_email(invite)
            
            # Update response data
            response.data['invite_sent_to'] = contact_email
        
        return response





class SendPaymentLinkView(generics.GenericAPIView):
    """Send payment link to organization after approval"""
    permission_classes = [permissions.IsAuthenticated, IsOrgAdmin]
    
    def post(self, request, organization_id):
        try:
            organization = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            return Response(
                {"error": "Organization not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create payment record
        amount = getattr(settings, 'ORGANIZATION_REGISTRATION_FEE', 99.00)
        payment = Payment.objects.create(
            organization=organization,
            amount=amount,
            status='pending'
        )
        
        # Generate payment link
        payment_url = f"{getattr(settings, 'SITE_URL', 'http://localhost:3000')}/payment/{payment.id}/"
        
        # Send email with payment link
        subject = f"Complete Your Registration for {organization.name}"
        message = f"""
        Dear Administrator,
        
        Your organization application has been approved!
        
        Please complete your registration by making the payment of ${amount}.
        
        Click here to pay: {payment_url}
        
        After payment, you'll be able to set up your account and invite team members.
        
        Thank you,
        {getattr(settings, 'PLATFORM_NAME', 'Sanctuary')} Team
        """
        
        # Get the organization contact email (from the first member or application)
        try:
            member_email = organization.members.first().user.email
        except:
            # Try to find from OrganizationApplication
            try:
                application = OrganizationApplication.objects.filter(
                    organization_name=organization.name
                ).first()
                member_email = application.contact_email if application else None
            except:
                member_email = None
        
        if member_email:
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[member_email],
                fail_silently=False
            )
        
        return Response({
            "message": "Payment link sent",
            "payment_id": str(payment.id),
            "payment_url": payment_url,
            "amount": amount
        })


class PaymentWebhookView(generics.GenericAPIView):
    """Handle payment webhooks from payment provider"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        # This is a simplified example - implement based on your payment provider
        payment_id = request.data.get('payment_id')
        status = request.data.get('status')
        
        try:
            payment = Payment.objects.get(id=payment_id)
            payment.status = status
            payment.paid_at = timezone.now() if status == 'completed' else None
            payment.save()
            
            if status == 'completed':
                # Organization is now fully active
                self.send_welcome_email(payment.organization)
            
            return Response({"status": "updated"})
        except Payment.DoesNotExist:
            return Response({"error": "Payment not found"}, status=404)
    
    def send_welcome_email(self, organization):
        subject = f"Welcome to {getattr(settings, 'PLATFORM_NAME', 'Sanctuary')}!"
        message = f"""
        Congratulations!
        
        Your payment has been processed and your organization "{organization.name}" is now active.
        
        You can now:
        1. Log in to your account
        2. Customize your organization settings
        3. Invite team members
        4. Start using all platform features
        
        Login here: {getattr(settings, 'SITE_URL', 'http://localhost:3000')}/login/
        
        Thank you for choosing {getattr(settings, 'PLATFORM_NAME', 'Sanctuary')}!
        """
        
        # Send to all organization owners/admins
        owners = organization.members.filter(role__in=['org_owner', 'admin'])
        emails = [member.user.email for member in owners]
        
        if emails:
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=emails,
                fail_silently=False
            )


# sanctuary/church/views.py (add these view functions)
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import OrganizationApplicationForm

def organization_apply_view(request):
    if request.method == 'POST':
        form = OrganizationApplicationForm(request.POST)
        if form.is_valid():
            application = form.save()
            messages.success(
                request, 
                'Your application has been submitted! We will review it and contact you soon.'
            )
            return redirect('home')
    else:
        form = OrganizationApplicationForm()
    
    return render(request, 'organization/apply.html', {'form': form})

# sanctuary/church/views.py
def accept_invite_view(request):
    token = request.GET.get('token')
    
    if not token:
        messages.error(request, 'Invalid invitation link.')
        return redirect('home')
    
    try:
        invite = Invite.objects.get(token=token)
        
        if not invite.is_valid():
            messages.error(request, 'This invitation has expired or has already been used.')
            return redirect('home')
        
        if request.user.is_authenticated:
            # User is logged in
            if request.method == 'POST':
                # Create or update membership
                membership, created = Membership.objects.get_or_create(
                    user=request.user,
                    organization=invite.organization,
                    defaults={'role': invite.role}
                )
                
                # If membership already existed, update role if needed
                if not created:
                    membership.role = invite.role
                    membership.save()
                
                # Update invite
                invite.accepted_at = timezone.now()
                invite.used_by = request.user
                invite.save()
                
                messages.success(
                    request, 
                    f'You have successfully joined {invite.organization.name}!'
                )
                return redirect('dashboard')
            
            # GET request - show accept page
            return render(request, 'invites/accept.html', {'invite': invite})
        else:
            # User not logged in, redirect to register with token
            request.session['invite_token'] = token
            messages.info(request, 'Please create an account or login to accept the invitation.')
            return redirect('register')
            
    except Invite.DoesNotExist:
        messages.error(request, 'Invalid invitation link.')
        return redirect('home')


# sanctuary/church/views.py (add this)
@login_required
def send_invite_view(request, organization_id):
    """View for organization owners to send invites"""
    organization = get_object_or_404(Organization, id=organization_id)
    
    # Check if user is owner/admin of this organization
    membership = get_object_or_404(
        Membership, 
        user=request.user, 
        organization=organization
    )
    
    if membership.role not in ['org_owner', 'admin']:
        messages.error(request, "You don't have permission to invite members.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        email = request.POST.get('email')
        role = request.POST.get('role')
        
        if not email or not role:
            messages.error(request, "Email and role are required.")
            return redirect('dashboard')
        
        # Create invite
        try:
            invite = Invite.create_invite(
                email=email,
                inviter=request.user,
                organization=organization,
                role=role
            )
            
            # Send email
            send_invite_email(invite)
            
            messages.success(request, f"Invite sent to {email}")
        except Exception as e:
            messages.error(request, f"Failed to send invite: {str(e)}")
        
        return redirect('dashboard')
    
    return render(request, 'organization/send_invite.html', {
        'organization': organization
    })




# sanctuary/church/views.py (add this)
@login_required
def organization_dashboard_view(request, organization_id):
    """Individual Organization Dashboard"""
    
    # Get the organization
    organization = get_object_or_404(Organization, id=organization_id)
    
    # Check if user has access to this organization
    membership = get_object_or_404(
        Membership,
        user=request.user,
        organization=organization
    )
    
    # Get organization statistics
    org_stats = {
        'total_members': organization.members.count(),
        'active_invites': organization.invites.filter(
            accepted_at__isnull=True,
            expires_at__gt=timezone.now()
        ).count(),
        'total_payments': organization.payments.count(),
        'completed_payments': organization.payments.filter(status='completed').count(),
        'pending_payments': organization.payments.filter(status='pending').count(),
    }
    
    # Get recent invites
    recent_invites = organization.invites.order_by('-created_at')[:5]
    
    # Get recent payments
    recent_payments = organization.payments.order_by('-created_at')[:5]
    
    # Get all members
    members = organization.members.select_related('user').order_by('-created_at')[:10]
    
    # Get user's organizations for sidebar dropdown
    user_organizations = Organization.objects.filter(
        members__user=request.user
    ).distinct()
    
    context = {
        'organization': organization,
        'membership': membership,
        'org_stats': org_stats,
        'recent_invites': recent_invites,
        'recent_payments': recent_payments,
        'members': members,
        'user_organizations': user_organizations,
    }
    
    return render(request, 'dashboard/main.html', context)