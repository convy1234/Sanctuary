# chat/routing.py

from django.urls import path, re_path
from . import consumers

# Support both the base endpoint (/ws/chat/) and the legacy
# path style used by the frontend (/ws/chat/<thread_type>/<uuid>/)
websocket_urlpatterns = [
    path('ws/chat/', consumers.ChatConsumer.as_asgi()),
    re_path(r'^ws/chat/(?P<thread_type>channel|dm)/(?P<thread_id>[0-9a-f-]+)/$', consumers.ChatConsumer.as_asgi()),
]
