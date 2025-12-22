# church/urls.py - CORRECTED VERSION
from django.urls import path
from . import views, api_views as as_views

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [


    # Mobile Voucher API endpoints
    path('api/vouchers/', as_views.voucher_list_api_view, name='voucher-list'),  # List endpoint
    path('api/vouchers/create/', as_views.voucher_create_api_view, name='voucher-create'),  # POST only
    path('api/vouchers/dashboard/', as_views.voucher_dashboard_api_view, name='voucher-dashboard'),
    path('api/vouchers/templates/', as_views.voucher_template_list_api_view, name='voucher-templates'),

    # API endpoints - generic paths last
    path('api/vouchers/<uuid:voucher_id>/', as_views.voucher_detail_api_view, name='voucher-detail'),
    path('api/vouchers/<uuid:voucher_id>/update/', as_views.voucher_update_api_view, name='voucher-update'),
    path('api/vouchers/<uuid:voucher_id>/delete/', as_views.voucher_delete_api_view, name='voucher-delete'),
    path('api/vouchers/<uuid:voucher_id>/submit/', as_views.voucher_submit_api_view, name='voucher-submit'),
    path('api/vouchers/<uuid:voucher_id>/approve/', as_views.voucher_approve_api_view, name='voucher-approve'),
    path('api/vouchers/<uuid:voucher_id>/reject/', as_views.voucher_reject_api_view, name='voucher-reject'),
    path('api/vouchers/<uuid:voucher_id>/pay/', as_views.voucher_pay_api_view, name='voucher-pay'),
    path('api/vouchers/<uuid:voucher_id>/comment/', as_views.voucher_add_comment_api_view, name='voucher-comment'),
    path('api/vouchers/reports/', as_views.voucher_reports_api_view, name='api_voucher_reports'),
    path('api/vouchers/notifications/', as_views.voucher_notifications_api_view, name='api_vouchers_notifications'),
    path('api/vouchers/notifications/<str:notification_id>/read/', as_views.mark_notification_read_api_view, name='api_mark_notification_read'),
    path('api/vouchers/notifications/read-all/', as_views.mark_all_notifications_read_api_view, name='api_mark_all_notifications_read'),
    
    path('vouchers/', views.voucher_list_view, name='voucher_list'),
    path('vouchers/dashboard/', views.voucher_dashboard_view, name='voucher_dashboard'),
    path('vouchers/create/', views.voucher_create_view, name='voucher_create'),
    path('vouchers/<uuid:voucher_id>/', views.voucher_detail_view, name='voucher_detail'),
    path('vouchers/<uuid:voucher_id>/edit/', views.voucher_update_view, name='voucher_edit'),
    path('vouchers/<uuid:voucher_id>/submit/', views.voucher_submit_view, name='voucher_submit'),
    path('vouchers/<uuid:voucher_id>/approve/', views.voucher_approve_view, name='voucher_approve'),
    path('vouchers/<uuid:voucher_id>/pdf/', views.voucher_pdf_view, name='voucher_pdf'),
    path('vouchers/<uuid:voucher_id>/download/', views.voucher_download_view, name='voucher_download'),


    path('voucher-templates/', views.voucher_template_list_view, name='voucher_template_list'),
    path('voucher-templates/create/', views.voucher_template_create_view, name='voucher_template_create'),
    path('voucher-templates/<uuid:template_id>/edit/', views.voucher_template_edit_view, name='voucher_template_edit'),
    path('voucher-templates/<uuid:template_id>/delete/', views.voucher_template_delete_view, name='voucher_template_delete'),
    path('voucher-templates/<uuid:template_id>/duplicate/', views.voucher_template_duplicate_view, name='voucher_template_duplicate'),
    path('vouchers/create/blank/', views.voucher_create_blank_view, name='voucher_create_blank'),
    path('vouchers/create/blank/template/<uuid:template_id>/', views.voucher_create_blank_view, name='voucher_create_blank_with_template'),
    # In your urls.py

    path('api/vouchers/reports/pending-approvals/', as_views.pending_approvals_report_view, name='api_vouchers_pending_approvals_report'),
    path('api/vouchers/reports/payment-status/', as_views.payment_status_report_view, name='api_vouchers_payment_status_report'),
    path('api/vouchers/reports/expense-trend/', as_views.expense_trend_analysis_view, name='api_vouchers_expense_trend_report'),
    path('api/vouchers/reports/overdue/', as_views.overdue_vouchers_report_view, name='api_vouchers_overdue_report'),
]