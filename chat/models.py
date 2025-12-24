import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from accounts.models import User
from task.models import Task


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


import uuid
import re
from datetime import datetime, timedelta
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


class Message(models.Model):
    """
    Chat message model with task conversion capabilities
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Parent: either Channel or DirectMessage
    channel = models.ForeignKey('Channel', on_delete=models.CASCADE, 
                               null=True, blank=True, related_name='messages')
    direct_message = models.ForeignKey('DirectMessage', on_delete=models.CASCADE,
                                      null=True, blank=True, related_name='messages')
    
    # Message content
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                              related_name='messages')
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    content = models.TextField()
    
    # Message type for system messages
    MESSAGE_TYPES = [
        ('text', 'Text Message'),
        ('task_created', 'Task Created'),
        ('task_assigned', 'Task Assigned'),
        ('task_completed', 'Task Completed'),
        ('task_updated', 'Task Updated'),
        ('file_share', 'File Shared'),
        ('system', 'System Message'),
    ]
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='text')
    
    # Task conversion fields
    converted_to_task = models.OneToOneField(
        'task.Task',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='converted_from_message',  # CHANGE THIS NAME
        help_text="The task that was created from this message"
    )
    
    # Optional: Link to an existing task (for task updates/comments in chat)
    related_task = models.ForeignKey(
        'task.Task',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_references',
        help_text="Task referenced in this message"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Read receipts
    read_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='read_messages',
        blank=True
    )
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['channel', 'created_at']),
            models.Index(fields=['direct_message', 'created_at']),
            models.Index(fields=['message_type']),
            models.Index(fields=['converted_to_task']),
            models.Index(fields=['related_task', 'created_at']),
        ]
    
    def __str__(self):
        sender_name = self.sender.member_profile.full_name if hasattr(self.sender, 'member_profile') else self.sender.username
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{sender_name}: {preview}"
    
    def save(self, *args, **kwargs):
        # Update parent's updated_at timestamp
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if self.channel:
            self.channel.updated_at = timezone.now()
            self.channel.save(update_fields=['updated_at'])
        elif self.direct_message:
            self.direct_message.updated_at = timezone.now()
            self.direct_message.save(update_fields=['updated_at'])
        
        # Process mentions in new messages
        if is_new and self.message_type == 'text':
            self._process_mentions()
    
    def mark_as_read(self, user):
        """Mark this message as read by a user"""
        self.read_by.add(user)
        
        # Update channel membership last_read_at
        if self.channel:
            membership = ChannelMembership.objects.filter(
                channel=self.channel, user=user
            ).first()
            if membership:
                membership.last_read_at = timezone.now()
                membership.save(update_fields=['last_read_at'])
    
    def convert_to_task(self, **kwargs):
        """
        Convert this message into a task
        
        Usage:
        task = message.convert_to_task(
            title="Custom Title",
            assigned_to=user,
            due_date=datetime.now() + timedelta(days=7),
            priority=3,
            labels=[label1, label2],
            department=worship_department
        )
        """
        from task.models import Task, TaskPriority
        from accounts.models import User
        
        # Check if already converted
        if self.converted_to_task:
            raise ValueError("This message has already been converted to a task")
        
        # Get parameters
        title = kwargs.get('title')
        assigned_to = kwargs.get('assigned_to')
        due_date = kwargs.get('due_date')
        priority = kwargs.get('priority', TaskPriority.NORMAL)
        labels = kwargs.get('labels', [])
        department = kwargs.get('department')
        is_private = kwargs.get('is_private', False)
        
        # Generate title from content if not provided
        if not title:
            title = self.content[:100]
            if len(self.content) > 100:
                title += "..."
        
        # Create the task
        task = Task.objects.create(
            organization=self.sender.organization,
            title=title,
            description=f"Task created from chat message:\n\n**Original Message:**\n{self.content}\n\n**Context:** {'Channel: ' + self.channel.name if self.channel else 'Direct Message'}",
            created_by=self.sender,
            assigned_to=assigned_to,
            department=department,
            origin_message=self,
            priority=priority,
            due_date=due_date,
            is_private=is_private,
            # Link to chat context
            related_channel=self.channel,
            related_dm=self.direct_message
        )
        
        # Add labels if provided
        if labels:
            task.labels.set(labels)
        
        # Link message to task
        self.converted_to_task = task
        self.save(update_fields=['converted_to_task'])
        
        # Create a system message in the chat about the task creation
        self._create_task_notification_message(task)
        
        # Send notifications
        self._send_task_notifications(task, assigned_to)
        
        return task
    
    def _create_task_notification_message(self, task):
        """Create a system message about task creation"""
        from task.models import TaskPriority
        
        priority_labels = {
            TaskPriority.LOW: "Low",
            TaskPriority.NORMAL: "Normal", 
            TaskPriority.HIGH: "High",
            TaskPriority.URGENT: "Urgent",
            TaskPriority.CRITICAL: "Critical"
        }
        
        message_content = f"✅ **Task Created**\n"
        message_content += f"**Title:** {task.title}\n"
        message_content += f"**Priority:** {priority_labels.get(task.priority, 'Normal')}\n"
        
        if task.assigned_to:
            assignee_name = task.assigned_to.member_profile.full_name if hasattr(task.assigned_to, 'member_profile') else task.assigned_to.email
            message_content += f"**Assigned to:** {assignee_name}\n"
        
        if task.due_date:
            message_content += f"**Due:** {task.due_date.strftime('%b %d, %Y')}\n"
        
        # Create the notification message
        Message.objects.create(
            channel=self.channel,
            direct_message=self.direct_message,
            sender=self.sender,
            content=message_content,
            message_type='task_created',
            related_task=task
        )
    
    def _send_task_notifications(self, task, assigned_to):
        """Send notifications to relevant users"""
        from task.models import TaskNotification
        
        # Notify the assignee
        if assigned_to:
            TaskNotification.objects.create(
                user=assigned_to,
                task=task,
                notification_type='assignment',
                title=f'Task Assigned: {task.title}',
                message=f'{self.sender.email} created a task from a chat message and assigned it to you'
            )
        
        # Notify other participants in the chat (excluding sender and assignee)
        chat_participants = self._get_chat_participants()
        for participant in chat_participants:
            if participant != self.sender and participant != assigned_to:
                TaskNotification.objects.create(
                    user=participant,
                    task=task,
                    notification_type='assignment',
                    title=f'New Task Created: {task.title}',
                    message=f'{self.sender.email} created a task from a chat message you participated in'
                )
    
    def _get_chat_participants(self):
        """Get all participants in the current chat context"""
        from accounts.models import User
        
        participants = set()
        
        if self.channel:
            # Get all channel members
            memberships = ChannelMembership.objects.filter(channel=self.channel)
            for membership in memberships:
                participants.add(membership.user)
        elif self.direct_message:
            # Get all DM participants
            for participant in self.direct_message.participants.all():
                participants.add(participant)
        
        return list(participants)
    
    def _process_mentions(self):
        """Process @mentions in message content"""
        from accounts.models import User
        
        # Simple mention pattern: @username or @email
        mention_pattern = r'@([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        mentions = re.findall(mention_pattern, self.content)
        
        for email in mentions:
            try:
                user = User.objects.get(email=email, organization=self.sender.organization)
                Mention.objects.get_or_create(message=self, user=user)
            except User.DoesNotExist:
                pass
    
    @property
    def can_convert_to_task(self):
        """Check if this message can be converted to a task"""
        return not self.converted_to_task and self.message_type == 'text'
    
    @property
    def chat_context(self):
        """Get the chat context info"""
        if self.channel:
            return {
                'type': 'channel',
                'id': self.channel.id,
                'name': self.channel.name,
                'url': f'/chat/channels/{self.channel.id}'
            }
        elif self.direct_message:
            other_user = self.direct_message.get_other_user(self.sender)
            return {
                'type': 'dm',
                'id': self.direct_message.id,
                'other_user': {
                    'id': other_user.id if other_user else None,
                    'email': other_user.email if other_user else None
                },
                'url': f'/chat/direct/{self.direct_message.id}'
            }
        return None
    
    def get_task_conversion_suggestions(self):
        """
        Analyze message content and suggest task parameters
        
        Returns:
        {
            'title': 'Suggested task title',
            'priority': 'high',
            'due_date': '2024-12-31',
            'assignee_suggestions': [
                {'id': 'user-id', 'email': 'user@example.com', 'reason': 'mentioned in message'}
            ],
            'keywords': ['urgent', 'follow-up', 'review']
        }
        """
        suggestions = {
            'title': self._suggest_task_title(),
            'priority': self._suggest_priority(),
            'due_date': self._suggest_due_date(),
            'assignee_suggestions': self._suggest_assignees(),
            'keywords': self._extract_keywords(),
            'estimated_duration': self._estimate_duration()
        }
        
        return suggestions
    
    def _suggest_task_title(self):
        """Extract a task title from message content"""
        content = self.content.strip()
        
        # If message starts with action-oriented text, use first sentence
        action_indicators = ['Can you', 'Please', 'Need to', 'Should', 'Must', 'Have to']
        
        for indicator in action_indicators:
            if content.lower().startswith(indicator.lower()):
                # Get first sentence
                sentences = content.split('.')
                if sentences and sentences[0]:
                    return sentences[0].strip()
        
        # Otherwise use first 10 words
        words = content.split()
        if len(words) > 10:
            return ' '.join(words[:10]) + '...'
        return content
    
    def _suggest_priority(self):
        """Suggest priority based on keywords"""
        content_lower = self.content.lower()
        
        priority_keywords = {
            'urgent': ['urgent', 'asap', 'immediately', 'right away', 'emergency', 'critical'],
            'high': ['important', 'priority', 'high priority', 'must', 'essential'],
            'normal': ['please', 'can you', 'could you', 'when you have time'],
            'low': ['whenever', 'no rush', 'low priority', 'sometime']
        }
        
        for priority_level, keywords in priority_keywords.items():
            for keyword in keywords:
                if keyword in content_lower:
                    return priority_level
        
        return 'normal'
    
    def _suggest_due_date(self):
        """Extract due date suggestions from text"""
        content_lower = self.content.lower()
        
        # Check for specific time references
        time_patterns = [
            (r'today', timezone.now().date()),
            (r'tomorrow', timezone.now().date() + timedelta(days=1)),
            (r'next week', timezone.now().date() + timedelta(days=7)),
            (r'next month', timezone.now().date() + timedelta(days=30)),
            (r'in (\d+) days', lambda m: timezone.now().date() + timedelta(days=int(m.group(1)))),
            (r'by (\w+)day', lambda m: self._get_next_weekday(m.group(1))),
            (r'on (\w+) \d{1,2}', lambda m: self._parse_date_string(m.group(0))),
        ]
        
        for pattern, date_calc in time_patterns:
            match = re.search(pattern, content_lower)
            if match:
                if callable(date_calc):
                    try:
                        return date_calc(match).isoformat()
                    except:
                        continue
                else:
                    return date_calc.isoformat()
        
        return None
    
    def _suggest_assignees(self):
        """Suggest assignees based on mentions and context"""
        from accounts.models import User
        
        suggestions = []
        
        # Check for @mentions
        mentions = Mention.objects.filter(message=self)
        for mention in mentions:
            suggestions.append({
                'id': mention.user.id,
                'email': mention.user.email,
                'name': mention.user.member_profile.full_name if hasattr(mention.user, 'member_profile') else mention.user.email,
                'reason': 'mentioned in message',
                'confidence': 'high'
            })
        
        # Check for context-based suggestions
        if self.channel and self.channel.department:
            # Suggest department head
            dept_head = User.objects.filter(
                organization=self.sender.organization,
                department=self.channel.department,
                is_hod=True
            ).first()
            
            if dept_head and dept_head not in [s['id'] for s in suggestions]:
                suggestions.append({
                    'id': dept_head.id,
                    'email': dept_head.email,
                    'name': dept_head.member_profile.full_name if hasattr(dept_head, 'member_profile') else dept_head.email,
                    'reason': f'Head of {self.channel.department.name} department',
                    'confidence': 'medium'
                })
        
        return suggestions
    
    def _extract_keywords(self):
        """Extract relevant keywords from message"""
        # Remove common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        
        words = re.findall(r'\b\w+\b', self.content.lower())
        keywords = [word for word in words if word not in stop_words and len(word) > 3]
        
        # Return top 5 unique keywords
        from collections import Counter
        keyword_counts = Counter(keywords)
        return [keyword for keyword, _ in keyword_counts.most_common(5)]
    
    def _estimate_duration(self):
        """Estimate task duration based on content"""
        content_lower = self.content.lower()
        
        # Simple estimation based on content length and keywords
        word_count = len(content_lower.split())
        
        if word_count < 20:
            return 'short'  # < 1 hour
        elif word_count < 100:
            return 'medium'  # 1-4 hours
        else:
            return 'long'  # > 4 hours
    
    def _get_next_weekday(self, weekday):
        """Get the next specific weekday"""
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        
        if weekday.lower() not in weekdays:
            return None
        
        target_day = weekdays.index(weekday.lower())
        today = timezone.now().date()
        days_ahead = target_day - today.weekday()
        
        if days_ahead <= 0:
            days_ahead += 7
        
        return today + timedelta(days=days_ahead)
    
    def _parse_date_string(self, date_str):
        """Parse date string like 'Friday 15' or 'Dec 15'"""
        try:
            # Try to parse with dateutil if available
            from dateutil import parser
            return parser.parse(date_str).date()
        except:
            return None


class Mention(models.Model):
    """
    Track user mentions in messages
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='mentions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mentions')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['message', 'user']
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.email} mentioned in message {self.message.id}"

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
