# chat/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from .models import Channel, DirectMessage, Message, ChannelMembership
from channels.layers import get_channel_layer

channel_layer = get_channel_layer()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope["user"]
        
        # Initialize attributes to None
        self.room_group_name = None
        self.dm_id = None
        self.channel_id = None
        
        if self.user.is_anonymous:
            await self.close(code=4001)  # Custom close code for unauthorized
            return
        
        try:
            # Get query parameters
            query_string = self.scope.get('query_string', b'').decode()
            params = {}
            
            if query_string:
                for param in query_string.split('&'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        params[key] = value
            
            self.dm_id = params.get('dm_id')
            self.channel_id = params.get('channel_id')
            
            # Determine room group name - FIXED: Use user.uid instead of user.id
            if self.dm_id:
                self.room_group_name = f'dm_{self.dm_id}'
            elif self.channel_id:
                self.room_group_name = f'channel_{self.channel_id}'
            else:
                # General connection - use user's uid (not id)
                self.room_group_name = f'user_{self.user.uid}'
            
            # Join room group
            if self.room_group_name:
                await self.channel_layer.group_add(
                    self.room_group_name,
                    self.channel_name
                )
            
            await self.accept()
            
            # Send connection confirmation
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': 'Connected to chat server',
                'room': self.room_group_name
            }))
            
        except Exception as e:
            print(f"Error in WebSocket connect: {e}")
            await self.close(code=4000)  # Custom close code for connection error

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Only discard if we successfully joined a group
        if hasattr(self, 'room_group_name') and self.room_group_name:
            try:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
            except Exception as e:
                print(f"Error discarding from group {self.room_group_name}: {e}")
        
        # Clean up attributes
        if hasattr(self, 'room_group_name'):
            del self.room_group_name
        if hasattr(self, 'dm_id'):
            del self.dm_id
        if hasattr(self, 'channel_id'):
            del self.channel_id

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'message':
                await self.handle_message(data)
            elif message_type == 'typing':
                await self.handle_typing(data)
            elif message_type == 'join_dm':
                await self.join_dm(data.get('dm_id'))
            elif message_type == 'join_channel':
                await self.join_channel(data.get('channel_id'))
            
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def handle_message(self, data):
        """Handle incoming chat message"""
        try:
            thread_type = data.get('thread_type')
            thread_id = data.get('thread_id')
            content = data.get('content', '').strip()
            reply_to = data.get('reply_to')
            
            if not content:
                raise ValueError("Message cannot be empty")
            
            # Save message to database
            if thread_type == 'dm':
                message = await self.save_dm_message(thread_id, content, reply_to)
                group_name = f'dm_{thread_id}'
            elif thread_type == 'channel':
                message = await self.save_channel_message(thread_id, content, reply_to)
                group_name = f'channel_{thread_id}'
            else:
                raise ValueError("Invalid thread type")
            
            if message:
                # Serialize message for broadcasting
                serialized_message = await self.serialize_message(message)
                
                # Broadcast to all in the room
                await self.channel_layer.group_send(
                    group_name,
                    {
                        'type': 'chat_message',
                        'message': serialized_message,
                        'thread_type': thread_type,
                        'thread_id': thread_id,
                    }
                )
                
                # Send confirmation to sender
                await self.send(text_data=json.dumps({
                    'type': 'message_sent',
                    'message_id': str(message.id),
                    'thread_type': thread_type,
                    'thread_id': thread_id,
                }))
                
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def handle_typing(self, data):
        """Handle typing indicator"""
        thread_type = data.get('thread_type')
        thread_id = data.get('thread_id')
        is_typing = data.get('is_typing', False)
        
        group_name = f'{thread_type}_{thread_id}'
        
        # Get user display name
        user_display_name = await self.get_user_display_name(self.user)
        
        # Broadcast typing indicator (except to sender) - FIXED: Use uid
        await self.channel_layer.group_send(
            group_name,
            {
                'type': 'typing_indicator',
                'user_id': str(self.user.uid),  # FIXED: Use uid
                'user_name': user_display_name,
                'is_typing': is_typing,
                'thread_type': thread_type,
                'thread_id': thread_id,
            }
        )

    async def join_dm(self, dm_id):
        """Join a DM room"""
        try:
            # Verify user is participant
            is_participant = await self.verify_dm_participant(dm_id)
            if not is_participant:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Not a participant in this DM'
                }))
                return
            
            # Leave previous room if any
            if hasattr(self, 'room_group_name') and self.room_group_name:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
            
            self.room_group_name = f'dm_{dm_id}'
            self.dm_id = dm_id
            self.channel_id = None
            
            # Join new room
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            await self.send(text_data=json.dumps({
                'type': 'joined_dm',
                'dm_id': dm_id,
                'message': f'Joined DM {dm_id}'
            }))
            
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error joining DM: {str(e)}'
            }))

    async def join_channel(self, channel_id):
        """Join a channel room"""
        try:
            # Verify user can access channel
            can_access = await self.verify_channel_access(channel_id)
            if not can_access:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Cannot access this channel'
                }))
                return
            
            # Leave previous room if any
            if hasattr(self, 'room_group_name') and self.room_group_name:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
            
            self.room_group_name = f'channel_{channel_id}'
            self.channel_id = channel_id
            self.dm_id = None
            
            # Join new room
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            await self.send(text_data=json.dumps({
                'type': 'joined_channel',
                'channel_id': channel_id,
                'message': f'Joined channel {channel_id}'
            }))
            
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error joining channel: {str(e)}'
            }))

    # WebSocket event handlers for group messages
    async def chat_message(self, event):
        """Receive chat message from group"""
        # Send to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'thread_type': event['thread_type'],
            'thread_id': event['thread_id'],
        }))

    async def typing_indicator(self, event):
        """Receive typing indicator from group"""
        # Don't send back to the user who's typing - FIXED: Compare with uid
        if event['user_id'] != str(self.user.uid):  # FIXED: Use uid
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'user_id': event['user_id'],
                'user_name': event['user_name'],
                'is_typing': event['is_typing'],
                'thread_type': event['thread_type'],
                'thread_id': event['thread_id'],
            }))

    # Database operations
    @database_sync_to_async
    def verify_dm_participant(self, dm_id):
        try:
            dm = DirectMessage.objects.get(id=dm_id)
            # FIXED: Use uid instead of id for filtering
            return dm.participants.filter(uid=self.user.uid).exists()
        except DirectMessage.DoesNotExist:
            return False

    @database_sync_to_async
    def verify_channel_access(self, channel_id):
        try:
            channel = Channel.objects.get(id=channel_id)
            if channel.is_public:
                return True
            # FIXED: Use uid instead of id for filtering
            return ChannelMembership.objects.filter(
                channel=channel, 
                user__uid=self.user.uid  # FIXED: Use uid
            ).exists()
        except Channel.DoesNotExist:
            return False

    @database_sync_to_async
    def save_dm_message(self, dm_id, content, reply_to=None):
        try:
            dm = DirectMessage.objects.get(id=dm_id)
            
            # Create message
            message = Message.objects.create(
                direct_message=dm,
                sender=self.user,
                content=content,
                reply_to=reply_to
            )
            
            # Mark as read by sender
            message.read_by.add(self.user)
            
            return message
        except Exception as e:
            print(f"Error saving DM message: {e}")
            return None

    @database_sync_to_async
    def save_channel_message(self, channel_id, content, reply_to=None):
        try:
            channel = Channel.objects.get(id=channel_id)
            
            # Create message
            message = Message.objects.create(
                channel=channel,
                sender=self.user,
                content=content,
                reply_to=reply_to
            )
            
            # Mark as read by sender
            message.read_by.add(self.user)
            
            # Update last read
            membership, _ = ChannelMembership.objects.get_or_create(
                channel=channel,
                user=self.user
            )
            membership.last_read_at = message.created_at
            membership.save()
            
            return message
        except Exception as e:
            print(f"Error saving channel message: {e}")
            return None

    @database_sync_to_async
    def serialize_message(self, message):
        """Serialize message for WebSocket transmission"""
        # Get sender info
        sender_name = message.sender.email.split('@')[0]
        sender_avatar = None
        
        try:
            member_profile = message.sender.member_profile
            if member_profile:
                sender_name = member_profile.full_name
                if member_profile.photo:
                    sender_avatar = f"/media/{member_profile.photo.name}"
        except AttributeError:
            pass
        
        return {
            'id': str(message.id),
            'content': message.content,
            'sender': {
                'id': str(message.sender.uid),  # FIXED: Use uid
                'name': sender_name,
                'avatar': sender_avatar,
            },
            'created_at': message.created_at.isoformat(),
            'created_at_timestamp': int(message.created_at.timestamp() * 1000),
            'reply_to': str(message.reply_to.id) if message.reply_to else None,
        }

    @database_sync_to_async
    def get_user_display_name(self, user):
        try:
            if hasattr(user, "member_profile") and user.member_profile:
                return user.member_profile.full_name
            return user.email or user.username
        except:
            return "Unknown User"