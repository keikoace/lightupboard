from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', include('apps.core.urls')),
    path('setup/', include('apps.setup.urls')),
    path('rates/', include('apps.rates.urls')),
    path('ddi/', include('apps.ddi.urls')),
    path('finance/', include('apps.finance.urls')),
    path('qos/', include('apps.qos.urls')),
    path('alerts/', include('apps.alerts.urls')),
    path('graphs/', include('apps.graphs.urls')),
    # Switch CDR ingestion REST API (no session auth — uses per-switch token)
    path('api/', include('apps.qos.api_urls')),
    # Customer portal (separate login, light theme)
    path('portal/', include('apps.portal.urls')),
    path('email-import/', include('apps.email_import.urls')),
]
