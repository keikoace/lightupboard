from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    # Invoices
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/generate/', views.invoice_generate, name='invoice_generate'),
    path('invoices/add/', views.invoice_add, name='invoice_add'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/print/', views.invoice_print, name='invoice_print'),
    path('invoices/<int:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('invoices/<int:pk>/delete/', views.invoice_delete, name='invoice_delete'),
    path('invoices/<int:pk>/send/', views.invoice_send, name='invoice_send'),
    path('invoicing/', views.invoicing, name='invoicing'),
    # Payments
    path('payments/', views.payments, name='payments'),
    path('payments/add/', views.payment_add, name='payment_add'),
    path('payments/<int:pk>/edit/', views.payment_edit, name='payment_edit'),
    path('payments/<int:pk>/delete/', views.payment_delete, name='payment_delete'),
    # Term Deals
    path('term-deals/', views.term_deals, name='term_deals'),
    path('term-deals/add/', views.term_deal_add, name='term_deal_add'),
    path('term-deals/<int:pk>/edit/', views.term_deal_edit, name='term_deal_edit'),
    path('term-deals/<int:pk>/delete/', views.term_deal_delete, name='term_deal_delete'),
    # Bill Verification
    path('bill-verification/', views.bill_verification, name='bill_verification'),
    path('bill-verification/add/', views.bill_verification_add, name='bill_verification_add'),
    path('bill-verification/<int:pk>/edit/', views.bill_verification_edit, name='bill_verification_edit'),
    path('bill-verification/<int:pk>/delete/', views.bill_verification_delete, name='bill_verification_delete'),
    path('bill-verification/<int:pk>/recalculate/', views.bill_verification_recalculate, name='bill_verification_recalculate'),
    # Revenue Share
    path('revenue-share/', views.revenue_share_list, name='revenue_share_list'),
    path('revenue-share/my/', views.my_revenue_share, name='my_revenue_share'),
    path('revenue-share/all/', views.all_revenue_share, name='all_revenue_share'),
    # Currency
    path('currency/', views.currency_rates, name='currency_rates'),
    # Other
    path('gross-profit/', views.gross_profit, name='gross_profit'),
    path('multi-invoice-email/', views.multi_invoice_email, name='multi_invoice_email'),
    path('reciprocals/', views.reciprocals, name='reciprocals'),
    path('maintenance/', views.maintenance, name='maintenance'),
    path('credit/', views.credit_list, name='credit_list'),
    # Customer Cart (Billable Items)
    path('cart/<int:company_pk>/', views.customer_cart, name='customer_cart'),
    path('cart/<int:company_pk>/add/', views.cart_item_add, name='cart_item_add'),
    path('cart/item/<int:pk>/edit/', views.cart_item_edit, name='cart_item_edit'),
    path('cart/item/<int:pk>/delete/', views.cart_item_delete, name='cart_item_delete'),
]
