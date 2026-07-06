from django.urls import path
from . import views

app_name = 'rates'

urlpatterns = [
    path('supplier/', views.supplier_rates, name='supplier_rates'),
    path('supplier/tariffs/', views.supplier_tariffs, name='supplier_tariffs'),
    path('customer/', views.customer_rates, name='customer_rates'),
    path('customer/tariffs/', views.customer_tariffs, name='customer_tariffs'),
    path('customer/export/', views.rate_sheet_export, name='rate_sheet_export'),
    path('cost-base/', views.cost_base, name='cost_base'),
    path('sell-buy/', views.sell_buy_comparison, name='sell_buy_comparison'),
    path('risk-opportunity/', views.risk_opportunity, name='risk_opportunity'),
    # Tariff CRUD
    path('tariffs/add/', views.tariff_add, name='tariff_add'),
    path('tariffs/<int:pk>/edit/', views.tariff_edit, name='tariff_edit'),
    path('tariffs/<int:pk>/delete/', views.tariff_delete, name='tariff_delete'),
    # Rate CRUD
    path('rates/add/', views.rate_add, name='rate_add'),
    path('rates/<int:pk>/edit/', views.rate_edit, name='rate_edit'),
    path('rates/<int:pk>/delete/', views.rate_delete, name='rate_delete'),
    path('rates/import/', views.rate_import, name='rate_import'),
    path('audit/', views.audit_log, name='audit_log'),
    path('origin-groups/', views.origin_group_list, name='origin_group_list'),
]
