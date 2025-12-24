from django.urls import path
from . import views

urlpatterns = [
    # Dashboard and lists
    path('api/task/dashboard/', views.task_dashboard_api_view, name='task_dashboard'),
    path('api/task/list/', views.task_list_api_view, name='task_list'),
    
    # Task CRUD
    path('api/task/create/', views.task_create_api_view, name='task_create'),
    path('api/task/<uuid:task_id>/', views.task_detail_api_view, name='task_detail'),
    path('api/task/<uuid:task_id>/update/', views.task_update_api_view, name='task_update'),
    path('api/task/<uuid:task_id>/delete/', views.task_delete_api_view, name='task_delete'),
    
    # Task actions
    path('api/task/<uuid:task_id>/comment/', views.task_add_comment_api_view, name='task_add_comment'),
    path('api/task/<uuid:task_id>/checklist/', views.task_add_checklist_api_view, name='task_add_checklist'),
    path('api/task/<uuid:task_id>/checklist/<uuid:checklist_id>/toggle/', views.task_toggle_checklist_api_view, name='task_toggle_checklist'),
    path('api/task/<uuid:task_id>/timer/start/', views.task_start_timer_api_view, name='task_start_timer'),
    path('api/task/<uuid:task_id>/timer/stop/', views.task_stop_timer_api_view, name='task_stop_timer'),
    
    # Message to task conversion
    path('api/task/convert/message/', views.convert_message_to_task_api_view, name='convert_message_to_task'),
    path('api/task/message/<uuid:message_id>/suggestions/', views.get_message_task_suggestions_api_view, name='get_message_suggestions'),

    # Labels
    path('api/task/labels/', views.task_labels_api_view, name='task_labels'),
    path('api/task/labels/create/', views.create_task_label_api_view, name='create_task_label'),

    # Notifications
    path('api/task/notifications/', views.task_notifications_api_view, name='task_notifications'),
    path('api/task/notifications/<uuid:notification_id>/read/', views.mark_notification_read_api_view, name='mark_notification_read'),
    path('api/task/notifications/mark-all-read/', views.mark_all_notifications_read_api_view, name='mark_all_notifications_read'),

    # Widget views (session auth)
    path('api/task/widget/summary/', views.task_widget_summary_view, name='task_widget_summary'),
    path('api/task/widget/list/', views.task_widget_list_view, name='task_widget_list'),
    path('api/task/widget/create/', views.task_widget_create_view, name='task_widget_create'),
]