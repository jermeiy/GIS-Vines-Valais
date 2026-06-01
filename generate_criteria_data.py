"""
Generate realistic criterion data for the cadastre viticole shapefile.
This script adds synthetic but realistic values based on the actual geometry and location.
"""
import geopandas as gpd
import numpy as np
from shapely.geometry import Point
import warnings
warnings.filterwarnings('ignore')

# Load the shapefile
print("Loading shapefile...")
gdf = gpd.read_file('data/cadastre_viticole.shp')
print(f"Loaded {len(gdf)} parcels")

# Known cities in Valais (Sion, Martigny, Monthey coordinates in EPSG:4326)
VALAIS_CITIES = [
    {'name': 'Sion', 'coords': (7.239, 46.209)},
    {'name': 'Martigny', 'coords': (7.056, 46.062)},
    {'name': 'Monthey', 'coords': (6.794, 46.266)}
]

# Convert to EPSG:4326 if needed for distance calculations
if gdf.crs != 'EPSG:4326':
    if gdf.crs is None:
        print("Setting CRS to EPSG:2154 (assumed Lambert-93)...")
        gdf = gdf.set_crs('EPSG:2154')
    gdf_wgs84 = gdf.to_crs('EPSG:4326')
else:
    gdf_wgs84 = gdf.copy()

# Calculate centroid for distance calculations
gdf['centroid'] = gdf_wgs84.geometry.centroid

# 1. SURFACE: Use existing surface_m2 data (convert to m²)
print("\n1. Calculating SURFACE...")
gdf['surface'] = gdf['surface_m2'].astype(float)
print(f"   Range: {gdf['surface'].min():.0f} - {gdf['surface'].max():.0f} m²")

# 2. PENTE (Slope): Generate realistic slope based on:
#    - Parcels in Valais can range from 0° (flat valley) to 45° (steep hillside)
#    - Assume some parcels are on slopes, others in flat areas
print("\n2. Calculating PENTE (Slope)...")
np.random.seed(42)  # For reproducibility
# Generate base slope with variation
base_slope = np.random.uniform(5, 35, len(gdf))
# Add some structure: parcels with larger areas tend to be on gentler slopes
area_normalized = (gdf['surface'] - gdf['surface'].min()) / (gdf['surface'].max() - gdf['surface'].min())
pente = base_slope * (1 - area_normalized * 0.4)  # Larger areas -> gentler slopes
gdf['pente'] = np.clip(pente, 2, 50)  # Clip to realistic range
print(f"   Range: {gdf['pente'].min():.1f}° - {gdf['pente'].max():.1f}°")

# 3. ORIENTATION: Calculate from polygon orientation
#    - North = 180°, South = 0°/360°, East = 90°, West = 270°
print("\n3. Calculating ORIENTATION...")
def get_polygon_orientation(geom):
    """Get approximate orientation of polygon (angle of major axis)"""
    if geom.is_empty:
        return 0
    coords = np.array(geom.exterior.coords)
    if len(coords) < 3:
        return 0
    # Use PCA-like approach: calculate principal direction
    center = coords.mean(axis=0)
    centered = coords - center
    # Calculate moment of inertia to find principal axis
    try:
        cov_matrix = np.cov(centered.T)
        eigenvalues, eigenvectors = np.linalg.eig(cov_matrix)
        principal_axis = eigenvectors[:, np.argmax(eigenvalues)]
        # Convert to degrees (0-360)
        angle = np.arctan2(principal_axis[1], principal_axis[0]) * 180 / np.pi
        # Map to 0-360 range where 180 = North
        orientation = (angle + 90) % 360
        return orientation
    except:
        return np.random.uniform(0, 360)

orientations = []
for geom in gdf.geometry:
    try:
        if geom.geom_type == 'Polygon':
            orientation = get_polygon_orientation(geom)
        else:
            # For MultiPolygon or other types, use largest part
            if hasattr(geom, 'geoms'):
                orientation = get_polygon_orientation(max(geom.geoms, key=lambda g: g.area))
            else:
                orientation = np.random.uniform(0, 360)
        orientations.append(orientation)
    except:
        orientations.append(np.random.uniform(0, 360))

gdf['orientation'] = orientations
print(f"   Range: {gdf['orientation'].min():.1f}° - {gdf['orientation'].max():.1f}°")

# 4. ALTITUDE: Realistic for Valais (300-2000m, higher in mountains)
#    - Assume centroid location gives hint at elevation
print("\n4. Calculating ALTITUDE...")
# Base elevation varies with location (southern parts tend to be lower)
lat = gdf_wgs84.geometry.centroid.y
lon = gdf_wgs84.geometry.centroid.x
# Rough Valais elevation model: lower in northwest, higher in southeast
base_alt = 500 + (lon - 6.5) * 200 + (46.3 - lat) * 150
altitude = base_alt + np.random.normal(0, 100, len(gdf))
gdf['altitude'] = np.clip(altitude, 300, 2200)
print(f"   Range: {gdf['altitude'].min():.0f} - {gdf['altitude'].max():.0f} m")

# 5. DISTANCE_URBAIN: Distance to nearest city in Valais
print("\n5. Calculating DISTANCE_URBAIN...")
distances_urbain = []
for centroid in gdf_wgs84.geometry.centroid:
    min_dist = min(
        centroid.distance(Point(city['coords'])) * 111000  # Convert degrees to meters
        for city in VALAIS_CITIES
    )
    distances_urbain.append(min_dist)

gdf['distance_urbain'] = distances_urbain
print(f"   Range: {min(distances_urbain):.0f} - {max(distances_urbain):.0f} m")

# 6. DISTANCE_ROUTE: Distance to nearest "road"
#    - Generate synthetic road network, assume roads in valley (low y-coordinate regions)
#    - Distance increases with elevation
print("\n6. Calculating DISTANCE_ROUTE...")
distance_route = []
for idx, row in gdf.iterrows():
    # Simulate roads following valley pattern (roads are easier to access in flat areas)
    # Distance to road increases with altitude
    base_dist = 50 + (row['altitude'] - 300) * 0.15  # Higher altitude = farther from roads
    # Add some randomness
    dist = base_dist + np.random.normal(0, 100)
    distance_route.append(max(50, dist))  # Minimum distance 50m

gdf['distance_route'] = distance_route
print(f"   Range: {min(distance_route):.0f} - {max(distance_route):.0f} m")

# Drop temporary columns
gdf = gdf.drop(columns=['centroid'])

print("\n" + "="*60)
print("Summary of generated criteria:")
print("="*60)
for col in ['pente', 'surface', 'distance_route', 'orientation', 'altitude', 'distance_urbain']:
    print(f"{col:18s}: min={gdf[col].min():10.1f}, max={gdf[col].max():10.1f}, mean={gdf[col].mean():10.1f}")

# Save back to shapefile
print("\nSaving updated shapefile...")
gdf.to_file('data/cadastre_viticole.shp', index=False)
print("✓ Shapefile updated successfully!")
print("\nYou can now restart the server to see the AHP scores in action.")
