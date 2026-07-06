from django.contrib import admin
from .models import Company, Switch, Destination, DisconnectCause

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display  = ['name', 'customer_number', 'role', 'currency', 'vat_exempt', 'is_active']
    list_filter   = ['role', 'is_active', 'currency', 'vat_exempt', 'account_managers']
    search_fields = ['name', 'customer_number']
    list_editable = ['customer_number', 'vat_exempt']
    filter_horizontal = ['account_managers', 'portal_users']

@admin.register(Switch)
class SwitchAdmin(admin.ModelAdmin):
    list_display = ['name', 'ip_address', 'is_active', 'api_token', 'last_updated']
    readonly_fields = ['api_token']

@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ['prefix', 'name', 'country', 'is_active']
    search_fields = ['prefix', 'name', 'country']

@admin.register(DisconnectCause)
class DisconnectCauseAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']
