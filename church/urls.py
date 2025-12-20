# church/urls.py - CORRECTED VERSION
from django.urls import path
from . import views 
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [

      # Members API
    path("api/members/", views.member_list_api_view, name='api_member_list'),
    path("api/members/<uuid:member_id>/", views.member_detail_api_view, name='api_member_detail'),
    path("api/members/create/", views.member_create_api_view, name='api_member_create'),
    path("api/members/<uuid:member_id>/update/", views.member_update_api_view, name='api_member_update'),
    path("api/members/<uuid:member_id>/delete/", views.member_delete_api_view, name='api_member_delete'),
    path("api/members/statistics/", views.member_statistics_api_view, name='api_member_statistics'),
    
    # ========== API ENDPOINTS (MUST COME FIRST) ==========
    path("api/departments/", views.department_list_api_view, name='api_department_list'),
    path("api/departments/create/", views.department_create_api_view, name='api_department_create'),
    path("api/departments/<uuid:department_id>/update/", views.department_update_api_view, name='api_department_update'),
    path("api/departments/<uuid:department_id>/delete/", views.department_delete_api_view, name='api_department_delete'),
    path('api/departments/<uuid:department_id>/', views.department_detail_api_view, name='api_department_detail'),

    path('api/departments/<uuid:department_id>/members/', views.department_members_api_view, name='api_department_members'),
    path('api/departments/<uuid:department_id>/members/add/', views.department_add_members_api_view, name='api_department_add_members'),
    path('api/departments/<uuid:department_id>/members/remove/', views.department_remove_members_api_view, name='api_department_remove_members'),


    # JWT Token endpoints
    path("api/token/", TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path("api/token/refresh/", TokenRefreshView.as_view(), name='token_refresh'),

    # Campus URLs
    path('api/campuses/', views.campus_list_api_view, name='api_campus_list'),
    path('api/campuses/<uuid:campus_id>/', views.campus_detail_api_view, name='api_campus_detail'),
    path('api/campuses/create/', views.campus_create_api_view, name='api_campus_create'),
    path('api/campuses/<uuid:campus_id>/update/', views.campus_update_api_view, name='api_campus_update'),
    path('api/campuses/<uuid:campus_id>/delete/', views.campus_delete_api_view, name='api_campus_delete'),
    path('api/campuses/<uuid:campus_id>/members/', views.campus_members_api_view, name='api_campus_members'),
    path('api/campuses/<uuid:campus_id>/members/add/', views.campus_add_members_api_view, name='api_campus_add_members'),
    path('api/campuses/<uuid:campus_id>/members/remove/', views.campus_remove_members_api_view, name='api_campus_remove_members'),

    # Family URLs
    path('api/families/', views.family_list_api_view, name='api_family_list'),
    path('api/families/<uuid:family_id>/', views.family_detail_api_view, name='api_family_detail'),
    path('api/families/create/', views.family_create_api_view, name='api_family_create'),
    path('api/families/<uuid:family_id>/update/', views.family_update_api_view, name='api_family_update'),
    path('api/families/<uuid:family_id>/delete/', views.family_delete_api_view, name='api_family_delete'),
    path('api/families/<uuid:family_id>/members/', views.family_members_api_view, name='api_family_members'),
    path('api/families/<uuid:family_id>/members/add/', views.family_add_members_api_view, name='api_family_add_members'),
    path('api/families/<uuid:family_id>/members/remove/', views.family_remove_members_api_view, name='api_family_remove_members'),

    # Add to your church/urls.py

    # Mobile Voucher API endpoints
    path('api/vouchers/', views.voucher_list_api_view, name='voucher-list'),  # List endpoint
    path('api/vouchers/create/', views.voucher_create_api_view, name='voucher-create'),  # POST only
    path('api/vouchers/dashboard/', views.voucher_dashboard_api_view, name='voucher-dashboard'),
    path('api/vouchers/templates/', views.voucher_template_list_api_view, name='voucher-templates'),

    # API endpoints - generic paths last
    path('api/vouchers/<uuid:voucher_id>/', views.voucher_detail_api_view, name='voucher-detail'),
    path('api/vouchers/<uuid:voucher_id>/update/', views.voucher_update_api_view, name='voucher-update'),
    path('api/vouchers/<uuid:voucher_id>/delete/', views.voucher_delete_api_view, name='voucher-delete'),
    path('api/vouchers/<uuid:voucher_id>/submit/', views.voucher_submit_api_view, name='voucher-submit'),
    path('api/vouchers/<uuid:voucher_id>/approve/', views.voucher_approve_api_view, name='voucher-approve'),
    path('api/vouchers/<uuid:voucher_id>/reject/', views.voucher_reject_api_view, name='voucher-reject'),
    path('api/vouchers/<uuid:voucher_id>/pay/', views.voucher_pay_api_view, name='voucher-pay'),
    path('api/vouchers/<uuid:voucher_id>/comment/', views.voucher_add_comment_api_view, name='voucher-comment'),
    path('api/vouchers/reports/', views.voucher_reports_api_view, name='api_voucher_reports'),
    path('api/vouchers/notifications/', views.voucher_notifications_api_view, name='api_vouchers_notifications'),
    path('api/vouchers/notifications/<str:notification_id>/read/', views.mark_notification_read_api_view, name='api_mark_notification_read'),
    path('api/vouchers/notifications/read-all/', views.mark_all_notifications_read_api_view, name='api_mark_all_notifications_read'),


    
    path('api/chat/home/', views.chat_home_api_view, name='chat_home_api'),
    path('api/chat/channels/create/', views.channel_create_api_view, name='channel_create_api'),
    path('api/chat/channels/<uuid:channel_id>/', views.channel_detail_api_view, name='channel_detail_api'),
    path('api/chat/channels/<uuid:channel_id>/send/', views.send_channel_message_api_view, name='send_channel_message_api'),
    path('api/chat/dms/start/', views.start_dm_api_view, name='start_dm_api'),
    path('api/chat/dms/<uuid:dm_id>/', views.dm_detail_api_view, name='dm_detail_api'),
    path('api/chat/dms/<uuid:dm_id>/send/', views.send_dm_message_api_view, name='send_dm_message_api'),
    path('api/chat/mark-read/', views.mark_messages_read_api_view, name='mark_messages_read_api'),
    path('api/chat/messages/<uuid:message_id>/delete/', views.delete_message_api_view, name='delete_message_api'),

                    
        
    
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

    path('api/vouchers/reports/pending-approvals/', views.pending_approvals_report_view, name='api_vouchers_pending_approvals_report'),
    path('api/vouchers/reports/payment-status/', views.payment_status_report_view, name='api_vouchers_payment_status_report'),
    path('api/vouchers/reports/expense-trend/', views.expense_trend_analysis_view, name='api_vouchers_expense_trend_report'),
    path('api/vouchers/reports/overdue/', views.overdue_vouchers_report_view, name='api_vouchers_overdue_report'),




    # ========== WEB VIEWS ==========
    # Member routes
    path("members/", views.member_list_view, name='member_list'),
    path("members/create/", views.member_create_view, name='member_create'),
    path("members/<uuid:member_id>/", views.member_detail_view, name='member_detail'),
    path("members/<uuid:member_id>/edit/", views.member_edit_view, name='member_edit'),
    path('members/<uuid:member_id>/delete/', views.member_delete_view, name='member_delete'),
    path('members/statistics/', views.member_statistics_view, name='member_statistics'),



    path('api/inventory/', views.inventory_dashboard_api_view, name='inventory_api_dashboard'),
    path('api/inventory/items/', views.inventory_item_list_api_view, name='inventory_api_item_list'),
    path('api/inventory/items/create/', views.inventory_item_create_api_view, name='inventory_api_item_create'),
    path('api/inventory/items/<uuid:item_id>/', views.inventory_item_detail_api_view, name='inventory_api_item_detail'),
    path('api/inventory/items/<uuid:item_id>/update/',views.inventory_item_update_api_view, name='inventory_api_item_update'),
    path('api/inventory/items/<uuid:item_id>/delete/',views.inventory_item_delete_api_view, name='inventory_api_item_delete'),

    path('api/inventory/checkouts/', views.inventory_checkout_list_api_view, name='inventory_api_checkout_list'),
    path('api/inventory/checkouts/create/', views.inventory_checkout_create_api_view, name='inventory_api_checkout_create'),
    path('api/inventory/alerts/lowstock/', views.inventory_low_stock_alerts_api_view, name='inventory_api_low_stock'),
    path('api/inventory/categories/', views.inventory_category_list_api_view, name='inventory_api_category_list'),
    path('api/inventory/vendors/',views.inventory_vendor_list_api_view, name='inventory_api_vendor_list'),
    path('api/inventory/transactions/',views.inventory_transaction_list_api_view, name='inventory_api_transaction_list'),
    path('api/inventory/stock/adjust/', views.stock_adjustment_api_view, name='inventory_api_stock_adjust'),




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
    
 # ========== ORGANIZATION-SPECIFIC ROUTES ==========
    path("<uuid:organization_id>/invite/", views.send_invite_view, name="send_invite"),
    path("<uuid:organization_id>/", views.organization_dashboard_view, name="organization_dashboard"),
    
    # ========== GENERAL ROUTES ==========
    path("", views.organization_list_view, name="organizations_list"),
    path("apply/", views.organization_apply_view, name="organization_apply"),
    path("invites/accept/", views.accept_invite_view, name="accept_invite"),
    path("admin/create/", views.create_org_owner_view, name="create_org_owner"),
    path("plans/", views.subscription_plan_list_view, name="subscription_plan_list"),
    path("plans/create/", views.subscription_plan_create_view, name="subscription_plan_create"),
    path("plans/<uuid:plan_id>/edit/", views.subscription_plan_update_view, name="subscription_plan_edit"),
    path("plans/<uuid:plan_id>/delete/", views.subscription_plan_delete_view, name="subscription_plan_delete"),
    
    # ========== ORGANIZATION DETAIL BY SLUG (MUST BE LAST) ==========
    path("<slug:slug>/", views.organization_detail_view, name="organization_detail"),

    
]