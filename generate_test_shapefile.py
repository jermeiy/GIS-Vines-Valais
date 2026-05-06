"""
Generate a test Shapefile with vine parcels for the Valais region.
This creates a complete, valid Shapefile for testing purposes.

Usage:
    python generate_test_shapefile.py
"""
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Polygon
import os

def generate_test_parcels():
    """Generate test parcels covering Valais region"""
    
    # Define a grid of parcels in Valais region (roughly 46°N, 7.5°E)
    center_lat = 46.3
    center_lon = 7.8
    
    # Grid parameters
    lat_range = 0.5  # ~55 km north-south
    lon_range = 0.8  # ~65 km east-west
    grid_size = 0.05  # Cell size
    
    parcels = []
    parcel_id = 1
    
    # Generate regular grid
    lats = np.arange(center_lat - lat_range/2, center_lat + lat_range/2, grid_size)
    lons = np.arange(center_lon - lon_range/2, center_lon + lon_range/2, grid_size)
    
    for lat in lats:
        for lon in lons:
            # Add some random variation to avoid perfect grid
            lat_var = np.random.uniform(-0.01, 0.01)
            lon_var = np.random.uniform(-0.01, 0.01)
            
            # Create small polygon (parcel)
            coords = [
                (lon + lon_var, lat + lat_var),
                (lon + lon_var + grid_size/2, lat + lat_var),
                (lon + lon_var + grid_size/2, lat + lat_var + grid_size/2),
                (lon + lon_var, lat + lat_var + grid_size/2),
                (lon + lon_var, lat + lat_var),
            ]
            
            polygon = Polygon(coords)
            
            # Generate attributes
            # Slope: 0-45 degrees, tends to be higher in mountainous areas
            pente = np.random.uniform(5, 45)
            
            # Distance to road: 0-500 meters
            distance_route = np.random.uniform(50, 500)
            
            # Surface: 500-5000 m²
            surface = np.random.uniform(500, 5000)
            
            parcels.append({
                'geometry': polygon,
                'id': parcel_id,
                'pente': pente,
                'distance_route': distance_route,
                'surface': surface,
            })
            
            parcel_id += 1
    
    return parcels

def create_test_shapefile(output_path='data/cadastre_viticole.shp'):
    """Create a test Shapefile with generated parcels"""
    
    print("Generating test parcels...")
    parcels = generate_test_parcels()
    print(f"Generated {len(parcels)} parcels")
    
    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame(parcels, crs='EPSG:4326')
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    
    # Save to Shapefile
    print(f"Saving Shapefile to {output_path}...")
    gdf.to_file(output_path, driver='ESRI Shapefile')
    
    # Verify
    if os.path.exists(output_path):
        print(f"✓ Successfully created {output_path}")
        
        # Verify all components
        base_path = output_path.replace('.shp', '')
        components = ['.shp', '.shx', '.dbf', '.prj']
        for ext in components:
            file_path = base_path + ext
            if os.path.exists(file_path):
                size = os.path.getsize(file_path)
                print(f"  ✓ {os.path.basename(file_path):<20} ({size:,} bytes)")
            else:
                print(f"  ✗ {os.path.basename(file_path):<20} MISSING")
        
        # Display statistics
        print("\nDataFrame Statistics:")
        print(f"  Total parcels: {len(gdf)}")
        print(f"\n  Slope (pente):")
        print(f"    Min:  {gdf['pente'].min():.2f}°")
        print(f"    Max:  {gdf['pente'].max():.2f}°")
        print(f"    Mean: {gdf['pente'].mean():.2f}°")
        
        print(f"\n  Distance to road:")
        print(f"    Min:  {gdf['distance_route'].min():.0f}m")
        print(f"    Max:  {gdf['distance_route'].max():.0f}m")
        print(f"    Mean: {gdf['distance_route'].mean():.0f}m")
        
        print(f"\n  Area (surface):")
        print(f"    Min:  {gdf['surface'].min():.0f}m²")
        print(f"    Max:  {gdf['surface'].max():.0f}m²")
        print(f"    Mean: {gdf['surface'].mean():.0f}m²")
        
        print("\n✓ Test Shapefile created successfully!")
        print("  You can now run the Django server to test the application")
        print("  python manage.py runserver 8080")
        return True
    else:
        print(f"✗ Failed to create Shapefile")
        return False


if __name__ == '__main__':
    try:
        create_test_shapefile()
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
