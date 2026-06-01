from django.shortcuts import render
from django.http import JsonResponse
import json
from .gis_utils import get_geojson_parcelles


def index(request):
    """Render the main map view"""
    return render(request, 'index.html')


def get_parcelles(request):
    """
    Fetch parcelles from Shapefile and return as GeoJSON with 6-criteria AHP scores.
    Returns individual criterion scores and computed weights.
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
                            "distance_route": 150,
                            "orientation": 180,
                            "altitude": 800,
                            "distance_urbain": 5000,
                            "score_pente": 0.42,
                            "score_surface": 0.65,
                            "score_distance_route": 0.15,
                            "score_orientation": 0.95,
                            "score_altitude": 0.35,
                            "score_distance_urbain": 0.50,
                            "ahp_weights": {
                                "pente": 0.24,
                                "surface": 0.15,
                                "distance_route": 0.18,
                                "orientation": 0.16,
                                "altitude": 0.17,
                                "distance_urbain": 0.10
                            }
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