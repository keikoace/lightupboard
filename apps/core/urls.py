from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('import-dest/', views.import_destinations, name='import_destinations'),
]
