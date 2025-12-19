# church/api_urls.py - CORRECTED VERSION
from django.urls import path
from . import api_views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    # Members API
    path("members/", api_views.member_list_api_view, name='api_member_list'),
    path("members/<uuid:member_id>/", api_views.member_detail_api_view, name='api_member_detail'),
    path("members/create/", api_views.member_create_api_view, name='api_member_create'),
    path("members/<uuid:member_id>/update/", api_views.member_update_api_view, name='api_member_update'),
    path("members/<uuid:member_id>/delete/", api_views.member_delete_api_view, name='api_member_delete'),
    path("members/statistics/", api_views.member_statistics_api_view, name='api_member_statistics'),
    
    # Departments API
    path("departments/", api_views.department_list_api_view, name='api_department_list'),
    path("departments/create/", api_views.department_create_api_view, name='api_department_create'),
    path("departments/<uuid:department_id>/update/", api_views.department_update_api_view, name='api_department_update'),
    path("departments/<uuid:department_id>/delete/", api_views.department_delete_api_view, name='api_department_delete'),
    path('departments/<uuid:department_id>/', api_views.department_detail_api_view, name='api_department_detail'),

    path('departments/<uuid:department_id>/members/', api_views.department_members_api_view, name='api_department_members'),
    path('departments/<uuid:department_id>/members/add/', api_views.department_add_members_api_view, name='api_department_add_members'),
    path('departments/<uuid:department_id>/members/remove/', api_views.department_remove_members_api_view, name='api_department_remove_members'),

    # JWT Token endpoints
    path("token/", TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path("token/refresh/", TokenRefreshView.as_view(), name='token_refresh'),

    # Campus URLs
    path('campuses/', api_views.campus_list_api_view, name='api_campus_list'),
    path('campuses/<uuid:campus_id>/', api_views.campus_detail_api_view, name='api_campus_detail'),
    path('campuses/create/', api_views.campus_create_api_view, name='api_campus_create'),
    path('campuses/<uuid:campus_id>/update/', api_views.campus_update_api_view, name='api_campus_update'),
    path('campuses/<uuid:campus_id>/delete/', api_views.campus_delete_api_view, name='api_campus_delete'),
    path('campuses/<uuid:campus_id>/members/', api_views.campus_members_api_view, name='api_campus_members'),
    path('campuses/<uuid:campus_id>/members/add/', api_views.campus_add_members_api_view, name='api_campus_add_members'),
    path('campuses/<uuid:campus_id>/members/remove/', api_views.campus_remove_members_api_view, name='api_campus_remove_members'),

    # Family URLs
    path('families/', api_views.family_list_api_view, name='api_family_list'),
    path('families/<uuid:family_id>/', api_views.family_detail_api_view, name='api_family_detail'),
    path('families/create/', api_views.family_create_api_view, name='api_family_create'),
    path('families/<uuid:family_id>/update/', api_views.family_update_api_view, name='api_family_update'),
    path('families/<uuid:family_id>/delete/', api_views.family_delete_api_view, name='api_family_delete'),
    path('families/<uuid:family_id>/members/', api_views.family_members_api_view, name='api_family_members'),
    path('families/<uuid:family_id>/members/add/', api_views.family_add_members_api_view, name='api_family_add_members'),
    path('families/<uuid:family_id>/members/remove/', api_views.family_remove_members_api_view, name='api_family_remove_members'),

    # Mobile Voucher API endpoints
    path('vouchers/', api_views.voucher_list_api_view, name='voucher-list'),
    path('vouchers/create/', api_views.voucher_create_api_view, name='voucher-create'),
    path('vouchers/dashboard/', api_views.voucher_dashboard_api_view, name='voucher-dashboard'),
    path('vouchers/templates/', api_views.voucher_template_list_api_view, name='voucher-templates'),

    # Generic voucher paths
    path('vouchers/<uuid:voucher_id>/', api_views.voucher_detail_api_view, name='voucher-detail'),
    path('vouchers/<uuid:voucher_id>/update/', api_views.voucher_update_api_view, name='voucher-update'),
    path('vouchers/<uuid:voucher_id>/delete/', api_views.voucher_delete_api_view, name='voucher-delete'),
    path('vouchers/<uuid:voucher_id>/submit/', api_views.voucher_submit_api_view, name='voucher-submit'),
    path('vouchers/<uuid:voucher_id>/approve/', api_views.voucher_approve_api_view, name='voucher-approve'),
    path('vouchers/<uuid:voucher_id>/reject/', api_views.voucher_reject_api_view, name='voucher-reject'),
    path('vouchers/<uuid:voucher_id>/pay/', api_views.voucher_pay_api_view, name='voucher-pay'),
    path('vouchers/<uuid:voucher_id>/comment/', api_views.voucher_add_comment_api_view, name='voucher-comment'),
    
    # Voucher Reports & Notifications
    path('vouchers/reports/', api_views.voucher_reports_api_view, name='api_voucher_reports'),
    path('vouchers/notifications/', api_views.voucher_notifications_api_view, name='api_vouchers_notifications'),
    path('vouchers/notifications/<str:notification_id>/read/', api_views.mark_notification_read_api_view, name='api_mark_notification_read'),
    path('vouchers/notifications/read-all/', api_views.mark_all_notifications_read_api_view, name='api_mark_all_notifications_read'),
    path('vouchers/reports/pending-approvals/', api_views.pending_approvals_report_view, name='api_vouchers_pending_approvals_report'),
    path('vouchers/reports/payment-status/', api_views.payment_status_report_view, name='api_vouchers_payment_status_report'),
    path('vouchers/reports/expense-trend/', api_views.expense_trend_analysis_view, name='api_vouchers_expense_trend_report'),
    path('vouchers/reports/overdue/', api_views.overdue_vouchers_report_view, name='api_vouchers_overdue_report'),

    # Inventory API endpoints
    path('inventory/', api_views.inventory_dashboard_api_view, name='inventory_api_dashboard'),
    path('inventory/items/', api_views.inventory_item_list_api_view, name='inventory_api_item_list'),
    path('inventory/items/create/', api_views.inventory_item_create_api_view, name='inventory_api_item_create'),
    path('inventory/items/<uuid:item_id>/', api_views.inventory_item_detail_api_view, name='inventory_api_item_detail'),
    path('inventory/items/<uuid:item_id>/update/', api_views.inventory_item_update_api_view, name='inventory_api_item_update'),
    path('inventory/items/<uuid:item_id>/delete/', api_views.inventory_item_delete_api_view, name='inventory_api_item_delete'),
    path('inventory/checkouts/', api_views.inventory_checkout_list_api_view, name='inventory_api_checkout_list'),
    path('inventory/checkouts/create/', api_views.inventory_checkout_create_api_view, name='inventory_api_checkout_create'),
    path('inventory/alerts/lowstock/', api_views.inventory_low_stock_alerts_api_view, name='inventory_api_low_stock'),
    path('inventory/categories/', api_views.inventory_category_list_api_view, name='inventory_api_category_list'),
    path('inventory/vendors/', api_views.inventory_vendor_list_api_view, name='inventory_api_vendor_list'),
    path('inventory/transactions/', api_views.inventory_transaction_list_api_view, name='inventory_api_transaction_list'),
    path('inventory/stock/adjust/', api_views.stock_adjustment_api_view, name='inventory_api_stock_adjust'),
]