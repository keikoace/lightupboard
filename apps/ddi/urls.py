from django.urls import path
from . import views

app_name = 'ddi'

urlpatterns = [
    # DDI Numbers
    path('numbers/', views.number_list, name='number_list'),
    path('numbers/add/', views.number_add, name='number_add'),
    path('numbers/<int:pk>/edit/', views.number_edit, name='number_edit'),
    path('numbers/<int:pk>/delete/', views.number_delete, name='number_delete'),
    # DDI Profiles
    path('profiles/', views.profile_list, name='profile_list'),
    path('profiles/add/', views.profile_add, name='profile_add'),
    path('profiles/<int:pk>/edit/', views.profile_edit, name='profile_edit'),
    path('profiles/<int:pk>/delete/', views.profile_delete, name='profile_delete'),
    # DDI Routes
    path('routes/', views.route_list, name='route_list'),
    path('routes/add/', views.route_add, name='route_add'),
    path('routes/<int:pk>/edit/', views.route_edit, name='route_edit'),
    path('routes/<int:pk>/delete/', views.route_delete, name='route_delete'),
    # Other
    path('cost-base/', views.cost_base, name='cost_base'),
    path('loss-analysis/', views.loss_analysis, name='loss_analysis'),
]
