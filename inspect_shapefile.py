import geopandas as gpd
import os

shapefile_path = os.path.join('data', 'cadastre_viticole.shp')
gdf = gpd.read_file(shapefile_path)
print("Shapefile columns:", gdf.columns.tolist())
print("\nFirst row:")
print(gdf.iloc[0])
print("\nCRS:", gdf.crs)
print("\nDataframe info:")
print(gdf.info())
print("\nShape:", gdf.shape)
print("\nColumn statistics:")
print(gdf.describe())
