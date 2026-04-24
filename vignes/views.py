from django.shortcuts import render
from django.http import JsonResponse
import json
from .models import Parcelle

def index(request):
    return render(request, 'index.html')

def get_parcelles(request):
    """Fetch parcelles from database and return as GeoJSON"""
    parcelles = Parcelle.objects.all()
    
    # If no parcelles in database, return sample data
    if not parcelles.exists():
        sample_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [7.36, 46.23]},
                    "properties": {"nom": "Parcelle Valais 1", "score": 0.75}
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [7.40, 46.25]},
                    "properties": {"nom": "Parcelle Valais 2", "score": 0.85}
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [7.32, 46.20]},
                    "properties": {"nom": "Parcelle Valais 3", "score": 0.65}
                }
            ]
        }
        return JsonResponse(sample_data)
    
    # Return real data from database
    features = [parcelle.to_geojson_feature() for parcelle in parcelles]
    geojson_data = {
        "type": "FeatureCollection",
        "features": features
    }
    return JsonResponse(geojson_data)