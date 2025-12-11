# sanctuary/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

from accounts import views as accounts
from church import views as church

urlpatterns = [
    path('admin/', admin.site.urls),


    # Frontend pages
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
    path('login/', accounts.login_view, name='login'),



    path('register/', accounts.register_view, name='register'),
    path('logout/', accounts.logout_view, name='logout'),
    path('dashboard/', accounts.dashboard_view, name='dashboard'),

    # Admin pages
    path('admin-dashboard/', accounts.admin_dashboard_view, name='admin_dashboard'),
    path('admin/organizations/', accounts.admin_organizations_view, name='admin_organizations'),
    path('admin/billing/', accounts.admin_billing_view, name='admin_billing'),
    path('organization/<uuid:organization_id>/', church.organization_dashboard_view, name='organization_dashboard'),
    
    # Organization management
   
    # Church-related views
    path('organizations/apply/', church.organization_apply_view, name='organization_apply'),
    path('invites/accept/', church.accept_invite_view, name='accept_invite'),
    path('organization/<uuid:organization_id>/invite/', church.send_invite_view, name='send_invite'),
   
    # API URLs
    path('api/', include('church.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)



