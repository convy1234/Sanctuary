# church/api_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import authenticate
from django.utils import timezone
from .models import Membership, Organization, Event, Sermon
from accounts.models import User




class MobileLoginView(APIView):
    """API view for mobile app login"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not email or not password:
            return Response(
                {'error': 'Email and password required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Authenticate user
        user = authenticate(request, username=email, password=password)
        
        if user is None:
            return Response(
                {'error': 'Invalid credentials'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        # Get user's organization memberships
        memberships = Membership.objects.filter(user=user).select_related('organization')
        organizations_data = []
        
        for membership in memberships:
            organizations_data.append({
                'id': str(membership.organization.id),
                'name': membership.organization.name,
                'role': membership.role,
            })
        
        return Response({
            'user': {
                'id': str(user.id),
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_staff': user.is_staff,
            },
            'organizations': organizations_data,
            'primary_organization': organizations_data[0] if organizations_data else None,
            'token': {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }
        }, status=status.HTTP_200_OK)


class UserProfileView(APIView):
    """Get current user profile"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        # Get user's organization memberships
        memberships = Membership.objects.filter(user=user).select_related('organization')
        organizations_data = []
        
        for membership in memberships:
            organizations_data.append({
                'id': str(membership.organization.id),
                'name': membership.organization.name,
                'role': membership.role,
            })
        
        return Response({
            'id': str(user.id),
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone': user.phone,
            'is_staff': user.is_staff,
            'is_active': user.is_active,
            'organizations': organizations_data,
            'primary_organization': organizations_data[0] if organizations_data else None,
        })


class MobileLogoutView(APIView):
    """Logout view for mobile app"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()  # If using token blacklisting
            
            return Response({
                'message': 'Successfully logged out'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


# Organization API views for mobile
class OrganizationListView(APIView):
    """List organizations the user belongs to"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        memberships = Membership.objects.filter(
            user=request.user
        ).select_related('organization')
        
        organizations = []
        for membership in memberships:
            org = membership.organization
            organizations.append({
                'id': str(org.id),
                'name': org.name,
                'description': org.description,
                'logo_url': org.logo.url if org.logo else None,
                'role': membership.role,
                'member_since': membership.created_at,
                'member_count': org.members.count(),
            })
        
        return Response(organizations)


class OrganizationDetailView(APIView):
    """Get organization details"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        try:
            # Check if user is a member of this organization
            membership = Membership.objects.get(
                user=request.user,
                organization_id=pk
            )
            
            organization = membership.organization
            
            # Get organization stats
            stats = {
                'total_members': organization.members.count(),
                'total_events': organization.events.count(),
                'total_sermons': organization.sermons.count(),
                'active_invites': organization.invites.filter(
                    accepted_at__isnull=True,
                    expires_at__gt=timezone.now()
                ).count(),
            }
            
            return Response({
                'id': str(organization.id),
                'name': organization.name,
                'description': organization.description,
                'address': organization.address,
                'phone': organization.phone,
                'email': organization.email,
                'website': organization.website,
                'logo_url': organization.logo.url if organization.logo else None,
                'stats': stats,
                'user_role': membership.role,
            })
            
        except Membership.DoesNotExist:
            return Response(
                {'error': 'You are not a member of this organization'},
                status=status.HTTP_403_FORBIDDEN
            )


# Add these Event and Sermon models if you don't have them
# Or adapt to your existing models

class EventListView(APIView):
    """Get events for an organization"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, organization_id):
        try:
            # Check if user is a member
            membership = Membership.objects.get(
                user=request.user,
                organization_id=organization_id
            )
            
            # Assuming you have an Event model
            # from .models import Event
            events = Event.objects.filter(
                organization_id=organization_id,
                start_date__gte=timezone.now()
            ).order_by('start_date')[:20]  # Limit to 20 upcoming events
            
            events_data = []
            for event in events:
                events_data.append({
                    'id': str(event.id),
                    'title': event.title,
                    'description': event.description,
                    'start_date': event.start_date,
                    'end_date': event.end_date,
                    'location': event.location,
                    'image_url': event.image.url if event.image else None,
                    'event_type': event.event_type,
                })
            
            return Response(events_data)
            
        except Membership.DoesNotExist:
            return Response(
                {'error': 'You are not a member of this organization'},
                status=status.HTTP_403_FORBIDDEN
            )


class SermonListView(APIView):
    """Get sermons for an organization"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, organization_id):
        try:
            # Check if user is a member
            membership = Membership.objects.get(
                user=request.user,
                organization_id=organization_id
            )
            
            # Assuming you have a Sermon model
            # from .models import Sermon
            sermons = Sermon.objects.filter(
                organization_id=organization_id
            ).order_by('-date')[:20]  # Latest 20 sermons
            
            sermons_data = []
            for sermon in sermons:
                sermons_data.append({
                    'id': str(sermon.id),
                    'title': sermon.title,
                    'preacher': sermon.preacher,
                    'date': sermon.date,
                    'description': sermon.description,
                    'audio_url': sermon.audio_file.url if sermon.audio_file else None,
                    'video_url': sermon.video_url,
                    'scripture': sermon.scripture,
                    'duration': sermon.duration,
                })
            
            return Response(sermons_data)
            
        except Membership.DoesNotExist:
            return Response(
                {'error': 'You are not a member of this organization'},
                status=status.HTTP_403_FORBIDDEN
            )