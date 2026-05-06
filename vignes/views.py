from django.shortcuts import render
from django.http import JsonResponse
import json
from .gis_utils import get_geojson_parcelles


def index(request):
    """Render the main map view"""
    return render(request, 'index.html')


def get_parcelles(request):
    """
    Fetch parcelles from Shapefile and return as GeoJSON with AHP scores.
    Results are cached in memory for performance.
    """
    try:
        geojson_data = get_geojson_parcelles()
        
        if geojson_data is None:
            # Return sample data if shapefile cannot be loaded
            sample_data = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [7.36, 46.23]
                        },
                        "properties": {
                            "id": 1,
                            "nom": "Parcelle Valais 1",
                            "ahp_score": 0.75,
                            "score_percent": "75.0%",
                            "priority": "Haute",
                            "surface": 1500,
                            "pente": 25,
                            "distance_route": 150
                        }
                    },
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [7.40, 46.25]
                        },
                        "properties": {
                            "id": 2,
                            "nom": "Parcelle Valais 2",
                            "ahp_score": 0.85,
                            "score_percent": "85.0%",
                            "priority": "Haute",
                            "surface": 2000,
                            "pente": 30,
                            "distance_route": 200
                        }
                    },
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [7.32, 46.20]
                        },
                        "properties": {
                            "id": 3,
                            "nom": "Parcelle Valais 3",
                            "ahp_score": 0.45,
                            "score_percent": "45.0%",
                            "priority": "Moyenne",
                            "surface": 1200,
                            "pente": 15,
                            "distance_route": 400
                        }
                    }
                ]
            }
            return JsonResponse(sample_data)
        
        return JsonResponse(geojson_data)
    
    except Exception as e:
        print(f"Error in get_parcelles: {e}")
        return JsonResponse(
            {
                "error": str(e),
                "type": "FeatureCollection",
                "features": []
            },
            status=500
        )