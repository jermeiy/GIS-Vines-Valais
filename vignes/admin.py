from django.contrib import admin
from .models import Parcelle

@admin.register(Parcelle)
class ParcelleAdmin(admin.ModelAdmin):
    list_display = ('nom', 'score', 'latitude', 'longitude', 'date_updated')
    list_filter = ('score', 'date_created')
    search_fields = ('nom',)
    readonly_fields = ('date_created', 'date_updated')
    fieldsets = (
        ('Information', {
            'fields': ('nom', 'score')
        }),
        ('Localisation', {
            'fields': ('latitude', 'longitude', 'geometry_geojson')
        }),
        ('Dates', {
            'fields': ('date_created', 'date_updated'),
            'classes': ('collapse',)
        }),
    )
