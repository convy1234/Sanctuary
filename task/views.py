import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Avg, Sum, Subquery, OuterRef, Prefetch, Value, IntegerField, Case, When
from django.db.models.functions import Coalesce
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from church.models import Department
from chat.models import Message as ChatMessage, Channel, DirectMessage, ChannelMembership
from .models import (
    Task, TaskPriority, TaskStatus, TaskLabel,
    TaskComment, TaskChecklist, TaskReminder,
    TaskTimeLog, TaskNotification
)

User = get_user_model()
channel_layer = get_channel_layer()


def get_user_organization(user):
    """Get user's organization with fallbacks"""
    if hasattr(user, 'organization') and user.organization:
        return user.organization
    
    # fallback if user belongs via profile or membership
    if hasattr(user, 'profile') and hasattr(user.profile, 'organization'):
        return user.profile.organization
    
    return None


def display_name_for(user):
    """Get display name for user"""
    if hasattr(user, "member_profile") and user.member_profile:
        return user.member_profile.full_name
    elif user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}".strip()
    elif user.first_name:
        return user.first_name
    else:
        return user.email.split('@')[0]


def get_user_role(user):
    """Get user role for display"""
    if user.is_owner:
        return "Owner"
    elif user.is_admin:
        return "Admin"
    elif user.is_pastor:
        return "Pastor"
    elif user.is_hod:
        return "Head of Department"
    elif user.is_worker:
        return "Worker"
    elif user.is_volunteer:
        return "Volunteer"
    else:
        return "Member"


def _serialize_chat_message(message):
    """Match chat socket payload shape"""
    sender_name = display_name_for(message.sender)
    sender_avatar = None
    try:
        if hasattr(message.sender, 'member_profile') and message.sender.member_profile.photo:
            sender_avatar = message.sender.member_profile.photo.url
    except AttributeError:
        pass
    return {
        'id': str(message.id),
        'content': message.content,
        'sender': {
            'id': str(message.sender.uid),
            'name': sender_name,
            'avatar': sender_avatar,
        },
        'created_at': message.created_at.isoformat(),
        'created_at_timestamp': int(message.created_at.timestamp() * 1000),
        'reply_to': str(message.reply_to.id) if message.reply_to else None,
    }


def _broadcast_chat_message(message):
    """Send a chat message to websocket subscribers if possible."""
    if not channel_layer:
        return
    
    if message.channel_id:
        thread_type = 'channel'
        thread_id = str(message.channel_id)
    elif message.direct_message_id:
        thread_type = 'dm'
        thread_id = str(message.direct_message_id)
    else:
        return
    
    try:
        async_to_sync(channel_layer.group_send)(
            f"{thread_type}_{thread_id}",
            {
                'type': 'chat_message',
                'message': _serialize_chat_message(message),
                'thread_type': thread_type,
                'thread_id': thread_id,
            }
        )
    except Exception:
        # Avoid failing the request if websocket broadcast fails
        pass


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_dashboard_api_view(request):
    """
    Task dashboard - summary and overview
    Returns data in the format expected by React Native app
    """
    user = request.user
    
    # Get user's organization
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get statistics
    tasks_qs = Task.objects.filter(organization=organization)
    
    # Apply privacy filters for non-admins
    if not (user.is_admin or user.is_pastor or user.is_owner):
        tasks_qs = tasks_qs.filter(
            Q(is_private=False) |
            Q(created_by=user) |
            Q(assigned_to=user)
        )
    
    # Calculate statistics
    total_tasks = tasks_qs.count()
    completed_tasks = tasks_qs.filter(status=TaskStatus.COMPLETED).count()
    in_progress_tasks = tasks_qs.filter(status=TaskStatus.IN_PROGRESS).count()
    pending_tasks = tasks_qs.filter(status=TaskStatus.PENDING).count()
    
    # Overdue tasks
    overdue_tasks = tasks_qs.filter(
        due_date__lt=timezone.now(),
        status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS]
    ).count()
    
    # Tasks assigned to me
    my_assigned_tasks = tasks_qs.filter(assigned_to=user).count()
    my_active_tasks = tasks_qs.filter(
        assigned_to=user,
        status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS]
    ).count()
    
    # Priority breakdown
    critical_tasks = tasks_qs.filter(priority=TaskPriority.CRITICAL).count()
    urgent_tasks = tasks_qs.filter(priority=TaskPriority.URGENT).count()
    high_tasks = tasks_qs.filter(priority=TaskPriority.HIGH).count()
    
    # Department breakdown
    departments = Department.objects.filter(organization=organization)
    department_stats = []
    
    for dept in departments:
        dept_tasks = tasks_qs.filter(department=dept)
        dept_stats = {
            'id': str(dept.id),
            'name': dept.name,
            'code': dept.code,
            'total': dept_tasks.count(),
            'completed': dept_tasks.filter(status=TaskStatus.COMPLETED).count(),
            'in_progress': dept_tasks.filter(status=TaskStatus.IN_PROGRESS).count(),
            'pending': dept_tasks.filter(status=TaskStatus.PENDING).count(),
        }
        department_stats.append(dept_stats)
    
    # Recent activity (last 7 days)
    week_ago = timezone.now() - timedelta(days=7)
    recent_created = tasks_qs.filter(created_at__gte=week_ago).count()
    recent_completed = tasks_qs.filter(
        status=TaskStatus.COMPLETED,
        completed_at__gte=week_ago
    ).count()
    
    # Upcoming deadlines (next 7 days)
    upcoming_deadline = timezone.now() + timedelta(days=7)
    upcoming_tasks = tasks_qs.filter(
        due_date__range=[timezone.now(), upcoming_deadline],
        status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS]
    ).count()
    
    # Compile dashboard data
    dashboard_data = {
        'summary': {
            'total': total_tasks,
            'completed': completed_tasks,
            'in_progress': in_progress_tasks,
            'pending': pending_tasks,
            'overdue': overdue_tasks,
            'assigned_to_me': my_assigned_tasks,
            'my_active': my_active_tasks,
        },
        'priority_breakdown': {
            'critical': critical_tasks,
            'urgent': urgent_tasks,
            'high': high_tasks,
            'normal': tasks_qs.filter(priority=TaskPriority.NORMAL).count(),
            'low': tasks_qs.filter(priority=TaskPriority.LOW).count(),
        },
        'recent_activity': {
            'created_this_week': recent_created,
            'completed_this_week': recent_completed,
            'upcoming_deadlines': upcoming_tasks,
        },
        'departments': department_stats,
        'user_stats': {
            'role': get_user_role(user),
            'can_create_task': True,  # All users can create tasks
            'can_manage_all': user.is_admin or user.is_pastor or user.is_owner,
        }
    }
    
    return Response({
        'success': True,
        'dashboard': dashboard_data,
        'timestamp': timezone.now().isoformat(),
    })


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_list_api_view(request):
    """
    Get tasks with filtering and pagination
    """
    user = request.user
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get query parameters
    status_filter = request.query_params.get('status')
    priority_filter = request.query_params.get('priority')
    assigned_to_filter = request.query_params.get('assigned_to')
    created_by_filter = request.query_params.get('created_by')
    department_filter = request.query_params.get('department')
    label_filter = request.query_params.get('label')
    search_query = request.query_params.get('search', '').strip()
    show_my_tasks = request.query_params.get('my_tasks', '').lower() == 'true'
    show_overdue = request.query_params.get('overdue', '').lower() == 'true'
    
    # Pagination
    page = int(request.query_params.get('page', 1))
    limit = int(request.query_params.get('limit', 20))
    offset = (page - 1) * limit
    
    # Base queryset
    tasks_qs = Task.objects.filter(organization=organization)
    
    # Apply privacy filters for non-admins
    if not (user.is_admin or user.is_pastor or user.is_owner):
        tasks_qs = tasks_qs.filter(
            Q(is_private=False) |
            Q(created_by=user) |
            Q(assigned_to=user)
        )
    
    # Apply filters
    if status_filter:
        tasks_qs = tasks_qs.filter(status=status_filter)
    
    if priority_filter and priority_filter.isdigit():
        tasks_qs = tasks_qs.filter(priority=int(priority_filter))
    
    if assigned_to_filter:
        tasks_qs = tasks_qs.filter(assigned_to__uid=assigned_to_filter)
    
    if created_by_filter:
        tasks_qs = tasks_qs.filter(created_by__uid=created_by_filter)
    
    if department_filter:
        tasks_qs = tasks_qs.filter(department__id=department_filter)
    
    if label_filter:
        tasks_qs = tasks_qs.filter(labels__id=label_filter)
    
    if search_query:
        tasks_qs = tasks_qs.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if show_my_tasks:
        tasks_qs = tasks_qs.filter(
            Q(assigned_to=user) |
            Q(created_by=user)
        )
    
    if show_overdue:
        tasks_qs = tasks_qs.filter(
            due_date__lt=timezone.now(),
            status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS]
        )
    
    # Get total count before pagination
    total_tasks = tasks_qs.count()
    
    # Apply sorting (priority, then due date, then created date)
    tasks_qs = tasks_qs.select_related(
        'created_by', 'assigned_to', 'department'
    ).prefetch_related('labels').order_by('-priority', 'due_date', '-created_at')
    
    # Apply pagination
    tasks = tasks_qs[offset:offset + limit]
    
    # Format tasks for response
    tasks_data = []
    for task in tasks:
        # Get creator info
        creator_name = display_name_for(task.created_by)
        creator_avatar = None
        try:
            if hasattr(task.created_by, 'member_profile') and task.created_by.member_profile.photo:
                creator_avatar = request.build_absolute_uri(task.created_by.member_profile.photo.url)
        except AttributeError:
            pass
        
        # Get assignee info
        assignee_info = None
        if task.assigned_to:
            assignee_name = display_name_for(task.assigned_to)
            assignee_avatar = None
            try:
                if hasattr(task.assigned_to, 'member_profile') and task.assigned_to.member_profile.photo:
                    assignee_avatar = request.build_absolute_uri(task.assigned_to.member_profile.photo.url)
            except AttributeError:
                pass
            
            assignee_info = {
                'id': str(task.assigned_to.uid),
                'name': assignee_name,
                'avatar': assignee_avatar,
                'role': get_user_role(task.assigned_to),
            }
        
        # Get department info
        department_info = None
        if task.department:
            department_info = {
                'id': str(task.department.id),
                'name': task.department.name,
                'code': task.department.code,
            }
        
        # Get labels
        labels_data = []
        for label in task.labels.all():
            labels_data.append({
                'id': str(label.id),
                'name': label.name,
                'color': label.color,
            })
        
        # Get chat context if exists
        chat_context = None
        if task.origin_message:
            chat_context = {
                'type': 'channel' if task.origin_message.channel else 'dm',
                'id': str(task.origin_message.channel.id if task.origin_message.channel else task.origin_message.direct_message.id),
                'message_id': str(task.origin_message.id),
                'preview': task.origin_message.content[:100] + '...' if len(task.origin_message.content) > 100 else task.origin_message.content,
            }
        
        # Format task data
        task_data = {
            'id': str(task.id),
            'title': task.title,
            'description': task.description,
            'priority': task.priority,
            'priority_label': task.get_priority_display(),
            'status': task.status,
            'status_label': task.get_status_display(),
            'progress': task.progress,
            'is_overdue': task.is_overdue,
            'is_private': task.is_private,
            
            'created_by': {
                'id': str(task.created_by.uid),
                'name': creator_name,
                'avatar': creator_avatar,
                'role': get_user_role(task.created_by),
            },
            'assigned_to': assignee_info,
            'department': department_info,
            
            'start_date': task.start_date.isoformat() if task.start_date else None,
            'due_date': task.due_date.isoformat() if task.due_date else None,
            'due_in_days': task.days_until_due,
            
            'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
            'actual_hours': float(task.actual_hours),
            
            'labels': labels_data,
            'chat_context': chat_context,
            
            'created_at': task.created_at.isoformat(),
            'updated_at': task.updated_at.isoformat(),
            'last_activity_at': task.last_activity_at.isoformat(),
            
            # Counts
            'comment_count': task.comments.count(),
            'checklist_count': task.checklists.count(),
            'completed_checklist_count': task.checklists.filter(is_completed=True).count(),
            'subtask_count': task.subtasks.count(),
            'completed_subtask_count': task.subtasks.filter(status=TaskStatus.COMPLETED).count(),
        }
        
        tasks_data.append(task_data)
    
    # Get available filters for UI
    available_labels = TaskLabel.objects.filter(organization=organization).values('id', 'name', 'color')
    available_departments = Department.objects.filter(organization=organization).values('id', 'name', 'code')
    
    return Response({
        'success': True,
        'tasks': tasks_data,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total_tasks,
            'has_more': (offset + limit) < total_tasks,
        },
        'filters': {
            'status_options': [{'value': val, 'label': label} for val, label in TaskStatus.choices],
            'priority_options': [{'value': val, 'label': label} for val, label in TaskPriority.choices],
            'labels': list(available_labels),
            'departments': list(available_departments),
        },
    })


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_create_api_view(request):
    """
    Create a new task
    """
    user = request.user
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Extract data from request
    title = request.data.get('title', '').strip()
    description = request.data.get('description', '').strip()
    priority = request.data.get('priority', TaskPriority.NORMAL)
    assigned_to_id = request.data.get('assigned_to')
    department_id = request.data.get('department')
    due_date_str = request.data.get('due_date')
    start_date_str = request.data.get('start_date')
    label_ids = request.data.get('labels', [])
    is_private = request.data.get('is_private', False)
    estimated_hours = request.data.get('estimated_hours')
    parent_task_id = request.data.get('parent_task')
    origin_message_id = request.data.get('origin_message_id')  # For converting from chat
    
    # Validate required fields
    if not title:
        return Response(
            {'success': False, 'error': 'Task title is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate priority
    if priority not in [p.value for p in TaskPriority]:
        priority = TaskPriority.NORMAL
    
    # Parse dates
    due_date = None
    if due_date_str:
        try:
            due_date = timezone.datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return Response(
                {'success': False, 'error': 'Invalid due date format. Use ISO format'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    start_date = None
    if start_date_str:
        try:
            start_date = timezone.datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return Response(
                {'success': False, 'error': 'Invalid start date format. Use ISO format'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    try:
        # Get assigned user
        assigned_to = None
        if assigned_to_id:
            try:
                assigned_to = User.objects.get(uid=assigned_to_id, organization=organization)
            except User.DoesNotExist:
                return Response(
                    {'success': False, 'error': 'Assigned user not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Get department
        department = None
        if department_id:
            try:
                department = Department.objects.get(id=department_id, organization=organization)
            except Department.DoesNotExist:
                return Response(
                    {'success': False, 'error': 'Department not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Get parent task
        parent_task = None
        if parent_task_id:
            try:
                parent_task = Task.objects.get(id=parent_task_id, organization=organization)
            except Task.DoesNotExist:
                return Response(
                    {'success': False, 'error': 'Parent task not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Get origin message (if converting from chat)
        origin_message = None
        if origin_message_id:
            try:
                origin_message = ChatMessage.objects.get(id=origin_message_id)
                # Verify user has access to this message
                if origin_message.channel:
                    if not ChannelMembership.objects.filter(
                        channel=origin_message.channel, 
                        user=user
                    ).exists():
                        return Response(
                            {'success': False, 'error': 'You do not have access to this message'},
                            status=status.HTTP_403_FORBIDDEN
                        )
                elif origin_message.direct_message:
                    if not origin_message.direct_message.participants.filter(uid=user.uid).exists():
                        return Response(
                            {'success': False, 'error': 'You are not a participant in this conversation'},
                            status=status.HTTP_403_FORBIDDEN
                        )
            except ChatMessage.DoesNotExist:
                return Response(
                    {'success': False, 'error': 'Message not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Create the task
        task = Task.objects.create(
            organization=organization,
            title=title,
            description=description,
            priority=priority,
            created_by=user,
            assigned_to=assigned_to,
            department=department,
            parent_task=parent_task,
            origin_message=origin_message,
            due_date=due_date,
            start_date=start_date,
            is_private=is_private,
            estimated_hours=estimated_hours,
        )
        
        # Add labels
        if label_ids:
            labels = TaskLabel.objects.filter(id__in=label_ids, organization=organization)
            task.labels.set(labels)
        
        # Link to chat context if applicable
        if origin_message:
            if origin_message.channel:
                task.related_channel = origin_message.channel
            elif origin_message.direct_message:
                task.related_dm = origin_message.direct_message
            task.save()
        
        # Create a notification in chat if task was created from chat
        if origin_message:
            # Create system message in chat
            system_message_content = f"✅ **Task Created**\n**Title:** {title}\n**Priority:** {task.get_priority_display()}"
            
            if assigned_to:
                assignee_name = display_name_for(assigned_to)
                system_message_content += f"\n**Assigned to:** {assignee_name}"
            
            if due_date:
                system_message_content += f"\n**Due:** {due_date.strftime('%b %d, %Y')}"
            
            system_message = ChatMessage.objects.create(
                channel=origin_message.channel if origin_message.channel else None,
                direct_message=origin_message.direct_message if origin_message.direct_message else None,
                sender=user,
                content=system_message_content,
                message_type='task_created',
                related_task=task
            )
            _broadcast_chat_message(system_message)
        
        # Create notification for assigned user
        if assigned_to and assigned_to != user:
            TaskNotification.objects.create(
                user=assigned_to,
                task=task,
                notification_type='assignment',
                title=f'Task Assigned: {title}',
                message=f'{display_name_for(user)} assigned you a new task'
            )
        
        # Get formatted task data for response
        task_data = _format_task_for_response(task, request)
        
        return Response({
            'success': True,
            'message': 'Task created successfully',
            'task': task_data,
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_detail_api_view(request, task_id):
    """
    Get task details including comments, checklists, etc.
    """
    user = request.user
    
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Task not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions
    if task.is_private:
        if not (user.is_admin or user.is_pastor or user.is_owner or 
                task.created_by == user or task.assigned_to == user):
            return Response(
                {'success': False, 'error': 'You do not have permission to view this task'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    
    # Check organization access
    if task.organization != user.organization:
        return Response(
            {'success': False, 'error': 'Task not found in your organization'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Get task data
    task_data = _format_task_for_response(task, request)
    
    # Get comments
    comments = TaskComment.objects.filter(task=task).select_related('author').order_by('created_at')
    comments_data = []
    
    for comment in comments:
        author_name = display_name_for(comment.author)
        author_avatar = None
        try:
            if hasattr(comment.author, 'member_profile') and comment.author.member_profile.photo:
                author_avatar = request.build_absolute_uri(comment.author.member_profile.photo.url)
        except AttributeError:
            pass
        
        comments_data.append({
            'id': str(comment.id),
            'content': comment.content,
            'author': {
                'id': str(comment.author.uid),
                'name': author_name,
                'avatar': author_avatar,
                'role': get_user_role(comment.author),
            },
            'created_at': comment.created_at.isoformat(),
            'updated_at': comment.updated_at.isoformat(),
        })
    
    # Get checklists
    checklists = TaskChecklist.objects.filter(task=task).order_by('order')
    checklists_data = []
    
    for checklist in checklists:
        completed_by_info = None
        if checklist.completed_by:
            completed_by_name = display_name_for(checklist.completed_by)
            completed_by_avatar = None
            try:
                if hasattr(checklist.completed_by, 'member_profile') and checklist.completed_by.member_profile.photo:
                    completed_by_avatar = request.build_absolute_uri(checklist.completed_by.member_profile.photo.url)
            except AttributeError:
                pass
            
            completed_by_info = {
                'id': str(checklist.completed_by.uid),
                'name': completed_by_name,
                'avatar': completed_by_avatar,
            }
        
        checklists_data.append({
            'id': str(checklist.id),
            'title': checklist.title,
            'is_completed': checklist.is_completed,
            'completed_by': completed_by_info,
            'completed_at': checklist.completed_at.isoformat() if checklist.completed_at else None,
            'order': checklist.order,
            'created_at': checklist.created_at.isoformat(),
        })
    
    # Get subtasks
    subtasks = task.subtasks.all().select_related('created_by', 'assigned_to').order_by('-priority', 'due_date')
    subtasks_data = []
    
    for subtask in subtasks:
        subtask_info = {
            'id': str(subtask.id),
            'title': subtask.title,
            'status': subtask.status,
            'status_label': subtask.get_status_display(),
            'priority': subtask.priority,
            'priority_label': subtask.get_priority_display(),
            'progress': subtask.progress,
            'assigned_to': {
                'id': str(subtask.assigned_to.uid) if subtask.assigned_to else None,
                'name': display_name_for(subtask.assigned_to) if subtask.assigned_to else None,
            } if subtask.assigned_to else None,
        }
        subtasks_data.append(subtask_info)
    
    # Get time logs
    time_logs = TaskTimeLog.objects.filter(task=task).select_related('user').order_by('-start_time')
    time_logs_data = []
    
    for time_log in time_logs:
        user_name = display_name_for(time_log.user)
        user_avatar = None
        try:
            if hasattr(time_log.user, 'member_profile') and time_log.user.member_profile.photo:
                user_avatar = request.build_absolute_uri(time_log.user.member_profile.photo.url)
        except AttributeError:
            pass
        
        time_logs_data.append({
            'id': str(time_log.id),
            'description': time_log.description,
            'user': {
                'id': str(time_log.user.uid),
                'name': user_name,
                'avatar': user_avatar,
            },
            'start_time': time_log.start_time.isoformat(),
            'end_time': time_log.end_time.isoformat() if time_log.end_time else None,
            'duration': time_log.duration,
            'is_running': time_log.is_running,
            'created_at': time_log.created_at.isoformat(),
        })
    
    # Get related chat messages if any
    chat_messages_data = []
    if task.origin_message or task.chat_references.exists():
        chat_messages = []
        
        # Add origin message
        if task.origin_message:
            chat_messages.append(task.origin_message)
        
        # Add referenced messages
        chat_messages.extend(task.chat_references.all())
        
        for chat_msg in chat_messages:
            sender_name = display_name_for(chat_msg.sender)
            sender_avatar = None
            try:
                if hasattr(chat_msg.sender, 'member_profile') and chat_msg.sender.member_profile.photo:
                    sender_avatar = request.build_absolute_uri(chat_msg.sender.member_profile.photo.url)
            except AttributeError:
                pass
            
            chat_context = None
            if chat_msg.channel:
                chat_context = {
                    'type': 'channel',
                    'id': str(chat_msg.channel.id),
                    'name': chat_msg.channel.name,
                }
            elif chat_msg.direct_message:
                chat_context = {
                    'type': 'dm',
                    'id': str(chat_msg.direct_message.id),
                }
            
            chat_messages_data.append({
                'id': str(chat_msg.id),
                'content': chat_msg.content,
                'sender': {
                    'id': str(chat_msg.sender.uid),
                    'name': sender_name,
                    'avatar': sender_avatar,
                },
                'created_at': chat_msg.created_at.isoformat(),
                'context': chat_context,
                'is_origin_message': chat_msg == task.origin_message,
            })
    
    # Get related chat channels/DMs for linking
    related_chats = []
    if task.related_channel:
        related_chats.append({
            'type': 'channel',
            'id': str(task.related_channel.id),
            'name': task.related_channel.name,
            'description': task.related_channel.description,
        })
    if task.related_dm:
        participants = task.related_dm.participants.exclude(uid=user.uid)
        participant_names = [display_name_for(p) for p in participants]
        related_chats.append({
            'type': 'dm',
            'id': str(task.related_dm.id),
            'name': ', '.join(participant_names) if participant_names else 'Direct Message',
            'participant_count': task.related_dm.participants.count(),
        })
    
    # Get participants (users involved in task)
    participants_data = []
    participants_set = set()
    
    # Add creator
    participants_set.add(task.created_by)
    
    # Add assignee
    if task.assigned_to:
        participants_set.add(task.assigned_to)
    
    # Add comment authors
    for comment in comments:
        participants_set.add(comment.author)
    
    # Add checklist completers
    for checklist in checklists:
        if checklist.completed_by:
            participants_set.add(checklist.completed_by)
    
    # Add time log users
    for time_log in time_logs:
        participants_set.add(time_log.user)
    
    # Format participants
    for participant in participants_set:
        if participant:
            participant_name = display_name_for(participant)
            participant_avatar = None
            try:
                if hasattr(participant, 'member_profile') and participant.member_profile.photo:
                    participant_avatar = request.build_absolute_uri(participant.member_profile.photo.url)
            except AttributeError:
                pass
            
            participants_data.append({
                'id': str(participant.uid),
                'name': participant_name,
                'avatar': participant_avatar,
                'role': get_user_role(participant),
                'is_creator': participant == task.created_by,
                'is_assignee': participant == task.assigned_to,
            })
    
    return Response({
        'success': True,
        'task': task_data,
        'comments': comments_data,
        'checklists': checklists_data,
        'subtasks': subtasks_data,
        'time_logs': time_logs_data,
        'chat_messages': chat_messages_data,
        'related_chats': related_chats,
        'participants': participants_data,
        'permissions': {
            'can_edit': user.is_admin or user.is_pastor or user.is_owner or task.created_by == user,
            'can_assign': user.is_admin or user.is_pastor or user.is_owner or task.created_by == user,
            'can_delete': user.is_admin or user.is_pastor or user.is_owner or task.created_by == user,
            'can_update_progress': user == task.assigned_to or user == task.created_by or user.is_admin or user.is_pastor or user.is_owner,
        }
    })


@api_view(['PUT', 'PATCH'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_update_api_view(request, task_id):
    """
    Update a task
    """
    user = request.user
    
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Task not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions
    if not (user.is_admin or user.is_pastor or user.is_owner or task.created_by == user):
        return Response(
            {'success': False, 'error': 'You do not have permission to edit this task'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Check organization access
    if task.organization != user.organization:
        return Response(
            {'success': False, 'error': 'Task not found in your organization'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Track changes for notifications
    old_status = task.status
    old_assigned_to = task.assigned_to
    old_priority = task.priority
    
    # Update fields
    update_fields = {}
    
    if 'title' in request.data:
        task.title = request.data.get('title', '').strip()
    
    if 'description' in request.data:
        task.description = request.data.get('description', '').strip()
    
    if 'priority' in request.data:
        priority = request.data.get('priority')
        if priority in [p.value for p in TaskPriority]:
            task.priority = priority
    
    if 'status' in request.data:
        status_val = request.data.get('status')
        if status_val in [s[0] for s in TaskStatus.choices]:
            task.status = status_val
    
    if 'progress' in request.data:
        progress = request.data.get('progress')
        if progress is not None:
            try:
                progress_int = int(progress)
                if 0 <= progress_int <= 100:
                    task.progress = progress_int
            except ValueError:
                pass
    
    if 'assigned_to' in request.data:
        assigned_to_id = request.data.get('assigned_to')
        if assigned_to_id:
            try:
                assigned_to = User.objects.get(uid=assigned_to_id, organization=user.organization)
                task.assigned_to = assigned_to
            except User.DoesNotExist:
                return Response(
                    {'success': False, 'error': 'Assigned user not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            task.assigned_to = None
    
    if 'department' in request.data:
        department_id = request.data.get('department')
        if department_id:
            try:
                department = Department.objects.get(id=department_id, organization=user.organization)
                task.department = department
            except Department.DoesNotExist:
                return Response(
                    {'success': False, 'error': 'Department not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            task.department = None
    
    if 'due_date' in request.data:
        due_date_str = request.data.get('due_date')
        if due_date_str:
            try:
                task.due_date = timezone.datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return Response(
                    {'success': False, 'error': 'Invalid due date format. Use ISO format'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            task.due_date = None
    
    if 'start_date' in request.data:
        start_date_str = request.data.get('start_date')
        if start_date_str:
            try:
                task.start_date = timezone.datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return Response(
                    {'success': False, 'error': 'Invalid start date format. Use ISO format'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            task.start_date = None
    
    if 'estimated_hours' in request.data:
        estimated_hours = request.data.get('estimated_hours')
        if estimated_hours is not None:
            try:
                task.estimated_hours = Decimal(estimated_hours)
            except (ValueError, TypeError):
                pass
    
    if 'is_private' in request.data:
        task.is_private = bool(request.data.get('is_private'))
    
    # Save the task
    task.save()
    
    # Update labels if provided
    if 'labels' in request.data:
        label_ids = request.data.get('labels', [])
        labels = TaskLabel.objects.filter(id__in=label_ids, organization=user.organization)
        task.labels.set(labels)
    
    # Send notifications for changes
    if old_status != task.status:
        # Notify creator and assignee about status change
        recipients = {task.created_by}
        if task.assigned_to:
            recipients.add(task.assigned_to)
        
        for recipient in recipients:
            if recipient != user:  # Don't notify the person who made the change
                TaskNotification.objects.create(
                    user=recipient,
                    task=task,
                    notification_type='completion' if task.status == TaskStatus.COMPLETED else 'progress',
                    title=f'Task Status Updated: {task.title}',
                    message=f'Task status changed from {old_status} to {task.status}'
                )
    
    if old_assigned_to != task.assigned_to:
        # Notify new assignee
        if task.assigned_to and task.assigned_to != user:
            TaskNotification.objects.create(
                user=task.assigned_to,
                task=task,
                notification_type='assignment',
                title=f'Task Assigned: {task.title}',
                message=f'{display_name_for(user)} assigned you this task'
            )
        
        # Notify old assignee if they were removed
        if old_assigned_to and old_assigned_to != user and old_assigned_to != task.assigned_to:
            TaskNotification.objects.create(
                user=old_assigned_to,
                task=task,
                notification_type='system',
                title=f'Task Reassigned: {task.title}',
                message=f'You are no longer assigned to this task'
            )
    
    if old_priority != task.priority and task.assigned_to and task.assigned_to != user:
        # Notify assignee about priority change
        TaskNotification.objects.create(
            user=task.assigned_to,
            task=task,
            notification_type='system',
            title=f'Task Priority Updated: {task.title}',
            message=f'Task priority changed to {task.get_priority_display()}'
        )
    
    # Get updated task data
    task_data = _format_task_for_response(task, request)
    
    return Response({
        'success': True,
        'message': 'Task updated successfully',
        'task': task_data,
    })


@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_delete_api_view(request, task_id):
    """
    Delete a task
    """
    user = request.user
    
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Task not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions
    if not (user.is_admin or user.is_pastor or user.is_owner or task.created_by == user):
        return Response(
            {'success': False, 'error': 'You do not have permission to delete this task'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Check organization access
    if task.organization != user.organization:
        return Response(
            {'success': False, 'error': 'Task not found in your organization'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    task_title = task.title
    task.delete()
    
    return Response({
        'success': True,
        'message': f'Task "{task_title}" deleted successfully',
    })


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_add_comment_api_view(request, task_id):
    """
    Add comment to a task
    """
    user = request.user
    
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Task not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions
    if task.is_private:
        if not (user.is_admin or user.is_pastor or user.is_owner or 
                task.created_by == user or task.assigned_to == user):
            return Response(
                {'success': False, 'error': 'You do not have permission to comment on this task'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    
    # Check organization access
    if task.organization != user.organization:
        return Response(
            {'success': False, 'error': 'Task not found in your organization'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    content = request.data.get('content', '').strip()
    if not content:
        return Response(
            {'success': False, 'error': 'Comment content is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create comment
    comment = TaskComment.objects.create(
        task=task,
        author=user,
        content=content
    )
    
    # Get comment data for response
    author_name = display_name_for(user)
    author_avatar = None
    try:
        if hasattr(user, 'member_profile') and user.member_profile.photo:
            author_avatar = request.build_absolute_uri(user.member_profile.photo.url)
    except AttributeError:
        pass
    
    comment_data = {
        'id': str(comment.id),
        'content': comment.content,
        'author': {
            'id': str(user.uid),
            'name': author_name,
            'avatar': author_avatar,
            'role': get_user_role(user),
        },
        'created_at': comment.created_at.isoformat(),
        'updated_at': comment.updated_at.isoformat(),
    }
    
    # Send notifications to task participants (excluding commenter)
    participants = set()
    participants.add(task.created_by)
    if task.assigned_to:
        participants.add(task.assigned_to)
    
    # Add previous comment authors
    previous_comments = TaskComment.objects.filter(task=task).exclude(author=user)
    for prev_comment in previous_comments:
        participants.add(prev_comment.author)
    
    for participant in participants:
        if participant and participant != user:
            TaskNotification.objects.create(
                user=participant,
                task=task,
                notification_type='comment',
                title=f'New Comment: {task.title}',
                message=f'{author_name} commented on task: {task.title}'
            )
    
    return Response({
        'success': True,
        'message': 'Comment added successfully',
        'comment': comment_data,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_add_checklist_api_view(request, task_id):
    """
    Add checklist item to a task
    """
    user = request.user
    
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Task not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions
    if not (user.is_admin or user.is_pastor or user.is_owner or 
            task.created_by == user or task.assigned_to == user):
        return Response(
            {'success': False, 'error': 'You do not have permission to add checklist items'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Check organization access
    if task.organization != user.organization:
        return Response(
            {'success': False, 'error': 'Task not found in your organization'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    title = request.data.get('title', '').strip()
    if not title:
        return Response(
            {'success': False, 'error': 'Checklist title is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create checklist item
    checklist = TaskChecklist.objects.create(
        task=task,
        title=title
    )
    
    checklist_data = {
        'id': str(checklist.id),
        'title': checklist.title,
        'is_completed': checklist.is_completed,
        'order': checklist.order,
        'created_at': checklist.created_at.isoformat(),
    }
    
    return Response({
        'success': True,
        'message': 'Checklist item added successfully',
        'checklist': checklist_data,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_toggle_checklist_api_view(request, task_id, checklist_id):
    """
    Toggle checklist item completion
    """
    user = request.user
    
    try:
        task = Task.objects.get(id=task_id)
        checklist = TaskChecklist.objects.get(id=checklist_id, task=task)
    except (Task.DoesNotExist, TaskChecklist.DoesNotExist):
        return Response(
            {'success': False, 'error': 'Task or checklist item not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check organization access
    if task.organization != user.organization:
        return Response(
            {'success': False, 'error': 'Task not found in your organization'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Toggle completion
    checklist.is_completed = not checklist.is_completed
    
    if checklist.is_completed:
        checklist.completed_by = user
        checklist.completed_at = timezone.now()
    else:
        checklist.completed_by = None
        checklist.completed_at = None
    
    checklist.save()
    
    # Update task progress based on checklist completion
    total_checklists = task.checklists.count()
    completed_checklists = task.checklists.filter(is_completed=True).count()
    
    if total_checklists > 0:
        new_progress = int((completed_checklists / total_checklists) * 100)
        if new_progress != task.progress:
            task.progress = new_progress
            task.save()
    
    checklist_data = {
        'id': str(checklist.id),
        'title': checklist.title,
        'is_completed': checklist.is_completed,
        'completed_by': {
            'id': str(checklist.completed_by.uid) if checklist.completed_by else None,
            'name': display_name_for(checklist.completed_by) if checklist.completed_by else None,
        },
        'completed_at': checklist.completed_at.isoformat() if checklist.completed_at else None,
        'order': checklist.order,
    }
    
    return Response({
        'success': True,
        'message': 'Checklist item updated',
        'checklist': checklist_data,
        'task_progress': task.progress,
    })


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_start_timer_api_view(request, task_id):
    """
    Start time tracking for a task
    """
    user = request.user
    
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Task not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check permissions
    if not (user.is_admin or user.is_pastor or user.is_owner or 
            task.created_by == user or task.assigned_to == user):
        return Response(
            {'success': False, 'error': 'You do not have permission to track time for this task'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Check organization access
    if task.organization != user.organization:
        return Response(
            {'success': False, 'error': 'Task not found in your organization'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Stop any running timers for this user
    TaskTimeLog.objects.filter(
        user=user,
        is_running=True
    ).update(is_running=False, end_time=timezone.now())
    
    # Start new timer
    description = request.data.get('description', 'Work on task')
    timer = TaskTimeLog.objects.create(
        task=task,
        user=user,
        description=description,
        start_time=timezone.now(),
        is_running=True
    )
    
    timer_data = {
        'id': str(timer.id),
        'description': timer.description,
        'user': {
            'id': str(user.uid),
            'name': display_name_for(user),
        },
        'start_time': timer.start_time.isoformat(),
        'is_running': timer.is_running,
    }
    
    return Response({
        'success': True,
        'message': 'Timer started',
        'timer': timer_data,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_stop_timer_api_view(request, task_id):
    """
    Stop time tracking for a task
    """
    user = request.user
    
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Task not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check organization access
    if task.organization != user.organization:
        return Response(
            {'success': False, 'error': 'Task not found in your organization'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Find active timer for this user and task
    try:
        timer = TaskTimeLog.objects.get(
            task=task,
            user=user,
            is_running=True
        )
    except TaskTimeLog.DoesNotExist:
        return Response(
            {'success': False, 'error': 'No active timer found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Stop timer
    timer.is_running = False
    timer.end_time = timezone.now()
    timer.save()
    
    # Update task's actual hours
    if timer.duration:
        task.actual_hours += Decimal(str(timer.duration))
        task.save()
    
    timer_data = {
        'id': str(timer.id),
        'description': timer.description,
        'duration': timer.duration,
        'start_time': timer.start_time.isoformat(),
        'end_time': timer.end_time.isoformat() if timer.end_time else None,
        'is_running': timer.is_running,
    }
    
    return Response({
        'success': True,
        'message': 'Timer stopped',
        'timer': timer_data,
        'task_actual_hours': float(task.actual_hours),
    })


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def convert_message_to_task_api_view(request):
    """
    Convert a chat message to a task
    This is the main endpoint for converting messages to tasks
    """
    user = request.user
    
    # Get message ID
    message_id = request.data.get('message_id')
    if not message_id:
        return Response(
            {'success': False, 'error': 'Message ID is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        message = ChatMessage.objects.get(id=message_id)
    except ChatMessage.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Message not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user has access to this message
    if message.channel:
        if not ChannelMembership.objects.filter(
            channel=message.channel, 
            user=user
        ).exists():
            return Response(
                {'success': False, 'error': 'You do not have access to this message'},
                status=status.HTTP_403_FORBIDDEN
            )
    elif message.direct_message:
        if not message.direct_message.participants.filter(uid=user.uid).exists():
            return Response(
                {'success': False, 'error': 'You are not a participant in this conversation'},
                status=status.HTTP_403_FORBIDDEN
            )
    
    # Check if message is already converted
    if hasattr(message, 'converted_to_task') and message.converted_to_task:
        return Response(
            {'success': False, 'error': 'This message has already been converted to a task'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get task details from request (or use suggestions)
    title = request.data.get('title')
    assigned_to_id = request.data.get('assigned_to')
    due_date_str = request.data.get('due_date')
    priority_str = request.data.get('priority')
    department_id = request.data.get('department')
    label_ids = request.data.get('labels', [])
    parent_task_id = request.data.get('parent_task')
    link_channel = str(request.data.get('link_channel', 'true')).lower() != 'false'
    
    # Parse assigned_to
    assigned_to = None
    if assigned_to_id:
        try:
            assigned_to = User.objects.get(
                uid=assigned_to_id,
                organization=user.organization
            )
        except User.DoesNotExist:
            return Response(
                {'success': False, 'error': 'Assigned user not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    # Parse due date
    due_date = None
    if due_date_str:
        try:
            due_date = timezone.datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return Response(
                {'success': False, 'error': 'Invalid due date format. Use ISO format'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    # Parse priority
    priority = TaskPriority.NORMAL
    if priority_str:
        if isinstance(priority_str, int):
            priority = priority_str
        elif priority_str.lower() == 'low':
            priority = TaskPriority.LOW
        elif priority_str.lower() == 'normal':
            priority = TaskPriority.NORMAL
        elif priority_str.lower() == 'high':
            priority = TaskPriority.HIGH
        elif priority_str.lower() == 'urgent':
            priority = TaskPriority.URGENT
        elif priority_str.lower() == 'critical':
            priority = TaskPriority.CRITICAL
    
    # Parse parent task
    parent_task = None
    if parent_task_id:
        try:
            parent_task = Task.objects.get(id=parent_task_id, organization=user.organization)
        except Task.DoesNotExist:
            return Response(
                {'success': False, 'error': 'Parent task not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    # Parse department
    department = None
    if department_id:
        try:
            department = Department.objects.get(
                id=department_id,
                organization=user.organization
            )
        except Department.DoesNotExist:
            return Response(
                {'success': False, 'error': 'Department not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    # Generate title from message if not provided
    if not title:
        title = message.content[:100]
        if len(message.content) > 100:
            title += "..."
    
    # Default assignee to DM recipient if not provided
    if not assigned_to and message.direct_message:
        assigned_to = message.direct_message.participants.exclude(uid=user.uid).first()
    
    # Default department from assignee's first department
    if not department and assigned_to and hasattr(assigned_to, 'member_profile'):
        first_dept = assigned_to.member_profile.departments.first() if hasattr(assigned_to.member_profile, 'departments') else None
        if first_dept:
            department = first_dept
    
    # Create task from message
    try:
        used_model_helper = False
        # Use the method on Message model if it exists
        if hasattr(message, 'convert_to_task'):
            task = message.convert_to_task(
                title=title,
                assigned_to=assigned_to,
                due_date=due_date,
                priority=priority,
                department=department,
                parent_task=parent_task,
                link_channel=link_channel,
                description=message.content
            )
            used_model_helper = True
        else:
            # Fallback: Create task manually
            task = Task.objects.create(
                organization=user.organization,
                title=title,
                description=message.content,
                created_by=user,
                assigned_to=assigned_to,
                department=department,
                parent_task=parent_task,
                origin_message=message,
                priority=priority,
                due_date=due_date,
                # Link to chat context
                related_channel=message.channel if link_channel else None,
                related_dm=message.direct_message,
            )
        
        # Add labels
        if label_ids:
            labels = TaskLabel.objects.filter(id__in=label_ids, organization=user.organization)
            task.labels.set(labels)
        
        # Reuse the original chat message instead of adding a duplicate entry (only when fallback used)
        if not used_model_helper:
            system_message_content = f"✅ **Task Created**\n**Title:** {title}\n**Priority:** {task.get_priority_display()}"
            
            if assigned_to:
                assignee_name = display_name_for(assigned_to)
                system_message_content += f"\n**Assigned to:** {assignee_name}"
            
            if due_date:
                system_message_content += f"\n**Due:** {due_date.strftime('%b %d, %Y')}"
            
            message.content = system_message_content
            message.message_type = 'task_created'
            message.related_task = task
            message.save(update_fields=['content', 'message_type', 'related_task'])
            _broadcast_chat_message(message)
        
        # Get task data for response
        task_data = _format_task_for_response(task, request)
        
        return Response({
            'success': True,
            'message': 'Message converted to task successfully',
            'task': task_data,
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'success': False, 'error': f'Failed to create task: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_message_task_suggestions_api_view(request, message_id):
    """
    Get task conversion suggestions for a message
    """
    user = request.user
    
    try:
        message = ChatMessage.objects.get(id=message_id)
    except ChatMessage.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Message not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user has access to this message
    if message.channel:
        if not ChannelMembership.objects.filter(
            channel=message.channel, 
            user=user
        ).exists():
            return Response(
                {'success': False, 'error': 'You do not have access to this message'},
                status=status.HTTP_403_FORBIDDEN
            )
    elif message.direct_message:
        if not message.direct_message.participants.filter(uid=user.uid).exists():
            return Response(
                {'success': False, 'error': 'You are not a participant in this conversation'},
                status=status.HTTP_403_FORBIDDEN
            )
    
    # Get suggestions from message if method exists
    suggestions = {}
    if hasattr(message, 'get_conversion_suggestions'):
        suggestions = message.get_conversion_suggestions()
    else:
        # Basic suggestions
        content = message.content
        suggestions = {
            'title': content[:100] + "..." if len(content) > 100 else content,
            'priority': 'normal',
            'due_date': None,
            'assignee_suggestions': [],
            'keywords': [],
        }
    
    # Add assignee suggestions from mentions
    from chat.models import Mention
    mentions = Mention.objects.filter(message=message)
    assignee_suggestions = []
    
    for mention in mentions:
        if mention.user and mention.user.organization == user.organization:
            assignee_name = display_name_for(mention.user)
            assignee_avatar = None
            try:
                if hasattr(mention.user, 'member_profile') and mention.user.member_profile.photo:
                    assignee_avatar = request.build_absolute_uri(mention.user.member_profile.photo.url)
            except AttributeError:
                pass
            
            assignee_suggestions.append({
                'id': str(mention.user.uid),
                'name': assignee_name,
                'avatar': assignee_avatar,
                'role': get_user_role(mention.user),
                'reason': 'mentioned in message',
                'confidence': 'high'
            })
    
    suggestions['assignee_suggestions'] = assignee_suggestions
    
    return Response({
        'success': True,
        'suggestions': suggestions,
        'message_preview': message.content[:200] + "..." if len(message.content) > 200 else message.content,
    })


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_labels_api_view(request):
    """
    Get all task labels for organization
    """
    user = request.user
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    labels = TaskLabel.objects.filter(organization=organization).order_by('name')
    
    labels_data = []
    for label in labels:
        labels_data.append({
            'id': str(label.id),
            'name': label.name,
            'color': label.color,
            'description': label.description,
            'created_by': {
                'id': str(label.created_by.uid) if label.created_by else None,
                'name': display_name_for(label.created_by) if label.created_by else None,
            },
            'created_at': label.created_at.isoformat(),
            'task_count': label.tasks.count(),
        })
    
    return Response({
        'success': True,
        'labels': labels_data,
    })


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def create_task_label_api_view(request):
    """
    Create a new task label
    """
    user = request.user
    organization = user.organization
    
    if not organization:
        return Response(
            {'success': False, 'error': 'No organization assigned'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    name = request.data.get('name', '').strip()
    color = request.data.get('color', '#6B7280')
    description = request.data.get('description', '').strip()
    
    if not name:
        return Response(
            {'success': False, 'error': 'Label name is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if label already exists
    if TaskLabel.objects.filter(organization=organization, name=name).exists():
        return Response(
            {'success': False, 'error': f'Label "{name}" already exists'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        label = TaskLabel.objects.create(
            organization=organization,
            name=name,
            color=color,
            description=description,
            created_by=user
        )
        
        label_data = {
            'id': str(label.id),
            'name': label.name,
            'color': label.color,
            'description': label.description,
            'created_by': {
                'id': str(user.uid),
                'name': display_name_for(user),
            },
            'created_at': label.created_at.isoformat(),
        }
        
        return Response({
            'success': True,
            'message': 'Label created successfully',
            'label': label_data,
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'success': False, 'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def task_notifications_api_view(request):
    """
    Get task notifications for current user
    """
    user = request.user
    
    # Get query parameters
    unread_only = request.query_params.get('unread_only', '').lower() == 'true'
    limit = int(request.query_params.get('limit', 20))
    
    notifications_qs = TaskNotification.objects.filter(user=user)
    
    if unread_only:
        notifications_qs = notifications_qs.filter(is_read=False)
    
    notifications = notifications_qs.select_related('task').order_by('-created_at')[:limit]
    
    notifications_data = []
    for notification in notifications:
        # Get task info
        task_info = None
        if notification.task:
            task_info = {
                'id': str(notification.task.id),
                'title': notification.task.title,
                'status': notification.task.status,
                'priority': notification.task.priority,
            }
        
        notifications_data.append({
            'id': str(notification.id),
            'type': notification.notification_type,
            'title': notification.title,
            'message': notification.message,
            'task': task_info,
            'is_read': notification.is_read,
            'is_important': notification.is_important,
            'created_at': notification.created_at.isoformat(),
        })
    
    # Get unread count
    unread_count = TaskNotification.objects.filter(user=user, is_read=False).count()
    
    return Response({
        'success': True,
        'notifications': notifications_data,
        'unread_count': unread_count,
    })


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_notification_read_api_view(request, notification_id):
    """
    Mark a notification as read
    """
    user = request.user
    
    try:
        notification = TaskNotification.objects.get(id=notification_id, user=user)
    except TaskNotification.DoesNotExist:
        return Response(
            {'success': False, 'error': 'Notification not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    notification.is_read = True
    notification.save()
    
    return Response({
        'success': True,
        'message': 'Notification marked as read',
    })


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read_api_view(request):
    """
    Mark all notifications as read
    """
    user = request.user
    
    updated_count = TaskNotification.objects.filter(user=user, is_read=False).update(is_read=True)
    
    return Response({
        'success': True,
        'message': f'Marked {updated_count} notifications as read',
        'updated_count': updated_count,
    })


# Helper functions

def _format_task_for_response(task, request):
    """Format a task object for API response"""
    # Get creator info
    creator_name = display_name_for(task.created_by)
    creator_avatar = None
    try:
        if hasattr(task.created_by, 'member_profile') and task.created_by.member_profile.photo:
            creator_avatar = request.build_absolute_uri(task.created_by.member_profile.photo.url)
    except AttributeError:
        pass
    
    # Get assignee info
    assignee_info = None
    if task.assigned_to:
        assignee_name = display_name_for(task.assigned_to)
        assignee_avatar = None
        try:
            if hasattr(task.assigned_to, 'member_profile') and task.assigned_to.member_profile.photo:
                assignee_avatar = request.build_absolute_uri(task.assigned_to.member_profile.photo.url)
        except AttributeError:
            pass
        
        assignee_info = {
            'id': str(task.assigned_to.uid),
            'name': assignee_name,
            'avatar': assignee_avatar,
            'role': get_user_role(task.assigned_to),
        }
    
    # Get department info
    department_info = None
    if task.department:
        department_info = {
            'id': str(task.department.id),
            'name': task.department.name,
            'code': task.department.code,
        }
    
    # Get labels
    labels_data = []
    for label in task.labels.all():
        labels_data.append({
            'id': str(label.id),
            'name': label.name,
            'color': label.color,
        })
    
    # Get chat context if exists
    chat_context = None
    if task.origin_message:
        chat_context = {
            'type': 'channel' if task.origin_message.channel else 'dm',
            'id': str(task.origin_message.channel.id if task.origin_message.channel else task.origin_message.direct_message.id),
            'message_id': str(task.origin_message.id),
            'preview': task.origin_message.content[:100] + '...' if len(task.origin_message.content) > 100 else task.origin_message.content,
        }
    
    # Format task data
    return {
        'id': str(task.id),
        'title': task.title,
        'description': task.description,
        'priority': task.priority,
        'priority_label': task.get_priority_display(),
        'status': task.status,
        'status_label': task.get_status_display(),
        'progress': task.progress,
        'is_overdue': task.is_overdue,
        'is_private': task.is_private,
        
        'created_by': {
            'id': str(task.created_by.uid),
            'name': creator_name,
            'avatar': creator_avatar,
            'role': get_user_role(task.created_by),
        },
        'assigned_to': assignee_info,
        'department': department_info,
        
        'start_date': task.start_date.isoformat() if task.start_date else None,
        'due_date': task.due_date.isoformat() if task.due_date else None,
        'due_in_days': task.days_until_due,
        'completed_at': task.completed_at.isoformat() if task.completed_at else None,
        
        'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
        'actual_hours': float(task.actual_hours),
        
        'labels': labels_data,
        'chat_context': chat_context,
        
        'created_at': task.created_at.isoformat(),
        'updated_at': task.updated_at.isoformat(),
        'last_activity_at': task.last_activity_at.isoformat(),
        
        # Counts
        'comment_count': task.comments.count(),
        'checklist_count': task.checklists.count(),
        'completed_checklist_count': task.checklists.filter(is_completed=True).count(),
        'subtask_count': task.subtasks.count(),
        'completed_subtask_count': task.subtasks.filter(status=TaskStatus.COMPLETED).count(),
    }


# -------------------------------
# Web widget (session-auth) views
# -------------------------------

@login_required
def task_widget_summary_view(request):
    """Lightweight task summary for sidebar/widget"""
    org = getattr(request.user, "organization", None)
    if not org:
        return JsonResponse({"error": "No organization assigned"}, status=403)

    # Get task statistics for the current user
    tasks = Task.objects.filter(organization=org)
    
    # Apply privacy filters
    if not (request.user.is_admin or request.user.is_pastor or request.user.is_owner):
        tasks = tasks.filter(
            Q(is_private=False) |
            Q(created_by=request.user) |
            Q(assigned_to=request.user)
        )
    
    # Get counts
    my_assigned = tasks.filter(assigned_to=request.user).count()
    my_active = tasks.filter(
        assigned_to=request.user,
        status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS]
    ).count()
    
    overdue = tasks.filter(
        due_date__lt=timezone.now(),
        status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS]
    ).count()
    
    high_priority = tasks.filter(
        priority__gte=TaskPriority.HIGH,
        status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS]
    ).count()
    
    return JsonResponse({
        "my_assigned": my_assigned,
        "my_active": my_active,
        "overdue": overdue,
        "high_priority": high_priority,
    })


@login_required
def task_widget_list_view(request):
    """Get tasks for widget display"""
    org = getattr(request.user, "organization", None)
    if not org:
        return JsonResponse({"error": "No organization assigned"}, status=403)

    # Get query params
    limit = int(request.GET.get("limit", 5))
    show_my_tasks = request.GET.get("my_tasks", "").lower() == "true"
    show_overdue = request.GET.get("overdue", "").lower() == "true"
    
    tasks_qs = Task.objects.filter(organization=org)
    
    # Apply privacy filters
    if not (request.user.is_admin or request.user.is_pastor or request.user.is_owner):
        tasks_qs = tasks_qs.filter(
            Q(is_private=False) |
            Q(created_by=request.user) |
            Q(assigned_to=request.user)
        )
    
    # Apply filters
    if show_my_tasks:
        tasks_qs = tasks_qs.filter(assigned_to=request.user)
    
    if show_overdue:
        tasks_qs = tasks_qs.filter(
            due_date__lt=timezone.now(),
            status__in=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS]
        )
    
    # Get tasks
    tasks = tasks_qs.select_related('created_by', 'assigned_to').order_by('-priority', 'due_date')[:limit]
    
    def _display_name(user_obj):
        if hasattr(user_obj, "member_profile") and user_obj.member_profile:
            return user_obj.member_profile.full_name
        return user_obj.email or user_obj.username
    
    tasks_data = []
    for task in tasks:
        assignee_name = _display_name(task.assigned_to) if task.assigned_to else "Unassigned"
        creator_name = _display_name(task.created_by)
        
        tasks_data.append({
            "id": str(task.id),
            "title": task.title,
            "priority": task.priority,
            "priority_label": task.get_priority_display(),
            "status": task.status,
            "status_label": task.get_status_display(),
            "progress": task.progress,
            "assignee": assignee_name,
            "creator": creator_name,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "is_overdue": task.is_overdue,
        })
    
    return JsonResponse({"tasks": tasks_data})


@login_required
@require_http_methods(["GET", "POST"])
def task_widget_create_view(request):
    """Create a task from widget"""
    if request.method == "GET":
        # Return form options
        org = getattr(request.user, "organization", None)
        if not org:
            return JsonResponse({"error": "No organization assigned"}, status=403)
        
        # Get departments
        departments = Department.objects.filter(organization=org).values('id', 'name', 'code')
        
        # Get users for assignment
        users = User.objects.filter(
            organization=org,
            is_active=True
        ).exclude(uid=request.user.uid).order_by('first_name', 'email')
        
        users_data = []
        for user in users:
            display = user.member_profile.full_name if hasattr(user, "member_profile") else (user.email or user.username)
            users_data.append({
                "id": str(user.uid),
                "name": display,
                "email": user.email,
            })
        
        # Get labels
        labels = TaskLabel.objects.filter(organization=org).values('id', 'name', 'color')
        
        return JsonResponse({
            "departments": list(departments),
            "users": users_data,
            "labels": list(labels),
            "priority_options": [{"value": val, "label": label} for val, label in TaskPriority.choices],
        })
    
    elif request.method == "POST":
        # Create task
        org = getattr(request.user, "organization", None)
        if not org:
            return JsonResponse({"error": "No organization assigned"}, status=403)
        
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        priority_raw = request.POST.get("priority", TaskPriority.NORMAL)
        is_private = request.POST.get("is_private", "false").lower() == "true"
        origin_message_id = request.POST.get("origin_message_id")
        related_thread_type = request.POST.get("related_thread_type")
        related_thread_id = request.POST.get("related_thread_id")
        due_date_str = request.POST.get("due_date")
        
        # Allow title to be inferred when converting from a chat message
        if not title and not origin_message_id and not related_thread_id:
            return JsonResponse({"error": "Title is required"}, status=400)
        
        try:
            priority = int(priority_raw)
        except (TypeError, ValueError):
            priority = TaskPriority.NORMAL
        
        # Parse due date (accept date-only or ISO datetime)
        due_date = None
        if due_date_str:
            try:
                due_date = timezone.make_aware(datetime.strptime(due_date_str, "%Y-%m-%d"))
            except Exception:
                try:
                    due_date = timezone.datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                    if timezone.is_naive(due_date):
                        due_date = timezone.make_aware(due_date)
                except Exception:
                    pass
        
        origin_message = None
        related_channel = None
        related_dm = None
        
        if origin_message_id:
            try:
                origin_message = ChatMessage.objects.get(id=origin_message_id)
            except ChatMessage.DoesNotExist:
                return JsonResponse({"error": "Message not found"}, status=404)
            
            if origin_message.channel:
                if not ChannelMembership.objects.filter(channel=origin_message.channel, user=request.user).exists():
                    return JsonResponse({"error": "You do not have access to this message"}, status=403)
                related_channel = origin_message.channel
            elif origin_message.direct_message:
                if not origin_message.direct_message.participants.filter(uid=request.user.uid).exists():
                    return JsonResponse({"error": "You are not a participant in this conversation"}, status=403)
                related_dm = origin_message.direct_message
            
            if not title:
                title = origin_message.content[:100] + ("..." if len(origin_message.content) > 100 else "")
                if not description:
                    description = origin_message.content
        
        # Link to a chat thread even without a specific origin message
        elif related_thread_type and related_thread_id:
            if related_thread_type == "channel":
                try:
                    related_channel = Channel.objects.get(id=related_thread_id, organization=org)
                except Channel.DoesNotExist:
                    return JsonResponse({"error": "Channel not found"}, status=404)
                if not related_channel.is_public and not ChannelMembership.objects.filter(channel=related_channel, user=request.user).exists():
                    return JsonResponse({"error": "Not a member of this channel"}, status=403)
            elif related_thread_type == "dm":
                try:
                    related_dm = DirectMessage.objects.get(id=related_thread_id, organization=org)
                except DirectMessage.DoesNotExist:
                    return JsonResponse({"error": "Conversation not found"}, status=404)
                if not related_dm.participants.filter(uid=request.user.uid).exists():
                    return JsonResponse({"error": "You are not a participant in this conversation"}, status=403)
        
        if not title and (related_channel or related_dm):
            title = related_channel.name if related_channel else "Direct message task"
            if related_channel:
                title = f"Task for #{related_channel.name}"
        
        # Create task
        task = Task.objects.create(
            organization=org,
            title=title,
            description=description,
            priority=priority,
            created_by=request.user,
            is_private=is_private,
            origin_message=origin_message,
            related_channel=related_channel,
            related_dm=related_dm,
            due_date=due_date,
        )
        
        # Handle assignment
        assigned_to = None
        assigned_to_id = request.POST.get("assigned_to")
        if assigned_to_id:
            try:
                assigned_to = User.objects.get(uid=assigned_to_id, organization=org)
                task.assigned_to = assigned_to
                task.save()
            except User.DoesNotExist:
                pass  # Silently ignore if user not found
        
        # Handle department
        department_id = request.POST.get("department")
        if department_id:
            try:
                department = Department.objects.get(id=department_id, organization=org)
                task.department = department
                task.save()
            except Department.DoesNotExist:
                pass
        
        # Let chat participants know when we are linked to a thread
        if related_channel or related_dm:
            summary = f"✅ Task Created\n**Title:** {task.title}\n**Priority:** {task.get_priority_display()}"
            if assigned_to:
                summary += f"\n**Assigned to:** {display_name_for(assigned_to)}"
            if due_date:
                summary += f"\n**Due:** {due_date.strftime('%b %d, %Y')}"
            system_message = ChatMessage.objects.create(
                channel=related_channel,
                direct_message=related_dm,
                sender=request.user,
                content=summary,
                message_type='task_created',
                related_task=task
            )
            _broadcast_chat_message(system_message)
        
        return JsonResponse({
            "success": True,
            "task_id": str(task.id),
            "title": task.title,
            "message": "Task created successfully",
        })


@login_required
def task_widget_parent_options_view(request):
    """Return recent tasks for parent selection (session auth)."""
    org = getattr(request.user, "organization", None)
    if not org:
        return JsonResponse({"error": "No organization assigned"}, status=403)
    
    tasks = Task.objects.filter(organization=org).order_by('-updated_at')[:20]
    
    def _display_name(task):
        prefix = task.get_priority_display()
        title = task.title
        return f"[{prefix}] {title}"
    
    data = [
        {"id": str(t.id), "title": _display_name(t)}
        for t in tasks
    ]
    return JsonResponse({"tasks": data})


@login_required
@require_http_methods(["POST"])
def task_convert_message_widget_view(request):
    """
    Session-auth version of convert_message_to_task_api_view for web chat widget.
    """
    org = getattr(request.user, "organization", None)
    if not org:
        return JsonResponse({"error": "No organization assigned"}, status=403)
    
    message_id = request.POST.get("message_id")
    if not message_id:
        return JsonResponse({"error": "Message ID is required"}, status=400)
    
    try:
        message = ChatMessage.objects.get(id=message_id)
    except ChatMessage.DoesNotExist:
        return JsonResponse({"error": "Message not found"}, status=404)
    
    # Access checks
    if message.channel:
        if not ChannelMembership.objects.filter(channel=message.channel, user=request.user).exists():
            return JsonResponse({"error": "You do not have access to this message"}, status=403)
    elif message.direct_message:
        if not message.direct_message.participants.filter(uid=request.user.uid).exists():
            return JsonResponse({"error": "You are not a participant in this conversation"}, status=403)
    
    # Already converted? Return success so UI can close cleanly.
    if hasattr(message, "converted_to_task") and message.converted_to_task:
        task = message.converted_to_task
        return JsonResponse({
            "success": True,
            "task_id": str(task.id),
            "title": task.title,
            "already_converted": True,
        })
    
    # Parse inputs
    title = (request.POST.get("title") or "").strip()
    due_date_str = request.POST.get("due_date")
    parent_task_id = request.POST.get("parent_task")
    link_channel = str(request.POST.get("link_channel", "true")).lower() != "false"
    
    # Default assignee is DM recipient if not provided
    assigned_to = None
    if message.direct_message:
        assigned_to = message.direct_message.participants.exclude(uid=request.user.uid).first()
    
    # Default department from assignee
    department = None
    if assigned_to and hasattr(assigned_to, "member_profile"):
        dept = getattr(assigned_to.member_profile, "departments", None)
        if dept:
            department = dept.first()
    
    # Parent task
    parent_task = None
    if parent_task_id:
        try:
            parent_task = Task.objects.get(id=parent_task_id, organization=org)
        except Task.DoesNotExist:
            # Fallback: try by title match
            parent_task = Task.objects.filter(organization=org, title__icontains=parent_task_id).order_by('-updated_at').first()
    
    
    # Title fallback
    if not title:
        title = message.content[:100] + ("..." if len(message.content) > 100 else "")
    
    # Due date parsing
    due_date = None
    if due_date_str:
        try:
            due_date = timezone.datetime.fromisoformat(due_date_str)
            if timezone.is_naive(due_date):
                due_date = timezone.make_aware(due_date)
        except Exception:
            pass
    
    try:
        if hasattr(message, "convert_to_task"):
            task = message.convert_to_task(
                title=title,
                assigned_to=assigned_to,
                due_date=due_date,
                priority=TaskPriority.NORMAL,
                department=department,
                parent_task=parent_task,
                link_channel=link_channel,
                description=message.content,
            )
        else:
            task = Task.objects.create(
                organization=org,
                title=title,
                description=message.content,
                created_by=request.user,
                assigned_to=assigned_to,
                department=department,
                parent_task=parent_task,
                origin_message=message,
                priority=TaskPriority.NORMAL,
                due_date=due_date,
                related_channel=message.channel if link_channel else None,
                related_dm=message.direct_message,
            )
            # update message for fallback path
            message.content = f"✅ **Task Created**\n**Title:** {title}\n**Priority:** {task.get_priority_display()}"
            if assigned_to:
                message.content += f"\n**Assigned to:** {display_name_for(assigned_to)}"
            if due_date:
                message.content += f"\n**Due:** {due_date.strftime('%b %d, %Y')}"
            message.message_type = 'task_created'
            message.related_task = task
            message.converted_to_task = task
            message.save(update_fields=["content", "message_type", "related_task", "converted_to_task"])
            _broadcast_chat_message(message)
        
        return JsonResponse({
            "success": True,
            "task_id": str(task.id),
            "title": task.title,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
def task_role_board_view(request):
    """
    Manage tasks grouped by role (pastor, admin, HOD, worker, volunteer).
    """
    org = getattr(request.user, "organization", None)
    if not org:
        return HttpResponseForbidden("No organization assigned")

    tasks_qs = Task.objects.filter(organization=org).select_related("assigned_to", "created_by")

    # Respect privacy for non-privileged users
    if not (request.user.is_admin or request.user.is_pastor or request.user.is_owner):
        tasks_qs = tasks_qs.filter(
            Q(is_private=False) |
            Q(created_by=request.user) |
            Q(assigned_to=request.user)
        )

    role_filters = [
        ("Head of Units / HOD", Q(assigned_to__is_hod=True)),
        ("Pastors", Q(assigned_to__is_pastor=True)),
        ("Admins", Q(assigned_to__is_admin=True)),
        ("Workers", Q(assigned_to__is_worker=True)),
        ("Volunteers", Q(assigned_to__is_volunteer=True)),
    ]

    role_blocks = []
    for title, role_q in role_filters:
        role_tasks = tasks_qs.filter(role_q).order_by("-priority", "due_date")[:12]
        role_blocks.append({
            "title": title,
            "count": role_tasks.count(),
            "tasks": role_tasks,
        })

    unassigned = tasks_qs.filter(assigned_to__isnull=True).order_by("-priority", "due_date")[:12]

    return render(request, "task/role_board.html", {
        "role_blocks": role_blocks,
        "unassigned": unassigned,
    })
