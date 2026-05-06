"""
Quick test of the Django API
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from vignes.gis_utils import get_geojson_parcelles

# Get the GeoJSON
geojson = get_geojson_parcelles()

if geojson:
    print("✓ GeoJSON generated successfully")
    print(f"  Total features: {len(geojson['features'])}")
    
    # Show first feature
    first = geojson['features'][0]
    print(f"\n  First feature properties:")
    for key, val in first['properties'].items():
        print(f"    {key}: {val}")
    
    # Calculate some statistics
    scores = [f['properties']['ahp_score'] for f in geojson['features']]
    print(f"\n  Score statistics:")
    print(f"    Min: {min(scores):.3f}")
    print(f"    Max: {max(scores):.3f}")
    print(f"    Mean: {sum(scores)/len(scores):.3f}")
    
    # Count by priority
    priorities = {}
    for f in geojson['features']:
        p = f['properties'].get('priority', 'Unknown')
        priorities[p] = priorities.get(p, 0) + 1
    
    print(f"\n  Parcels by priority:")
    for priority in ['Haute', 'Moyenne', 'Basse', 'Très Basse']:
        count = priorities.get(priority, 0)
        print(f"    {priority}: {count}")
    
    print(f"\n✓ System is ready!")
else:
    print("✗ Failed to generate GeoJSON")
