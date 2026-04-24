from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('api/parcelles/', views.get_parcelles, name='parcelles'),
]