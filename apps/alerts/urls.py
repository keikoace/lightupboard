from django.urls import path
from . import views

app_name = 'alerts'

urlpatterns = [
    path('unprocessed/', views.unprocessed, name='unprocessed'),
    path('ddi-unprocessed/', views.ddi_unprocessed, name='ddi_unprocessed'),
    path('rules/', views.rule_list, name='rule_list'),
    path('rules/add/', views.rule_add, name='rule_add'),
    path('rules/<int:pk>/edit/', views.rule_edit, name='rule_edit'),
    path('rules/<int:pk>/delete/', views.rule_delete, name='rule_delete'),
    path('traffic/', views.traffic_alerts, name='traffic_alerts'),
    path('events/<int:pk>/action/', views.event_action, name='event_action'),
]
