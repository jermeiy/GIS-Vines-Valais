from django.urls import path
from . import views

urlpatterns = [
    path('',               views.index,        name='index'),
    path('api/parcelles/', views.api_parcelles, name='api-parcelles'),
    path('api/regions/',   views.api_regions,   name='api-regions'),
]
