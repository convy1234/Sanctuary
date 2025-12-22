import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from accounts.models import User


class Channel(models.Model):
    """
    Simple chat channel (like Slack channel)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('church.Organization', on_delete=models.CASCADE, related_name='channels')
    
    name = models.CharField(max_length=100, unique=True)  # e.g., "general", "worship-team"
    description = models.CharField(max_length=255, blank=True)
    
    # Auto-add all organization members?
    is_public = models.BooleanField(default=True, 
                                   help_text="All organization members can join automatically")
    
    # Who can post
    is_read_only = models.BooleanField(default=False, 
                                      help_text="Only admins can post (for announcements)")
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, 
                                   on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"#{self.name} ({self.organization.slug})"
    
    def save(self, *args, **kwargs):
        # Ensure channel name is lowercase with dashes
        if self.name:
            self.name = self.name.lower().replace(' ', '-')
        super().save(*args, **kwargs)
    
    def get_members(self):
        """Get all members who can access this channel"""
        if self.is_public:
            # All organization members
            return self.organization.members.all()
        else:
            # Only channel members
            return User.objects.filter(channel_memberships__channel=self)


class ChannelMembership(models.Model):
    """
    Track which users are in which channels
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='channel_memberships')
    
    # ADD THIS FIELD for unread tracking
    last_read_at = models.DateTimeField(null=True, blank=True)
    
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['channel', 'user']
    
    def __str__(self):
        return f"{self.user.username} in #{self.channel.name}"


class DirectMessage(models.Model):
    """
    Simple direct message thread between users
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('church.Organization', on_delete=models.CASCADE, related_name='direct_messages')
    
    # Store participants
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='direct_messages')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        users = list(self.participants.all()[:3])
        names = ", ".join([u.member_profile.full_name for u in users])
        if self.participants.count() > 3:
            names += f" and {self.participants.count() - 3} more"
        return f"DM: {names}"
    
    @classmethod
    def get_or_create_dm(cls, user1, user2, organization):
        """Get existing DM or create new one between two users"""
        # Find existing DM with exactly these two users
        existing = cls.objects.filter(
            organization=organization,
            participants=user1
        ).filter(participants=user2)
        
        for dm in existing:
            if dm.participants.count() == 2:
                return dm
        
        # Create new DM
        dm = cls.objects.create(organization=organization)
        dm.participants.add(user1, user2)
        return dm
    
    def get_other_user(self, current_user):
        """Get the other user in a 1:1 DM"""
        return self.participants.exclude(id=current_user.id).first()


class Message(models.Model):
    """
    Simple message model for both channels and DMs
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Parent: either Channel or DirectMessage
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, 
                               null=True, blank=True, related_name='messages')
    direct_message = models.ForeignKey(DirectMessage, on_delete=models.CASCADE,
                                      null=True, blank=True, related_name='messages')
    
    # Message content
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                              related_name='messages')
    content = models.TextField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Read receipts (simple)
    read_by = models.ManyToManyField(settings.AUTH_USER_MODEL, 
                                    related_name='read_messages',
                                    blank=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        sender_name = self.sender.member_profile.full_name if hasattr(self.sender, 'member_profile') else self.sender.username
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{sender_name}: {preview}"
    
    def save(self, *args, **kwargs):
        # Update parent's updated_at timestamp
        super().save(*args, **kwargs)
        if self.channel:
            self.channel.updated_at = timezone.now()
            self.channel.save(update_fields=['updated_at'])
        elif self.direct_message:
            self.direct_message.updated_at = timezone.now()
            self.direct_message.save(update_fields=['updated_at'])


class ChatFile(models.Model):
    """
    Simple file upload for messages
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='files')
    
    file = models.FileField(upload_to='chat/files/%Y/%m/%d/')
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.file_name


class ChannelJoinRequest(models.Model):
    """
    Tracks requests to join a private/non-public channel.
    """
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="join_requests")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="channel_join_requests")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="channel_join_decisions"
    )

    class Meta:
        unique_together = ("channel", "user")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} -> {self.channel} [{self.status}]"
