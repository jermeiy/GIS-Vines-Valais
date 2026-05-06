"""
GIS utilities for processing vine cadastre data and calculating AHP scores.
"""
import os
import json
import geopandas as gpd
import numpy as np
from pathlib import Path
from django.conf import settings

# Cache for GeoJSON data
_geojson_cache = None
_cache_timestamp = None


class AHPScorer:
    """
    Analytic Hierarchy Process (AHP) scorer for vine parcels.
    Weights: slope 40%, distance to road 30%, area 30%
    """
    
    # AHP weights
    WEIGHTS = {
        'slope': 0.40,
        'distance_road': 0.30,
        'area': 0.30
    }
    
    @staticmethod
    def normalize_value(value, min_val, max_val):
        """Normalize a value to [0, 1] range"""
        if max_val == min_val:
            return 0.5
        return (value - min_val) / (max_val - min_val)
    
    @staticmethod
    def score_slope(slope, min_slope=0, max_slope=60):
        """
        Higher slope = higher priority (easier to uproot on steep terrain)
        Normalized to [0, 1]
        """
        normalized = AHPScorer.normalize_value(slope, min_slope, max_slope)
        return np.clip(normalized, 0, 1)
    
    @staticmethod
    def score_distance_road(distance_m, min_dist=0, max_dist=1000):
        """
        Farther from road = higher priority (more difficult to access)
        Normalized to [0, 1] inverted
        """
        normalized = AHPScorer.normalize_value(distance_m, min_dist, max_dist)
        return np.clip(1 - normalized, 0, 1)  # Invert: more distance = higher score
    
    @staticmethod
    def score_area(area_m2, min_area=100, max_area=50000):
        """
        Larger area = higher priority (more efficient uprooting)
        Normalized to [0, 1]
        """
        normalized = AHPScorer.normalize_value(area_m2, min_area, max_area)
        return np.clip(normalized, 0, 1)
    
    @classmethod
    def calculate_score(cls, feature):
        """
        Calculate AHP score for a feature.
        
        Expects feature properties to have:
        - pente (slope in degrees)
        - distance_route or distance_r (distance to road in meters) 
          Note: Shapefile truncates to 10 chars, so check both names
        - surface (area in m²)
        """
        props = feature.get('properties', {})
        
        # Get values with defaults, handle both full and truncated field names
        slope = float(props.get('pente', 0))
        distance_road = float(props.get('distance_route') or props.get('distance_r', 0))
        area = float(props.get('surface', 0))
        
        # Calculate individual scores
        score_s = cls.score_slope(slope)
        score_d = cls.score_distance_road(distance_road)
        score_a = cls.score_area(area)
        
        # Calculate weighted AHP score
        ahp_score = (
            cls.WEIGHTS['slope'] * score_s +
            cls.WEIGHTS['distance_road'] * score_d +
            cls.WEIGHTS['area'] * score_a
        )
        
        return np.clip(ahp_score, 0, 1)


class GISProcessor:
    """Process GIS data and generate GeoJSON with AHP scores."""
    
    def __init__(self):
        self.shapefile_path = os.path.join(settings.BASE_DIR, 'data', 'cadastre_viticole.shp')
    
    def load_shapefile(self):
        """Load shapefile and convert to EPSG:4326"""
        if not os.path.exists(self.shapefile_path):
            raise FileNotFoundError(f"Shapefile not found at {self.shapefile_path}")
        
        # Read shapefile
        gdf = gpd.read_file(self.shapefile_path)
        
        # Convert to EPSG:4326 if needed
        if gdf.crs is None:
            print(f"Warning: No CRS found in shapefile, assuming EPSG:2154 (Lambert-93)")
            gdf = gdf.set_crs('EPSG:2154')
        
        if gdf.crs != 'EPSG:4326':
            gdf = gdf.to_crs('EPSG:4326')
        
        return gdf
    
    def generate_geojson_with_scores(self):
        """
        Load shapefile, calculate AHP scores, and generate GeoJSON.
        Returns GeoJSON FeatureCollection with scores.
        """
        gdf = self.load_shapefile()
        
        # Convert to GeoJSON
        geojson = json.loads(gdf.to_json())
        
        # Calculate and add AHP scores to each feature
        for feature in geojson['features']:
            score = AHPScorer.calculate_score(feature)
            feature['properties']['ahp_score'] = float(score)
            
            # Add readable score percentage
            feature['properties']['score_percent'] = f"{score * 100:.1f}%"
            
            # Add priority level
            if score > 0.75:
                feature['properties']['priority'] = 'Haute'
            elif score > 0.50:
                feature['properties']['priority'] = 'Moyenne'
            elif score > 0.25:
                feature['properties']['priority'] = 'Basse'
            else:
                feature['properties']['priority'] = 'Très Basse'
        
        return geojson
    
    @staticmethod
    def get_cached_geojson():
        """Get cached GeoJSON, regenerate if needed"""
        global _geojson_cache
        
        if _geojson_cache is None:
            processor = GISProcessor()
            try:
                _geojson_cache = processor.generate_geojson_with_scores()
            except Exception as e:
                print(f"Error loading shapefile: {e}")
                _geojson_cache = None
        
        return _geojson_cache


def get_geojson_parcelles():
    """
    Main entry point to get parcelles as GeoJSON with scores.
    Returns cached result if available.
    """
    return GISProcessor.get_cached_geojson()
