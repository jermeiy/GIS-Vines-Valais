from django.shortcuts import render
from django.http import JsonResponse
from .gis_utils import get_geojson_for_region, REGIONS


def index(request):
    return render(request, 'index.html')


def api_parcelles(request):
    """GeoJSON d'un district avec scores AHP. Param: ?region=sion"""
    region_key = request.GET.get('region', 'sion')

    if region_key not in REGIONS:
        return JsonResponse({'error': f"Région inconnue: '{region_key}'"}, status=400)

    try:
        return JsonResponse(get_geojson_for_region(region_key))
    except FileNotFoundError as e:
        return JsonResponse({'error': str(e)}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_regions(request):
    """Liste des districts disponibles."""
    return JsonResponse({'regions': [
        {'key': k, 'nom': v['nom'], 'centre': v['centre'], 'zoom': v['zoom']}
        for k, v in REGIONS.items()
    ]})
