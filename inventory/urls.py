# church/urls.py - CORRECTED VERSION
from django.urls import path
from . import views, api_views as as_views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('api/inventory/', as_views.inventory_dashboard_api_view, name='inventory_api_dashboard'),
    path('api/inventory/items/', as_views.inventory_item_list_api_view, name='inventory_api_item_list'),
    path('api/inventory/items/create/', as_views.inventory_item_create_api_view, name='inventory_api_item_create'),
    path('api/inventory/items/<uuid:item_id>/', as_views.inventory_item_detail_api_view, name='inventory_api_item_detail'),
    path('api/inventory/items/<uuid:item_id>/update/',as_views.inventory_item_update_api_view, name='inventory_api_item_update'),
    path('api/inventory/items/<uuid:item_id>/delete/',as_views.inventory_item_delete_api_view, name='inventory_api_item_delete'),

    path('api/inventory/checkouts/', as_views.inventory_checkout_list_api_view, name='inventory_api_checkout_list'),
    path('api/inventory/checkouts/create/', as_views.inventory_checkout_create_api_view, name='inventory_api_checkout_create'),
    path('api/inventory/alerts/lowstock/', as_views.inventory_low_stock_alerts_api_view, name='inventory_api_low_stock'),
    path('api/inventory/categories/', as_views.inventory_category_list_api_view, name='inventory_api_category_list'),
    path('api/inventory/vendors/',as_views.inventory_vendor_list_api_view, name='inventory_api_vendor_list'),
    path('api/inventory/transactions/',as_views.inventory_transaction_list_api_view, name='inventory_api_transaction_list'),
    path('api/inventory/stock/adjust/', as_views.stock_adjustment_api_view, name='inventory_api_stock_adjust'),
    
    
    # inventory
    path('', views.inventory_dashboard_view, name='inventory_dashboard'),
    path('items/', views.inventory_item_list_view, name='inventory_item_list'),
    path('items/create/', views.inventory_item_create_view, name='inventory_item_create'),
    path('items/<uuid:item_id>/', views.inventory_item_detail_view, name='inventory_item_detail'),
    path('items/<uuid:item_id>/edit/', views.inventory_item_update_view, name='inventory_item_update'),
    path('items/<uuid:item_id>/delete/', views.inventory_item_delete_view, name='inventory_item_delete'),
    
    path('checkouts/', views.inventory_checkout_list_view, name='inventory_checkout_list'),
    path('checkouts/create/', views.inventory_checkout_create_view, name='inventory_checkout_create'),
    path('checkouts/<uuid:checkout_id>/return/', views.inventory_checkout_return_view, name='inventory_checkout_return'),
    path('checkouts/<uuid:checkout_id>/extend/', views.inventory_checkout_extend_view, name='inventory_checkout_extend'),
    
]