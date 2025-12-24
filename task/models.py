import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


class TaskPriority(models.IntegerChoices):
    """Priority levels for tasks"""
    LOW = 1, 'Low'
    NORMAL = 2, 'Normal'
    HIGH = 3, 'High'
    URGENT = 4, 'Urgent'
    CRITICAL = 5, 'Critical'


class TaskStatus(models.TextChoices):
    """Task status options"""
    PENDING = 'pending', 'Pending'
    IN_PROGRESS = 'in_progress', 'In Progress'
    COMPLETED = 'completed', 'Completed'
    ON_HOLD = 'on_hold', 'On Hold'
    CANCELLED = 'cancelled', 'Cancelled'
    OVERDUE = 'overdue', 'Overdue'


class TaskLabel(models.Model):
    """
    Color-coded labels for categorizing tasks
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('church.Organization', on_delete=models.CASCADE, related_name='task_labels')
    
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#6B7280', help_text="Hex color code")
    description = models.CharField(max_length=255, blank=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['organization', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.organization.slug})"


class Task(models.Model):
    """
    Main task model - can be created from chat messages
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('church.Organization', on_delete=models.CASCADE, related_name='tasks')
    
    # Basic task info
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Task classification
    priority = models.IntegerField(choices=TaskPriority.choices, default=TaskPriority.NORMAL)
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.PENDING)
    labels = models.ManyToManyField(TaskLabel, related_name='tasks', blank=True)
    
    # People involved
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                                  related_name='created_tasks')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='assigned_tasks')
    
    # Team/department
    department = models.ForeignKey('church.Department', on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='tasks')
    
    # Parent-child tasks (for subtasks)
    parent_task = models.ForeignKey('self', on_delete=models.CASCADE, 
                                   null=True, blank=True, related_name='subtasks')
    
    # ORIGIN MESSAGE - This is the key connection!
    # The chat message that this task was created from
    origin_message = models.ForeignKey('chat.Message', on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='created_tasks',
                                      help_text="The chat message this task was created from")
    
    # Related discussion (optional - can link to existing channel/DM)
    related_channel = models.ForeignKey('chat.Channel', on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='tasks')
    related_dm = models.ForeignKey('chat.DirectMessage', on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='tasks')
    
    # Timeline
    start_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Progress tracking
    progress = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Task dependencies
    depends_on = models.ManyToManyField('self', symmetrical=False, 
                                       related_name='dependencies', blank=True)
    
    # Visibility
    is_private = models.BooleanField(default=False, 
                                     help_text="Only visible to assigned users and creators")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-priority', 'due_date', '-created_at']
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['organization', 'assigned_to']),
            models.Index(fields=['organization', 'due_date']),
            models.Index(fields=['organization', 'priority']),
            models.Index(fields=['origin_message']),  # For quick lookups
        ]
    
    def __str__(self):
        return f"[{self.get_priority_display()}] {self.title}"
    
    def save(self, *args, **kwargs):
        # Update status if completed
        if self.progress == 100 and self.status != TaskStatus.COMPLETED:
            self.status = TaskStatus.COMPLETED
            self.completed_at = timezone.now()
        
        # Check for overdue tasks
        if (self.due_date and self.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]
                and timezone.now() > self.due_date):
            self.status = TaskStatus.OVERDUE
        
        super().save(*args, **kwargs)
    
    @property
    def is_overdue(self):
        return (self.due_date and self.status != TaskStatus.COMPLETED 
                and timezone.now() > self.due_date)
    
    @property
    def days_until_due(self):
        if not self.due_date:
            return None
        delta = self.due_date - timezone.now()
        return delta.days
    
    @property
    def participants(self):
        """Get all users involved in this task"""
        from accounts.models import User
        user_ids = set()
        user_ids.add(self.created_by_id)
        if self.assigned_to_id:
            user_ids.add(self.assigned_to_id)
        
        # Add comment authors
        user_ids.update(self.comments.values_list('author_id', flat=True))
        
        return User.objects.filter(id__in=user_ids)
    
    @property
    def chat_context(self):
        """Get the chat context where this task originated"""
        if self.origin_message:
            if self.origin_message.channel:
                return {
                    'type': 'channel',
                    'id': self.origin_message.channel.id,
                    'name': self.origin_message.channel.name
                }
            elif self.origin_message.direct_message:
                return {
                    'type': 'dm',
                    'id': self.origin_message.direct_message.id
                }
        return None
    
    @classmethod
    def create_from_message(cls, message, title=None, assigned_to=None, due_date=None, priority=None):
        """
        Create a task from a chat message
        
        Usage:
        task = Task.create_from_message(
            message=chat_message,
            title="Follow up on discussion",
            assigned_to=some_user,
            due_date=tomorrow,
            priority=TaskPriority.HIGH
        )
        """
        from accounts.models import User
        
        # Use message content as description if no title provided
        if not title:
            title = message.content[:100] + "..." if len(message.content) > 100 else message.content
        
        task = cls.objects.create(
            organization=message.sender.organization,
            title=title,
            description=f"Task created from chat message:\n\n{message.content}",
            created_by=message.sender,
            assigned_to=assigned_to,
            origin_message=message,
            priority=priority or TaskPriority.NORMAL,
            due_date=due_date
        )
        
        # Link to the chat context
        if message.channel:
            task.related_channel = message.channel
        elif message.direct_message:
            task.related_dm = message.direct_message
        
        task.save()
        
        # Create a notification in the chat about the task creation
        from chat.models import Message as ChatMessage
        ChatMessage.objects.create(
            channel=message.channel if message.channel else None,
            direct_message=message.direct_message if message.direct_message else None,
            sender=message.sender,
            content=f"✅ Task created from this message: {task.title}",
            message_type='task_created',
            related_task=task
        )
        
        # Send notification to assigned user
        if assigned_to:
            from .models import TaskNotification
            TaskNotification.objects.create(
                user=assigned_to,
                task=task,
                notification_type='assignment',
                title=f'Task Assigned: {task.title}',
                message=f'{message.sender.email} assigned you a task from a chat conversation'
            )
        
        return task


class TaskComment(models.Model):
    """
    Comments/discussion on tasks
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                              related_name='task_comments')
    
    content = models.TextField()
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, 
                                null=True, blank=True, related_name='replies')
    
    # File attachments
    attachments = models.ManyToManyField('chat.ChatFile', blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        preview = self.content[:50]
        return f"{self.author.email}: {preview}..."
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update task's last activity
        self.task.last_activity_at = timezone.now()
        self.task.save(update_fields=['last_activity_at'])


class TaskChecklist(models.Model):
    """
    Checklist items for a task
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='checklists')
    
    title = models.CharField(max_length=255)
    is_completed = models.BooleanField(default=False)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
    
    def __str__(self):
        status = "✓" if self.is_completed else "□"
        return f"{status} {self.title}"


class TaskReminder(models.Model):
    """
    Reminders for tasks
    """
    REMINDER_TYPES = [
        ('due_date', 'Due Date'),
        ('start_date', 'Start Date'),
        ('custom', 'Custom'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='reminders')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name='task_reminders')
    
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPES)
    remind_at = models.DateTimeField()
    message = models.CharField(max_length=255, blank=True)
    
    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['remind_at']
    
    def __str__(self):
        return f"Reminder for {self.task.title} at {self.remind_at}"


class TaskTimeLog(models.Model):
    """
    Time tracking for tasks
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name='task_time_logs')
    
    description = models.CharField(max_length=255)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    
    is_running = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_time']
    
    def __str__(self):
        duration = self.duration if self.end_time else "Running"
        return f"{self.user.email}: {duration} on {self.task.title}"
    
    @property
    def duration(self):
        if not self.end_time:
            return None
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 3600  # Return hours


class TaskNotification(models.Model):
    """
    Notifications for task events
    """
    NOTIFICATION_TYPES = [
        ('assignment', 'Task Assigned'),
        ('due_soon', 'Due Soon'),
        ('overdue', 'Task Overdue'),
        ('comment', 'New Comment'),
        ('completion', 'Task Completed'),
        ('progress', 'Progress Update'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name='task_notifications')
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='notifications')
    
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    is_read = models.BooleanField(default=False)
    is_important = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.notification_type}: {self.title}"