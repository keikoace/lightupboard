from django.urls import path
from . import views

app_name = 'graphs'

urlpatterns = [
    path('hourly/', views.hourly_minutes, name='hourly_minutes'),
    path('top-ten/', views.top_ten, name='top_ten'),
    path('minutes-trends/', views.minutes_trends, name='minutes_trends'),
    path('gp-trends/', views.gp_trends, name='gp_trends'),
    path('drilldown/', views.drilldown, name='drilldown'),
    path('world-map/', views.world_map, name='world_map'),
    path('term-deals/', views.term_deals, name='term_deals'),
]
