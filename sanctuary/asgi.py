"""
ASGI config for sanctuary project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os
import django

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from chat.routing import websocket_urlpatterns
from channels.security.websocket import AllowedHostsOriginValidator
from sanctuary.middleware import JWTAuthMiddleware


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sanctuary.settings")

django_asgi_app = get_asgi_application()


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddleware(  # Use your JWT middleware
            AuthMiddlewareStack(  # Keep Django auth middleware for session auth
                URLRouter(
                    websocket_urlpatterns
                )
            )
        )
    ),
})