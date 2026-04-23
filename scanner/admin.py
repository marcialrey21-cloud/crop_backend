from django.contrib import admin
from .models import ScanHistory

# This tells Django how to display your data in the admin panel
@admin.register(ScanHistory)
class ScanHistoryAdmin(admin.ModelAdmin):
    # This creates neat columns for your dashboard
    list_display = ('disease_name', 'confidence_score', 'created_at')
    # This prevents the date from being accidentally edited
    readonly_fields = ('created_at',)