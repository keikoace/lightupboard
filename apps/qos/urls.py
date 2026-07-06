from django.urls import path
from . import views

app_name = 'qos'

urlpatterns = [
    path('minutes/', views.minutes_analysis, name='minutes_analysis'),
    path('minutes/customer/', views.customer_minutes, name='customer_minutes'),
    path('minutes/supplier/', views.supplier_minutes, name='supplier_minutes'),
    path('minutes/ddi/', views.ddi_minutes, name='ddi_minutes'),
    path('cdr/', views.cdr_extract, name='cdr_extract'),
    path('cdr/ddi/', views.ddi_cdr_extract, name='ddi_cdr_extract'),
]
