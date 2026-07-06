from django.contrib import admin
from apps.setup.models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display  = ('pk', 'subject', 'company', 'priority', 'status', 'created_by', 'created_at')
    list_filter   = ('status', 'priority')
    search_fields = ('subject', 'description', 'company__name')
    date_hierarchy = 'created_at'
