import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Subquery, OuterRef
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from member.models import Member
from .models import Channel, ChannelMembership, DirectMessage, Message, ChatFile, ChannelJoinRequest

User = get_user_model()

channel_layer = get_channel_layer()


def get_user_organization(user):
    if hasattr(user, 'organization') and user.organization:
        return user.organization
    
    # fallback if user belongs via profile or membership
    if hasattr(user, 'profile') and hasattr(user.profile, 'organization'):
        return user.profile.organization
    
    return None


def channel_group_name(channel_id):
    return f"chat.channel.{channel_id}"


def dm_group_name(dm_id):
    return f"chat.dm.{dm_id}"


def display_name_for(user):
    if hasattr(user, "member_profile") and user.member_profile:
        return user.member_profile.full_name
    return user.email or user.username


# chat/views.py (update the broadcast_message function)

def broadcast_message(thread_type, thread_id, msg_obj):
    """Send a message payload to websocket subscribers."""
    
    # Get sender info
    sender_name = display_name_for(msg_obj.sender)
    sender_avatar = None
    
    # Try to get avatar
    try:
        if hasattr(msg_obj.sender, 'member_profile') and msg_obj.sender.member_profile.photo:
            # You'll need request context here, so we'll handle it in the consumer
            pass
    except AttributeError:
        pass
    
    payload = {
        "id": str(msg_obj.id),
        "content": msg_obj.content,
        "sender": {
            "id": str(msg_obj.sender.uid),
            "name": sender_name,
            "avatar": sender_avatar,
        },
        "created_at": msg_obj.created_at.isoformat(),
        "created_at_timestamp": int(msg_obj.created_at.timestamp() * 1000),
        "reply_to": str(msg_obj.reply_to.id) if msg_obj.reply_to else None,
    }
    
    group_name = f"{thread_type}_{thread_id}"
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "chat_message",
            "message": payload,
        }
    )





@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def chat_home_api_view(request):
    """
    Mobile API for chat home - matches your existing UI structure
    Returns data in the exact format your React Native app expects
    """
    user = request.user
    
    # Get user's organization
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get user display name (with fallbacks)
    user_display_name = None
    user_avatar = None
    
    # Try to get from member profile first
    try:
        member_profile = user.member_profile
        user_display_name = member_profile.full_name
        user_avatar = member_profile.photo.url if member_profile.photo else None
    except AttributeError:
        # Fallback 1: Use first_name + last_name from User model
        if user.first_name:
            user_display_name = f"{user.first_name} {user.last_name}".strip()
            if not user_display_name:
                user_display_name = user.first_name
        # Fallback 2: Use email prefix
        if not user_display_name:
            user_display_name = user.email.split('@')[0]
    
    print(f"🔍 [DEBUG] User display name: {user_display_name}")
    print(f"🔍 [DEBUG] User organization: {organization.name}")
    
    # ========== GET CHANNELS ==========
    channels = Channel.objects.filter(
        organization=organization,
        memberships__user=user
    ).annotate(
        unread_count=Subquery(
            Message.objects.filter(
                channel=OuterRef('pk'),
                created_at__gt=Subquery(
                    ChannelMembership.objects.filter(
                        channel=OuterRef('pk'),
                        user=user
                    ).values('last_read_at')[:1]
                )
            ).values('channel').annotate(count=Count('pk')).values('count')[:1]
        ) or 0,
        
        latest_message_content=Subquery(
            Message.objects.filter(
                channel=OuterRef('pk')
            ).order_by('-created_at').values('content')[:1]
        ),
        
        latest_message_time=Subquery(
            Message.objects.filter(
                channel=OuterRef('pk')
            ).order_by('-created_at').values('created_at')[:1]
        ),
        
        member_count=Count('memberships', distinct=True),
    ).order_by('name')
    
    channels_data = []
    for channel in channels:
        latest_preview = "No messages yet"
        if channel.latest_message_content:
            latest_preview = channel.latest_message_content[:100]
        
        channels_data.append({
            'id': str(channel.id),
            'name': channel.name,
            'display_name': channel.name.replace('-', ' ').title(),
            'description': channel.description or '',
            'unread_count': channel.unread_count or 0,
            'last_message': latest_preview,
            'last_message_time': channel.latest_message_time.isoformat() if channel.latest_message_time else None,
            'last_message_sender': None,
            'is_public': channel.is_public,
            'member_count': channel.member_count or 0,
        })
    
    print(f"✅ Found {len(channels_data)} channels for user")
    
    # ========== GET DIRECT MESSAGES ==========
    dm_threads = DirectMessage.objects.filter(
        organization=organization,
        participants=user
    ).annotate(
        unread_count=Subquery(
            Message.objects.filter(
                direct_message=OuterRef('pk'),
                created_at__gt=Subquery(
                    Message.objects.filter(
                        direct_message=OuterRef('pk'),
                        read_by=user
                    ).order_by('-created_at').values('created_at')[:1]
                )
            ).values('direct_message').annotate(count=Count('pk')).values('count')[:1]
        ) or 0,
        
        latest_message_content=Subquery(
            Message.objects.filter(
                direct_message=OuterRef('pk')
            ).order_by('-created_at').values('content')[:1]
        ),
        
        latest_message_time=Subquery(
            Message.objects.filter(
                direct_message=OuterRef('pk')
            ).order_by('-created_at').values('created_at')[:1]
        ),
    ).order_by('-updated_at')
    
    dms_data = []
    for dm in dm_threads:
        # Check if it's a group DM
        # Use hasattr to check if is_group exists, default to False
        is_group = getattr(dm, 'is_group', False)
        
        if not is_group:
            other_user = dm.participants.exclude(uid=user.uid).first()
            if not other_user:
                continue
            
            # Get other user's display name
            other_display_name = other_user.email.split('@')[0]
            other_avatar = None
            
            try:
                other_member = other_user.member_profile
                if other_member:
                    other_display_name = other_member.full_name
                    if other_member.photo:
                        other_avatar = request.build_absolute_uri(other_member.photo.url)
            except AttributeError:
                pass
            
            dms_data.append({
                'id': str(dm.id),
                'name': other_display_name,
                'avatar': other_avatar,
                'latest': dm.latest_message_content or "No messages yet",
                'updatedAt': int(dm.latest_message_time.timestamp() * 1000) if dm.latest_message_time else int(timezone.now().timestamp() * 1000),
                'unread': dm.unread_count or 0,
                'is_group': False,
                'user_id': str(other_user.uid),
                'user_name': other_display_name,
                'user_avatar': other_avatar,
            })
        else:
            # Handle group DMs if you have the field
            group_name = getattr(dm, 'group_name', f"Group ({dm.participants.count()})")
            dms_data.append({
                'id': str(dm.id),
                'name': group_name,
                'avatar': None,
                'latest': dm.latest_message_content or "No messages yet",
                'updatedAt': int(dm.latest_message_time.timestamp() * 1000) if dm.latest_message_time else int(timezone.now().timestamp() * 1000),
                'unread': dm.unread_count or 0,
                'is_group': True,
                'group_name': group_name,
            })
    
    print(f"✅ Found {len(dms_data)} DMs for user")
    
    # ========== GET OTHER USERS IN ORGANIZATION ==========
    # Get all ACTIVE users in the same organization (excluding current user)
    org_users = User.objects.filter(
        organization=organization,
        is_active=True
    ).exclude(uid=user.uid)
    
    print(f"🔍 Total users in org '{organization.name}': {User.objects.filter(organization=organization).count()}")
    print(f"🔍 Other users (excluding current): {org_users.count()}")
    
    members_data = []
    for org_user in org_users:
        # Get display name
        display_name = org_user.email.split('@')[0]
        avatar = None
        
        # Try to get from member profile
        try:
            member_profile = org_user.member_profile
            if member_profile:
                display_name = member_profile.full_name
                if member_profile.photo:
                    avatar = request.build_absolute_uri(member_profile.photo.url)
        except AttributeError:
            pass
        
        # Get role
        role = 'Member'
        if org_user.is_pastor:
            role = 'Pastor'
        elif org_user.is_hod:
            role = 'Head of Department'
        elif org_user.is_admin:
            role = 'Admin'
        elif org_user.is_owner:
            role = 'Owner'
        elif org_user.is_worker:
            role = 'Worker'
        elif org_user.is_volunteer:
            role = 'Volunteer'
        
        # Fallback to user's first_name + last_name
        if display_name == org_user.email.split('@')[0]:
            if org_user.first_name:
                name_parts = [org_user.first_name.strip()]
                if org_user.last_name and org_user.last_name.strip() and org_user.last_name != org_user.email:
                    name_parts.append(org_user.last_name.strip())
                name = " ".join(name_parts).strip()
                if name:
                    display_name = name
        
        members_data.append({
            'id': str(org_user.uid),
            'name': display_name,
            'avatar': avatar,
            'role': role,
            'email': org_user.email,
        })
    
    print(f"✅ Prepared {len(members_data)} users for chat list")
    
    # Calculate total unread
    total_unread = sum([c['unread_count'] for c in channels_data]) + sum([d['unread'] for d in dms_data])
    
    # Build response
    response_data = {
        'success': True,
        'channels': channels_data,
        'directMessages': dms_data,
        'organizationMembers': members_data,
        'total_unread': total_unread,
        'user': {
            'id': str(user.uid),
            'name': user_display_name,
            'avatar': request.build_absolute_uri(user_avatar) if user_avatar else None,
            'organization_name': organization.name,
        },
    }
    
    return Response(response_data)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def channel_create_api_view(request):
    """
    Create a new channel - FIXED VERSION
    """
    user = request.user
    organization = get_user_organization(user)
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    name = request.data.get('name', '').strip().lower()
    description = request.data.get('description', '').strip()
    is_public = request.data.get('is_public', True)
    is_read_only = request.data.get('is_read_only', False)
    
    if not name:
        return Response(
            {'success': False, 'error': 'Channel name is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate name format
    name = name.replace(' ', '-')
    
    # Check if channel already exists
    if Channel.objects.filter(organization=organization, name=name).exists():
        return Response(
            {'success': False, 'error': f'Channel #{name} already exists'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Create channel
        channel = Channel.objects.create(
            organization=organization,
            name=name,
            description=description,
            is_public=is_public,
            is_read_only=is_read_only,
            created_by=user
        )
        
        # Auto-join creator
        ChannelMembership.objects.create(
            channel=channel,
            user=user
        )
        
        # If public, auto-join all organization members
        if is_public:
            # Get all USERS in the organization (not Members)
            org_users = User.objects.filter(organization=organization, is_active=True)
            for org_user in org_users:
                ChannelMembership.objects.get_or_create(
                    channel=channel,
                    user=org_user
                )
        
        # Get creator name for welcome message
        creator_name = user.email.split('@')[0]
        try:
            if hasattr(user, 'member_profile') and user.member_profile:
                creator_name = user.member_profile.full_name
        except AttributeError:
            pass
        
        # Fallback to user's first_name + last_name
        if creator_name == user.email.split('@')[0]:
            if user.first_name:
                name_parts = [user.first_name.strip()]
                if user.last_name and user.last_name.strip() and user.last_name != user.email:
                    name_parts.append(user.last_name.strip())
                name = " ".join(name_parts).strip()
                if name:
                    creator_name = name
        
        # Send welcome message
        Message.objects.create(
            channel=channel,
            sender=user,
            content=f"Welcome to #{channel.name}! This channel was created by {creator_name}."
        )
        
        return Response({
            'success': True,
            'message': f'Channel #{channel.name} created successfully',
            'channel': {
                'id': str(channel.id),
                'name': channel.name,
                'display_name': channel.name.replace('-', ' ').title(),
                'description': channel.description,
                'is_public': channel.is_public,
                'is_read_only': channel.is_read_only,
                'created_at': channel.created_at.isoformat(),
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def channel_detail_api_view(request, channel_id):
    """Get channel details and messages"""
    try:
        channel = Channel.objects.get(id=channel_id, organization=request.user.organization)
    except Channel.DoesNotExist:
        return Response({'success': False, 'error': 'Channel not found'}, status=404)
    
    # Check if user is member
    if not ChannelMembership.objects.filter(channel=channel, user=request.user).exists():
        return Response({'success': False, 'error': 'Not a member of this channel'}, status=403)
    
    # Get paginated messages
    page = int(request.query_params.get('page', 1))
    limit = int(request.query_params.get('limit', 50))
    offset = (page - 1) * limit
    
    messages_qs = Message.objects.filter(channel=channel).select_related('sender').order_by('-created_at')
    total_messages = messages_qs.count()
    messages = messages_qs[offset:offset + limit]
    
    # Format messages
    messages_data = []
    for msg in messages:
        # Get sender display name
        sender_name = msg.sender.email.split('@')[0]
        sender_avatar = None
        
        try:
            member_profile = msg.sender.member_profile
            if member_profile:
                sender_name = member_profile.full_name
                if member_profile.photo:
                    sender_avatar = request.build_absolute_uri(member_profile.photo.url)
        except AttributeError:
            pass
        
        messages_data.append({
            'id': str(msg.id),
            'content': msg.content,
            'sender': {
                'id': str(msg.sender.uid),
                'name': sender_name,
                'avatar': sender_avatar,
            },
            'created_at': msg.created_at.isoformat(),
            'created_at_timestamp': int(msg.created_at.timestamp() * 1000),
        })
    
    # Get channel members (Users who are members)
    channel_memberships = ChannelMembership.objects.filter(channel=channel).select_related('user')
    members_data = []
    
    for membership in channel_memberships:
        member_user = membership.user
        
        # Get display name
        display_name = member_user.email.split('@')[0]
        avatar = None
        
        try:
            member_profile = member_user.member_profile
            if member_profile:
                display_name = member_profile.full_name
                if member_profile.photo:
                    avatar = request.build_absolute_uri(member_profile.photo.url)
        except AttributeError:
            pass
        
        members_data.append({
            'id': str(member_user.uid),
            'name': display_name,
            'avatar': avatar,
            'joined_at': membership.joined_at.isoformat(),
        })
    
    # Get channel info
    channel_data = {
        'id': str(channel.id),
        'name': channel.name,
        'display_name': channel.name.replace('-', ' ').title(),
        'description': channel.description or '',
        'is_public': channel.is_public,
        'is_read_only': channel.is_read_only,
        'member_count': len(members_data),
        'created_by': None,
        'created_at': channel.created_at.isoformat(),
    }
    
    # Get creator info if available
    if channel.created_by:
        creator_name = channel.created_by.email.split('@')[0]
        try:
            creator_profile = channel.created_by.member_profile
            if creator_profile:
                creator_name = creator_profile.full_name
        except AttributeError:
            pass
        channel_data['created_by'] = creator_name
    
    return Response({
        'success': True,
        'channel': channel_data,
        'messages': messages_data,
        'members': members_data,
        'pagination': {
            'page': page,
            'limit': limit,
            'has_more': (offset + limit) < total_messages,
            'total_messages': total_messages,
        },
        'permissions': {
            'can_post': not channel.is_read_only,
            'can_manage': request.user.is_admin or request.user.is_owner,
        }
    })


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def channel_join_api_view(request, channel_id):
    """Join a channel (auto-join if public, otherwise create a join request)."""
    user = request.user
    organization = get_user_organization(request.user)
    if not organization:
        return Response({"success": False, "error": "No organization assigned"}, status=status.HTTP_400_BAD_REQUEST)

    channel = get_object_or_404(Channel, id=channel_id, organization=organization)

    if channel.is_public:
        ChannelMembership.objects.get_or_create(channel=channel, user=user)
        return Response({"success": True, "message": "Joined channel", "channel": str(channel.id)})

    req, created_req = ChannelJoinRequest.objects.get_or_create(channel=channel, user=user)
    if not created_req and req.status == "approved":
        ChannelMembership.objects.get_or_create(channel=channel, user=user)
        return Response({"success": True, "message": "Already approved"})
    if not created_req and req.status == "pending":
        return Response({"success": True, "message": "Already requested", "status": req.status})

    req.status = "pending"
    req.decided_at = None
    req.decided_by = None
    req.save()
    return Response({"success": True, "message": "Join request sent", "status": req.status})


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def channel_leave_api_view(request, channel_id):
    """Leave a channel."""
    user = request.user
    organization = get_user_organization(user)
    if not organization:
        return Response({"success": False, "error": "No organization assigned"}, status=status.HTTP_400_BAD_REQUEST)

    channel = get_object_or_404(Channel, id=channel_id, organization=organization)
    ChannelMembership.objects.filter(channel=channel, user=user).delete()
    return Response({"success": True, "message": "Left channel"})


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def channel_join_approve_api_view(request, request_id):
    """Approve a join request (channel creator/staff)."""
    user = request.user
    join_request = get_object_or_404(ChannelJoinRequest, id=request_id)

    if not (user.is_staff or user.is_superuser or join_request.channel.created_by == user):
        return Response({"success": False, "error": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)

    join_request.status = "approved"
    join_request.decided_at = timezone.now()
    join_request.decided_by = user
    join_request.save()

    ChannelMembership.objects.get_or_create(channel=join_request.channel, user=join_request.user)
    return Response({"success": True, "message": "Request approved"})


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def send_channel_message_api_view(request, channel_id):
    """
    Send message to a channel
    """
    user = request.user
    organization = get_user_organization(user)
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        channel = Channel.objects.get(id=channel_id, organization=organization)
    except Channel.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Channel not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions
    if channel.is_read_only:
        if not (user.is_staff or user.is_superuser):
            return Response(
                {'success': False, 'error': 'This channel is read-only'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    
    # Check if user is member
    if not channel.is_public:
        if not ChannelMembership.objects.filter(channel=channel, user=user).exists():
            return Response(
                {'success': False, 'error': 'You are not a member of this channel'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    
    content = request.data.get('content', '').strip()
    if not content:
        return Response(
            {'success': False, 'error': 'Message content is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Create message
        message = Message.objects.create(
            channel=channel,
            sender=user,
            content=content
        )

        # Ensure membership record exists for tracking
        ChannelMembership.objects.get_or_create(channel=channel, user=user)

        # Mark as read by sender
        message.read_by.add(user)

        # Broadcast to websocket listeners
        broadcast_message("channel", channel.id, message)
        
        # Get sender info for response
        try:
            sender_info = {
                'id': str(user.uid),
                'name': user.member_profile.full_name,
                'avatar': request.build_absolute_uri(user.member_profile.photo.url) if user.member_profile.photo else None,
                'role': user.member_profile.family_role,
            }
        except AttributeError:
            sender_info = {
                'id': str(user.uid),
                'name': user.username,
                'avatar': None,
            }
        
        return Response({
            'success': True,
            'message': 'Message sent successfully',
            'message_id': str(message.id),
            'message': {
                'id': str(message.id),
                'content': message.content,
                'sender': sender_info,
                'created_at': message.created_at.isoformat(),
                'created_at_timestamp': int(message.created_at.timestamp() * 1000),
            },
            'target': {
                'type': 'channel',
                'id': str(channel.id),
                'name': channel.name,
            },
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )









@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def start_dm_api_view(request):
    """
    Start a new DM conversation - FIXED VERSION
    """
    user = request.user
    
    # Get user's organization from User model (same as chat_home_api_view)
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    target_user_id = request.data.get('user_id')
    if not target_user_id:
        return Response(
            {'success': False, 'error': 'User ID is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Use uid to find the user
        target_user = User.objects.get(uid=target_user_id)
    except User.DoesNotExist:
        return Response(
            {'success': False, 'error': 'User not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # SIMPLE CHECK: Just check if target_user has the same organization
    # NO MEMBER PROFILE CHECK NEEDED!
    if target_user.organization != organization:
        return Response(
            {'success': False, 'error': 'User is not in your organization'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get or create DM thread
    dm_thread = DirectMessage.get_or_create_dm(user, target_user, organization)
    
    # Get other user display name (SAME LOGIC AS chat_home_api_view)
    display_name = target_user.email.split('@')[0]
    avatar = None
    
    # Try to get from member profile
    try:
        member_profile = target_user.member_profile
        if member_profile:
            display_name = member_profile.full_name
            if member_profile.photo:
                avatar = request.build_absolute_uri(member_profile.photo.url)
    except AttributeError:
        pass  # No member profile, that's OK!
    
    # Get role (same as chat_home_api_view)
    role = 'Member'
    if target_user.is_pastor:
        role = 'Pastor'
    elif target_user.is_hod:
        role = 'Head of Department'
    elif target_user.is_admin:
        role = 'Admin'
    elif target_user.is_owner:
        role = 'Owner'
    elif target_user.is_worker:
        role = 'Worker'
    elif target_user.is_volunteer:
        role = 'Volunteer'
    
    # Fallback to user's first_name + last_name
    if display_name == target_user.email.split('@')[0]:
        if target_user.first_name:
            name_parts = [target_user.first_name.strip()]
            if target_user.last_name and target_user.last_name.strip() and target_user.last_name != target_user.email:
                name_parts.append(target_user.last_name.strip())
            name = " ".join(name_parts).strip()
            if name:
                display_name = name
    
    other_user_info = {
        'id': str(target_user.uid),
        'name': display_name,
        'avatar': avatar,
        'role': role,
        'email': target_user.email,
    }
    
    return Response({
        'success': True,
        'message': 'Direct message thread created',
        'dm_thread': {
            'id': str(dm_thread.id),
            'created_at': dm_thread.created_at.isoformat(),
            'updated_at': dm_thread.updated_at.isoformat(),
        },
        'other_user': other_user_info,
    })


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def dm_detail_api_view(request, dm_id):
    """
    Get DM thread details and messages - FIXED VERSION
    """
    user = request.user
    
    # Get user's organization from User model
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        dm_thread = DirectMessage.objects.get(id=dm_id, organization=organization)
    except DirectMessage.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Conversation not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user is participant
    if not dm_thread.participants.filter(uid=user.uid).exists():
        return Response(
            {'success': False, 'error': 'You are not a participant in this conversation'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get messages with pagination
    page = int(request.query_params.get('page', 1))
    limit = int(request.query_params.get('limit', 50))
    offset = (page - 1) * limit
    
    # Get messages (oldest first for chat UI)
    messages = Message.objects.filter(
        direct_message=dm_thread
    ).select_related('sender').order_by('created_at')[offset:offset + limit]
    
    # Get other participant(s)
    other_participants = dm_thread.participants.exclude(uid=user.uid)
    participants_data = []
    
    for participant in other_participants:
        # Get display name
        display_name = participant.email.split('@')[0]
        avatar = None
        
        # Try to get from member profile
        try:
            member_profile = participant.member_profile
            if member_profile:
                display_name = member_profile.full_name
                if member_profile.photo:
                    avatar = request.build_absolute_uri(member_profile.photo.url)
        except AttributeError:
            pass
        
        # Get role
        role = 'Member'
        if participant.is_pastor:
            role = 'Pastor'
        elif participant.is_hod:
            role = 'Head of Department'
        elif participant.is_admin:
            role = 'Admin'
        elif participant.is_owner:
            role = 'Owner'
        elif participant.is_worker:
            role = 'Worker'
        elif participant.is_volunteer:
            role = 'Volunteer'
        
        # Fallback to user's first_name + last_name
        if display_name == participant.email.split('@')[0]:
            if participant.first_name:
                name_parts = [participant.first_name.strip()]
                if participant.last_name and participant.last_name.strip() and participant.last_name != participant.email:
                    name_parts.append(participant.last_name.strip())
                name = " ".join(name_parts).strip()
                if name:
                    display_name = name
        
        participants_data.append({
            'id': str(participant.uid),
            'name': display_name,
            'avatar': avatar,
            'role': role,
            'email': participant.email,
        })
    
    # Format messages
    messages_data = []
    for msg in messages:
        # Get sender info with fallbacks
        sender_info = None
        if msg.sender:
            # Get display name
            display_name = msg.sender.email.split('@')[0]
            avatar = None
            
            # Try to get from member profile
            try:
                member_profile = msg.sender.member_profile
                if member_profile:
                    display_name = member_profile.full_name
                    if member_profile.photo:
                        avatar = request.build_absolute_uri(member_profile.photo.url)
            except AttributeError:
                pass
            
            # Get role
            role = 'Member'
            if msg.sender.is_pastor:
                role = 'Pastor'
            elif msg.sender.is_hod:
                role = 'Head of Department'
            elif msg.sender.is_admin:
                role = 'Admin'
            elif msg.sender.is_owner:
                role = 'Owner'
            elif msg.sender.is_worker:
                role = 'Worker'
            elif msg.sender.is_volunteer:
                role = 'Volunteer'
            
            # Fallback to user's first_name + last_name
            if display_name == msg.sender.email.split('@')[0]:
                if msg.sender.first_name:
                    name_parts = [msg.sender.first_name.strip()]
                    if msg.sender.last_name and msg.sender.last_name.strip() and msg.sender.last_name != msg.sender.email:
                        name_parts.append(msg.sender.last_name.strip())
                    name = " ".join(name_parts).strip()
                    if name:
                        display_name = name
            
            sender_info = {
                'id': str(msg.sender.uid),
                'name': display_name,
                'avatar': avatar,
                'role': role,
            }
        
        messages_data.append({
            'id': str(msg.id),
            'content': msg.content,
            'sender': sender_info,
            'created_at': msg.created_at.isoformat(),
            'created_at_timestamp': int(msg.created_at.timestamp() * 1000),
        })
    
    # Get thread info
    # Check if is_group exists, default to False
    is_group = getattr(dm_thread, 'is_group', False)
    
    thread_info = {
        'id': str(dm_thread.id),
        'is_group': is_group,
        'participants': participants_data,
        'created_at': dm_thread.created_at.isoformat(),
        'updated_at': dm_thread.updated_at.isoformat(),
    }
    
    return Response({
        'success': True,
        'dm_thread': thread_info,
        'messages': messages_data,
        'pagination': {
            'page': page,
            'limit': limit,
            'has_more': Message.objects.filter(direct_message=dm_thread).count() > (offset + limit),
            'total_messages': Message.objects.filter(direct_message=dm_thread).count(),
        }
    })

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def send_dm_message_api_view(request, dm_id):
    """
    Send message to a DM thread - FIXED VERSION
    """
    user = request.user
    
    # Get user's organization from User model
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        dm_thread = DirectMessage.objects.get(id=dm_id, organization=organization)
    except DirectMessage.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Conversation not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user is participant
    if not dm_thread.participants.filter(uid=user.uid).exists():
        return Response(
            {'success': False, 'error': 'You are not a participant in this conversation'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    content = request.data.get('content', '').strip()
    if not content:
        return Response(
            {'success': False, 'error': 'Message content is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Create message
        message = Message.objects.create(
            direct_message=dm_thread,
            sender=user,
            content=content
        )

        # Mark as read by sender
        message.read_by.add(user)
        broadcast_message("dm", dm_thread.id, message)
        
        # Get sender info with fallbacks (same logic as dm_detail_api_view)
        display_name = user.email.split('@')[0]
        avatar = None
        
        # Try to get from member profile
        try:
            member_profile = user.member_profile
            if member_profile:
                display_name = member_profile.full_name
                if member_profile.photo:
                    avatar = request.build_absolute_uri(member_profile.photo.url)
        except AttributeError:
            pass  # No member profile, that's OK!
        
        # Get role
        role = 'Member'
        if user.is_pastor:
            role = 'Pastor'
        elif user.is_hod:
            role = 'Head of Department'
        elif user.is_admin:
            role = 'Admin'
        elif user.is_owner:
            role = 'Owner'
        elif user.is_worker:
            role = 'Worker'
        elif user.is_volunteer:
            role = 'Volunteer'
        
        # Fallback to user's first_name + last_name
        if display_name == user.email.split('@')[0]:
            if user.first_name:
                name_parts = [user.first_name.strip()]
                if user.last_name and user.last_name.strip() and user.last_name != user.email:
                    name_parts.append(user.last_name.strip())
                name = " ".join(name_parts).strip()
                if name:
                    display_name = name
        
        sender_info = {
            'id': str(user.uid),
            'name': display_name,
            'avatar': avatar,
            'role': role,
        }
        
        return Response({
            'success': True,
            'message': 'Message sent successfully',
            'message_id': str(message.id),
            'message': {
                'id': str(message.id),
                'content': message.content,
                'sender': sender_info,
                'created_at': message.created_at.isoformat(),
                'created_at_timestamp': int(message.created_at.timestamp() * 1000),
            },
            'target': {
                'type': 'dm',
                'id': str(dm_thread.id),
                'is_group': False,
            },
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_messages_read_api_view(request):
    """
    Mark messages as read
    """
    user = request.user
    organization = get_user_organization(user)
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    message_type = request.data.get('type')  # 'channel' or 'dm'
    target_id = request.data.get('target_id')
    
    if not message_type or not target_id:
        return Response(
            {'success': False, 'error': 'Type and target ID are required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        if message_type == 'channel':
            channel = Channel.objects.get(id=target_id, organization=organization)
            
            # Update last read time
            membership, _ = ChannelMembership.objects.get_or_create(
                channel=channel,
                user=user
            )
            membership.last_read_at = timezone.now()
            membership.save()
            
        elif message_type == 'dm':
            dm_thread = DirectMessage.objects.get(id=target_id, organization=organization)
            
            # Mark all messages in DM as read for this user
            messages = Message.objects.filter(direct_message=dm_thread)
            for message in messages:
                message.read_by.add(user)
        
        else:
            return Response(
                {'success': False, 'error': 'Invalid type. Use "channel" or "dm"'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({
            'success': True,
            'message': f'Messages marked as read for {message_type}',
        })
        
    except (Channel.DoesNotExist, DirectMessage.DoesNotExist):
        return Response(
            {'success': False, 'error': 'Target not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_message_api_view(request, message_id):
    """
    Delete a message
    """
    user = request.user
    organization = get_user_organization(user)
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        message = Message.objects.get(id=message_id)
        
        # Check if user owns the message or is admin
        if message.sender != user and not (user.is_staff or user.is_superuser):
            return Response(
                {'success': False, 'error': 'You can only delete your own messages'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        message.delete()
        
        return Response({
            'success': True,
            'message': 'Message deleted'
        })
        
    except Message.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Message not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )


# -------------------------------
# Web widget (session-auth) views
# -------------------------------

def _get_org(user):
    return getattr(user, "organization", None)


@login_required
def chat_widget_summary_view(request):
    """Lightweight summary for sidebar/chat widget."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "No organization assigned"}, status=403)

    channels = (
        Channel.objects.filter(organization=org)
        .annotate(
            latest_message_time=Subquery(
                Message.objects.filter(channel=OuterRef("pk"))
                .order_by("-created_at")
                .values("created_at")[:1]
            ),
            latest_message_content=Subquery(
                Message.objects.filter(channel=OuterRef("pk"))
                .order_by("-created_at")
                .values("content")[:1]
            ),
            is_member=Count("memberships", filter=Q(memberships__user=request.user)),
            join_status=Subquery(
                ChannelJoinRequest.objects.filter(channel=OuterRef("pk"), user=request.user)
                .values("status")[:1]
            ),
        )
        .order_by("name")
        .distinct()
    )

    channels_data = [
        {
            "id": str(ch.id),
            "type": "channel",
            "name": ch.name,
            "display_name": ch.name.replace("-", " ").title(),
            "last_message": ch.latest_message_content or "",
            "last_message_time": ch.latest_message_time.isoformat() if ch.latest_message_time else None,
            "is_member": bool(ch.is_member),
            "is_public": ch.is_public,
            "join_status": ch.join_status or None,
        }
        for ch in channels
    ]

    dms = (
        DirectMessage.objects.filter(organization=org, participants=request.user)
        .annotate(
            latest_message_time=Subquery(
                Message.objects.filter(direct_message=OuterRef("pk"))
                .order_by("-created_at")
                .values("created_at")[:1]
            ),
            latest_message_content=Subquery(
                Message.objects.filter(direct_message=OuterRef("pk"))
                .order_by("-created_at")
                .values("content")[:1]
            ),
        )
        .order_by("-updated_at")
    )

    def _display_name(user_obj):
        if hasattr(user_obj, "member_profile") and user_obj.member_profile:
            return user_obj.member_profile.full_name
        return user_obj.email or user_obj.username

    dms_data = []
    for dm in dms:
        other = dm.participants.exclude(uid=request.user.uid).first()
        name = _display_name(other) if other else "Direct Message"
        dms_data.append(
            {
                "id": str(dm.id),
                "type": "dm",
                "name": name,
                "last_message": dm.latest_message_content or "",
                "last_message_time": dm.latest_message_time.isoformat() if dm.latest_message_time else None,
            }
        )

    members_data = []
    members_qs = User.objects.filter(organization=org).exclude(uid=request.user.uid).order_by("first_name", "email")
    for person in members_qs:
        members_data.append(
            {
                "id": str(person.uid),
                "name": _display_name(person),
                "email": person.email,
                "role": getattr(getattr(person, "member_profile", None), "family_role", "") or "Member",
            }
        )

    return JsonResponse({"channels": channels_data, "dms": dms_data, "members": members_data})


@login_required
def chat_page(request):
    """Full chat page for the dashboard (session auth)."""
    return render(request, "chat/chat.html")


@login_required
def chat_widget_messages_view(request, thread_type, thread_id):
    """Return recent messages for a channel or dm."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "No organization assigned"}, status=403)

    if thread_type == "channel":
        thread = get_object_or_404(Channel, id=thread_id, organization=org)
        if not thread.is_public and not ChannelMembership.objects.filter(channel=thread, user=request.user).exists():
            return JsonResponse({"error": "Not a member of this channel"}, status=403)
        qs = Message.objects.filter(channel=thread).select_related("sender").order_by("-created_at")[:40]
        thread_name = thread.name
    elif thread_type == "dm":
        thread = get_object_or_404(DirectMessage, id=thread_id, organization=org, participants=request.user)
        qs = Message.objects.filter(direct_message=thread).select_related("sender").order_by("-created_at")[:40]
        thread_name = ", ".join(
            [
                u.member_profile.full_name if hasattr(u, "member_profile") else (u.email or u.username)
                for u in thread.participants.exclude(uid=request.user.uid)
            ]
        )
    else:
        return JsonResponse({"error": "Invalid thread type"}, status=400)

    messages_payload = []
    for msg in qs[::-1]:  # oldest first
        sender = msg.sender
        display = sender.member_profile.full_name if hasattr(sender, "member_profile") else (sender.email or sender.username)
        messages_payload.append(
            {
                "id": str(msg.id),
                "sender": display,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
                "is_me": sender == request.user,
            }
        )

    return JsonResponse({"messages": messages_payload, "thread": thread_name})


@login_required
def chat_widget_send_view(request):
    """Send a message to a channel or dm (session-auth)."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "No organization assigned"}, status=403)

    thread_type = request.POST.get("thread_type")
    thread_id = request.POST.get("thread_id")
    content = (request.POST.get("content") or "").strip()
    if not content:
        return JsonResponse({"error": "Content required"}, status=400)

    if thread_type == "channel":
        channel = get_object_or_404(Channel, id=thread_id, organization=org)
        msg = Message.objects.create(channel=channel, sender=request.user, content=content)
        broadcast_message("channel", channel.id, msg)
    elif thread_type == "dm":
        dm = get_object_or_404(DirectMessage, id=thread_id, organization=org, participants=request.user)
        msg = Message.objects.create(direct_message=dm, sender=request.user, content=content)
        broadcast_message("dm", dm.id, msg)
    else:
        return JsonResponse({"error": "Invalid thread type"}, status=400)

    return JsonResponse(
        {
            "id": str(msg.id),
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
            "sender": request.user.member_profile.full_name
            if hasattr(request.user, "member_profile")
            else (request.user.email or request.user.username),
        }
    )


@login_required
@require_POST
def chat_widget_start_dm_view(request):
    """Create (or reuse) a DM thread with another user in the same organization."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "No organization assigned"}, status=403)

    target_id = request.POST.get("user_id")
    if not target_id:
        return JsonResponse({"error": "user_id required"}, status=400)

    try:
        target = User.objects.get(uid=target_id, organization=org)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    if target == request.user:
        return JsonResponse({"error": "Cannot start a chat with yourself"}, status=400)

    dm = (
        DirectMessage.objects.filter(organization=org, participants=request.user)
        .filter(participants=target)
        .first()
    )
    if not dm:
        dm = DirectMessage.objects.create(organization=org)
        dm.participants.add(request.user, target)

    display = target.member_profile.full_name if hasattr(target, "member_profile") else (target.email or target.username)
    return JsonResponse({"thread_id": str(dm.id), "type": "dm", "name": display})


@login_required
@require_POST
def chat_widget_create_channel_view(request):
    """Session-auth helper to create a channel from the dashboard chat page."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "No organization assigned"}, status=403)

    name = (request.POST.get("name") or "").strip()
    description = (request.POST.get("description") or "").strip()
    is_public = request.POST.get("is_public", "true").lower() != "false"

    if not name:
        return JsonResponse({"error": "Channel name required"}, status=400)

    channel, created = Channel.objects.get_or_create(
        organization=org,
        name=name.lower().replace(" ", "-"),
        defaults={
            "description": description,
            "is_public": is_public,
            "created_by": request.user,
        },
    )
    # Ensure creator is a member
    ChannelMembership.objects.get_or_create(channel=channel, user=request.user)

    return JsonResponse(
        {
            "id": str(channel.id),
            "created": created,
            "name": channel.name,
            "display_name": channel.name.replace("-", " ").title(),
        }
    )


@login_required
@require_POST
def chat_widget_join_channel_view(request):
    """Join or request to join a channel from the dashboard chat page."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "No organization assigned"}, status=403)

    channel_id = request.POST.get("channel_id")
    channel = get_object_or_404(Channel, id=channel_id, organization=org)

    if channel.is_public:
        ChannelMembership.objects.get_or_create(channel=channel, user=request.user)
        return JsonResponse({"joined": True, "status": "joined"})

    req, created = ChannelJoinRequest.objects.get_or_create(channel=channel, user=request.user)
    if not created and req.status == "approved":
        ChannelMembership.objects.get_or_create(channel=channel, user=request.user)
        return JsonResponse({"joined": True, "status": "approved"})

    req.status = "pending"
    req.decided_at = None
    req.decided_by = None
    req.save()
    ChannelMembership.objects.filter(channel=channel, user=request.user).delete()
    return JsonResponse({"joined": False, "status": "pending"})


@login_required
@require_POST
def chat_widget_add_member_view(request):
    """Add a member to a channel (session auth, limited to admins/pastors/owners or channel creators)."""
    org = _get_org(request.user)
    if not org:
        return JsonResponse({"error": "No organization assigned"}, status=403)

    channel_id = request.POST.get("channel_id")
    user_id = request.POST.get("user_id")
    if not channel_id or not user_id:
        return JsonResponse({"error": "channel_id and user_id required"}, status=400)

    channel = get_object_or_404(Channel, id=channel_id, organization=org)
    target_user = get_object_or_404(User, uid=user_id, organization=org)

    # Permission: admins/pastors/owners or channel creator
    if not (
        request.user.is_admin
        or request.user.is_pastor
        or request.user.is_owner
        or channel.created_by == request.user
    ):
        return JsonResponse({"error": "You do not have permission to add members to this channel"}, status=403)

    membership, created = ChannelMembership.objects.get_or_create(channel=channel, user=target_user)
    return JsonResponse({
        "added": True,
        "channel_id": str(channel.id),
        "user_id": str(target_user.uid),
        "created": created,
    })
