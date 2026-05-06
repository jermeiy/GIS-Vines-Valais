"""
Test script for GIS utilities
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, 'c:\\Users\\chipi\\Documents\\Visual Studio 2017\\GIS\\GIS-Vines-Valais')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from vignes.gis_utils import AHPScorer, GISProcessor

# Test AHP Scorer
print("=" * 60)
print("Testing AHP Scorer")
print("=" * 60)

# Test feature
test_feature = {
    "properties": {
        "id": 1,
        "pente": 25,
        "distance_route": 150,
        "surface": 1500
    }
}

score = AHPScorer.calculate_score(test_feature)
print(f"\nTest Feature:")
print(f"  Slope (pente): {test_feature['properties']['pente']}°")
print(f"  Distance to road: {test_feature['properties']['distance_route']}m")
print(f"  Area (surface): {test_feature['properties']['surface']}m²")
print(f"\n  Calculated AHP Score: {score:.3f} ({score*100:.1f}%)")

# Test color mapping
from vignes.gis_utils import AHPScorer

def get_priority_color(score):
    if score > 0.75:
        return "#d73027 (RED - High Priority)"
    elif score > 0.50:
        return "#fc8d59 (ORANGE - Medium Priority)"
    elif score > 0.25:
        return "#fee08b (YELLOW - Low Priority)"
    else:
        return "#1a9850 (GREEN - Very Low Priority)"

print(f"  Color: {get_priority_color(score)}")

print("\n" + "=" * 60)
print("Testing various scenarios")
print("=" * 60)

scenarios = [
    {"name": "Steep terrain, far from road, large area", "pente": 45, "distance_route": 500, "surface": 5000},
    {"name": "Flat, close to road, small area", "pente": 5, "distance_route": 50, "surface": 500},
    {"name": "Medium slope, medium distance, medium area", "pente": 20, "distance_route": 200, "surface": 2000},
]

for scenario in scenarios:
    test_feat = {
        "properties": {
            "pente": scenario["pente"],
            "distance_route": scenario["distance_route"],
            "surface": scenario["surface"]
        }
    }
    score = AHPScorer.calculate_score(test_feat)
    print(f"\n{scenario['name']}:")
    print(f"  Slope: {scenario['pente']}°, Distance: {scenario['distance_route']}m, Area: {scenario['surface']}m²")
    print(f"  Score: {score:.3f} ({score*100:.1f}%) → {get_priority_color(score)}")

print("\n" + "=" * 60)
print("GIS Processor Test")
print("=" * 60)

processor = GISProcessor()
shapefile_path = processor.shapefile_path
print(f"\nShapefile path: {shapefile_path}")
print(f"File exists: {os.path.exists(shapefile_path)}")

if os.path.exists(shapefile_path):
    try:
        gdf = processor.load_shapefile()
        print(f"✓ Shapefile loaded successfully")
        print(f"  CRS: {gdf.crs}")
        print(f"  Number of features: {len(gdf)}")
        print(f"  Columns: {list(gdf.columns)}")
        
        # Try generating GeoJSON
        geojson = processor.generate_geojson_with_scores()
        print(f"\n✓ GeoJSON generated successfully")
        print(f"  Number of features in GeoJSON: {len(geojson['features'])}")
        if geojson['features']:
            first_feature = geojson['features'][0]
            print(f"  First feature properties: {list(first_feature['properties'].keys())}")
    except Exception as e:
        print(f"✗ Error: {e}")
else:
    print(f"✗ Shapefile not found")
    print("\nNote: The complete Shapefile (with .shx and .dbf files) is required.")
    print("Sample test completed with synthetic data.")

print("\n" + "=" * 60)
print("Test completed!")
print("=" * 60)
