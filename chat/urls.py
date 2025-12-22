# Chat URLs (JWT APIs + web widget)
from django.urls import path
from . import views 
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("", views.chat_page, name="chat_page"),
    path('api/chat/home/', views.chat_home_api_view, name='chat_home_api'),
    path('api/chat/channels/create/', views.channel_create_api_view, name='channel_create_api'),
    path('api/chat/channels/<uuid:channel_id>/', views.channel_detail_api_view, name='channel_detail_api'),
    path('api/chat/channels/<uuid:channel_id>/join/', views.channel_join_api_view, name='channel_join_api'),
    path('api/chat/channels/<uuid:channel_id>/leave/', views.channel_leave_api_view, name='channel_leave_api'),
    path('api/chat/channels/<uuid:channel_id>/send/', views.send_channel_message_api_view, name='send_channel_message_api'),
    path('api/chat/dms/start/', views.start_dm_api_view, name='start_dm_api'),
    path('api/chat/dms/<uuid:dm_id>/', views.dm_detail_api_view, name='dm_detail_api'),
    path('api/chat/dms/<uuid:dm_id>/send/', views.send_dm_message_api_view, name='send_dm_message_api'),
    path('api/chat/mark-read/', views.mark_messages_read_api_view, name='mark_messages_read_api'),
    path('api/chat/messages/<uuid:message_id>/delete/', views.delete_message_api_view, name='delete_message_api'),
    path('api/chat/join-requests/<uuid:request_id>/approve/', views.channel_join_approve_api_view, name='channel_join_approve_api'),

    # Web widget (session auth)
    path('widget/summary/', views.chat_widget_summary_view, name='chat_widget_summary'),
    path('widget/<str:thread_type>/<uuid:thread_id>/messages/', views.chat_widget_messages_view, name='chat_widget_messages'),
    path('widget/send/', views.chat_widget_send_view, name='chat_widget_send'),
    path('widget/dm/start/', views.chat_widget_start_dm_view, name='chat_widget_start_dm'),
    path('widget/channel/create/', views.chat_widget_create_channel_view, name='chat_widget_create_channel'),
    path('widget/channel/join/', views.chat_widget_join_channel_view, name='chat_widget_join_channel'),
]
