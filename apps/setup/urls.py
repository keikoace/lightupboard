from django.urls import path
from . import views

app_name = 'setup'

urlpatterns = [
    path('users/', views.user_list, name='user_list'),
    # Portal users
    path('portal-users/', views.portal_user_list, name='portal_user_list'),
    path('portal-users/add/', views.portal_user_add, name='portal_user_add'),
    path('portal-users/<int:pk>/edit/', views.portal_user_edit, name='portal_user_edit'),
    path('portal-users/<int:pk>/revoke/', views.portal_user_revoke, name='portal_user_revoke'),
    # Companies
    path('companies/', views.company_list, name='company_list'),
    path('companies/add/', views.company_add, name='company_add'),
    path('companies/<int:pk>/', views.company_detail, name='company_detail'),
    path('companies/<int:pk>/edit/', views.company_edit, name='company_edit'),
    path('companies/<int:pk>/delete/', views.company_delete, name='company_delete'),
    path('companies/<int:pk>/profile/', views.company_profile, name='company_profile'),
    # Trunks (nested under company)
    path('companies/<int:company_pk>/trunks/add/', views.trunk_add, name='trunk_add'),
    path('companies/<int:company_pk>/trunks/<int:pk>/edit/', views.trunk_edit, name='trunk_edit'),
    path('companies/<int:company_pk>/trunks/<int:pk>/delete/', views.trunk_delete, name='trunk_delete'),
    # Switches
    path('switches/', views.switch_list, name='switch_list'),
    path('switches/add/', views.switch_add, name='switch_add'),
    path('switches/<int:pk>/edit/', views.switch_edit, name='switch_edit'),
    path('switches/<int:pk>/delete/', views.switch_delete, name='switch_delete'),
    # Destinations
    path('destinations/', views.destination_list, name='destination_list'),
    path('destinations/add/', views.destination_add, name='destination_add'),
    path('destinations/<int:pk>/edit/', views.destination_edit, name='destination_edit'),
    path('destinations/<int:pk>/delete/', views.destination_delete, name='destination_delete'),
    # Disconnect causes
    path('disconnect-causes/', views.disc_cause_list, name='disc_cause_list'),
    path('disconnect-causes/add/', views.disc_cause_add, name='disc_cause_add'),
    path('disconnect-causes/<int:pk>/edit/', views.disc_cause_edit, name='disc_cause_edit'),
    path('disconnect-causes/<int:pk>/delete/', views.disc_cause_delete, name='disc_cause_delete'),
    # Other
    path('tickets/', views.ticket_list, name='ticket_list'),
    path('tickets/create/', views.ticket_create, name='ticket_create'),
    path('tickets/<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('tickets/<int:pk>/update/', views.ticket_update, name='ticket_update'),
    path('interconnects/', views.interconnect_list, name='interconnect_list'),
]
