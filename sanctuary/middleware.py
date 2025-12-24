# sanctuary/middleware.py - UPDATED
import jwt
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
import urllib.parse

User = get_user_model()

class JWTAuthMiddleware:
    """JWT Authentication middleware for Django Channels"""
    
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        print(f"🔗 WebSocket connection attempt")
        
        # Get token from query string
        query_string = scope.get('query_string', b'').decode('utf-8')
        token = None
        
        if query_string:
            try:
                parsed = urllib.parse.parse_qs(query_string)
                token_list = parsed.get('token', [])
                if token_list:
                    token = token_list[0]
                    print(f"   Token found: {token[:20]}...")
            except Exception as e:
                print(f"   ❌ Error parsing query string: {e}")
        
        # Authenticate with token
        if token:
            try:
                print(f"   🔐 Attempting JWT decode...")
                
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=["HS256"]
                )
                
                print(f"   ✅ JWT decoded successfully")
                
                user_id = payload.get('user_id')
                print(f"   User ID from JWT: {user_id}")
                
                if user_id:
                    user = await self.get_user(user_id)
                    if user:
                        scope['user'] = user
                        # DON'T print the user object directly - it triggers __str__
                        print(f"   ✅ User authenticated: {user.email}")
                    else:
                        scope['user'] = AnonymousUser()
                        print(f"   ❌ User not found in database")
                else:
                    scope['user'] = AnonymousUser()
                    print("   ❌ No user_id in JWT payload")
                    
            except jwt.ExpiredSignatureError:
                print("   ❌ Token expired")
                scope['user'] = AnonymousUser()
            except jwt.InvalidTokenError as e:
                print(f"   ❌ Invalid token: {e}")
                scope['user'] = AnonymousUser()
            except Exception as e:
                print(f"   ❌ JWT error: {e}")
                scope['user'] = AnonymousUser()
        else:
            print("   ❌ No token provided")
            scope['user'] = AnonymousUser()
        
        # Print safely without triggering __str__
        if isinstance(scope['user'], AnonymousUser):
            print(f"   Final user: AnonymousUser")
        else:
            print(f"   Final user: Authenticated ({scope['user'].email})")
        
        return await self.app(scope, receive, send)

    @database_sync_to_async
    def get_user(self, user_id):
        try:
            print(f"   🔍 Looking up user with ID: {user_id}")
            
            # Try by uid first
            try:
                user = User.objects.get(uid=user_id)
                print(f"   ✅ Found user by uid: {user.email}")
                return user
            except User.DoesNotExist:
                # Try by id as fallback
                try:
                    user = User.objects.get(id=user_id)
                    print(f"   ✅ Found user by id: {user.email}")
                    return user
                except (User.DoesNotExist, ValueError):
                    return None
        except Exception as e:
            print(f"   ❌ Error looking up user: {e}")
            return None