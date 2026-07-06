from django.urls import path
from . import api

urlpatterns = [
    path('cdr/ingest/', api.cdr_ingest, name='cdr_ingest'),
]
