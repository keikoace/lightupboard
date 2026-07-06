from django.urls import path
from . import views

app_name = 'email_import'

urlpatterns = [
    path('',                     views.rule_list,   name='rule_list'),
    path('add/',                 views.rule_add,    name='rule_add'),
    path('<int:pk>/edit/',       views.rule_edit,   name='rule_edit'),
    path('<int:pk>/delete/',     views.rule_delete, name='rule_delete'),
    path('logs/<int:pk>/',       views.log_detail,  name='log_detail'),
    path('run/',                 views.run_now,     name='run_now'),
]
