from django.urls import path
from . import views

app_name = 'portal'

urlpatterns = [
    path('',              views.portal_root,      name='root'),
    path('login/',        views.portal_login,     name='login'),
    path('logout/',       views.portal_logout,    name='logout'),
    path('dashboard/',    views.dashboard,        name='dashboard'),
    path('invoices/',     views.invoices,         name='invoices'),
    path('invoices/<int:pk>/',       views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/print/', views.invoice_print,  name='invoice_print'),
    path('traffic/',      views.traffic,          name='traffic'),
    path('dids/',         views.dids,             name='dids'),
    path('rates/',        views.rates,            name='rates'),
    path('cdrs/export/',  views.cdr_export,       name='cdr_export'),
    path('account/',      views.account,          name='account'),
]
