import uuid

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from django.contrib.auth.models import AnonymousUser

from .models import Channel, DirectMessage, ChannelMembership
from .views import channel_group_name, dm_group_name


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close()
            return

        self.thread_type = self.scope["url_route"]["kwargs"].get("thread_type")
        self.thread_id = self.scope["url_route"]["kwargs"].get("thread_id")

        if not await self._can_join(user, self.thread_type, self.thread_id):
            await self.close()
            return

        if self.thread_type == "channel":
            self.group_name = channel_group_name(self.thread_id)
        else:
            self.group_name = dm_group_name(self.thread_id)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "status", "state": "connected"})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def chat_message(self, event):
        await self.send_json(event.get("data", {}))

    @sync_to_async
    def _can_join(self, user, thread_type, thread_id):
        if thread_type == "channel":
            try:
                channel = Channel.objects.get(id=thread_id, organization=user.organization)
            except Channel.DoesNotExist:
                return False
            if channel.is_public:
                ChannelMembership.objects.get_or_create(channel=channel, user=user)
                return True
            return ChannelMembership.objects.filter(channel=channel, user=user).exists()
        if thread_type == "dm":
            try:
                dm = DirectMessage.objects.get(id=thread_id, organization=user.organization)
            except DirectMessage.DoesNotExist:
                return False
            return dm.participants.filter(id=user.id).exists()
        return False
