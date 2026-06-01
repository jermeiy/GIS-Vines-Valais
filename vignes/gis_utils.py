"""
GIS utilities for processing vine cadastre data and calculating AHP scores.
Implements 6-criteria Analytic Hierarchy Process with eigenvector method.
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
    6-Criteria Analytic Hierarchy Process (AHP) scorer for vine parcels.
    
    Criteria:
    - pente (slope): steeper = higher score
    - surface: smaller parcel = higher score (INVERSE)
    - distance_route: farther from road = higher score
    - orientation: north-facing (180°) = higher, south-facing (0°/360°) = lower
    - altitude: higher = higher score
    - distance_urbain: closer to city = higher score (INVERSE)
    """
    
    # 6x6 Pairwise Comparison Matrix
    # Edit these ratios to change relative importance of criteria
    # A[i][j] = importance of criterion i relative to criterion j
    PAIRWISE_MATRIX = np.array([
        [1.0,  2.0,  3.0,  2.0,  2.0,  1.0],    # pente vs others
        [0.5,  1.0,  0.5,  0.5,  0.5,  2.0],    # surface vs others
        [0.33, 2.0,  1.0,  2.0,  2.0,  1.0],    # distance_route vs others
        [0.5,  2.0,  0.5,  1.0,  0.5,  1.0],    # orientation vs others
        [0.5,  2.0,  0.5,  2.0,  1.0,  1.0],    # altitude vs others
        [1.0,  0.5,  1.0,  1.0,  1.0,  1.0]     # distance_urbain vs others
    ], dtype=float)
    
    # Criterion names (order matches matrix rows/cols)
    CRITERIA = ['pente', 'surface', 'distance_route', 'orientation', 'altitude', 'distance_urbain']
    
    # Track computed weights
    WEIGHTS = None
    CONSISTENCY_RATIO = None
    
    @classmethod
    def compute_weights(cls):
        """
        Compute AHP weights using eigenvector method.
        Returns dict of criterion -> weight and updates CONSISTENCY_RATIO.
        Prints warning if CR > 0.10.
        """
        if cls.WEIGHTS is not None:
            return cls.WEIGHTS  # Return cached weights
        
        # Normalize each column
        col_sums = np.sum(cls.PAIRWISE_MATRIX, axis=0)
        normalized = cls.PAIRWISE_MATRIX / col_sums
        
        # Calculate weights as row averages
        weights = np.mean(normalized, axis=1)
        
        # Calculate consistency ratio
        # 1. Calculate A * w (matrix-vector product)
        aw = np.dot(cls.PAIRWISE_MATRIX, weights)
        
        # 2. Calculate λ_max (principal eigenvalue)
        lambda_max = np.mean(aw / weights)
        
        # 3. Calculate consistency index
        n = len(weights)
        ci = (lambda_max - n) / (n - 1)
        
        # 4. Random Index for n=6
        ri_values = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45}
        ri = ri_values.get(n, 1.24)
        
        # 5. Consistency ratio
        cr = ci / ri if ri != 0 else 0
        cls.CONSISTENCY_RATIO = cr
        
        if cr > 0.10:
            print(f"⚠️ AHP Consistency Ratio ({cr:.3f}) exceeds 0.10 - matrix may need review")
        else:
            print(f"✓ AHP Consistency Ratio: {cr:.3f} (acceptable)")
        
        # Store weights as dict
        cls.WEIGHTS = {cls.CRITERIA[i]: float(weights[i]) for i in range(n)}
        return cls.WEIGHTS
    
    @staticmethod
    def normalize_value(value, min_val, max_val):
        """Normalize a value to [0, 1] range"""
        if max_val == min_val:
            return 0.5
        return (value - min_val) / (max_val - min_val)
    
    @staticmethod
    def score_pente(pente, min_val=0, max_val=60):
        """Slope: steeper = higher score. Normalized to [0, 1]."""
        normalized = AHPScorer.normalize_value(pente, min_val, max_val)
        return np.clip(normalized, 0, 1)
    
    @staticmethod
    def score_surface(surface, min_val=100, max_val=50000):
        """Surface: smaller = higher score (INVERSE). Normalized to [0, 1]."""
        normalized = AHPScorer.normalize_value(surface, min_val, max_val)
        return np.clip(1 - normalized, 0, 1)  # Invert
    
    @staticmethod
    def score_distance_route(distance_route, min_val=0, max_val=1000):
        """Distance to road: farther = higher score. Normalized to [0, 1]."""
        normalized = AHPScorer.normalize_value(distance_route, min_val, max_val)
        return np.clip(normalized, 0, 1)
    
    @staticmethod
    def score_orientation(orientation, min_val=0, max_val=360):
        """
        Orientation: north-facing (180°) = higher, south-facing (0°/360°) = lower.
        Normalized to [0, 1]. Computes distance to north (180°) as: 1 - |orientation - 180| / 180
        """
        # Normalize orientation to [0, 360)
        orientation = orientation % 360
        
        # Distance from north (180°)
        distance_from_north = min(abs(orientation - 180), 360 - abs(orientation - 180))
        normalized = 1 - (distance_from_north / 180)
        
        return np.clip(normalized, 0, 1)
    
    @staticmethod
    def score_altitude(altitude, min_val=300, max_val=2000):
        """Altitude: higher = higher score. Normalized to [0, 1]."""
        normalized = AHPScorer.normalize_value(altitude, min_val, max_val)
        return np.clip(normalized, 0, 1)
    
    @staticmethod
    def score_distance_urbain(distance_urbain, min_val=0, max_val=10000):
        """Distance to city: closer = higher score (INVERSE). Normalized to [0, 1]."""
        normalized = AHPScorer.normalize_value(distance_urbain, min_val, max_val)
        return np.clip(1 - normalized, 0, 1)  # Invert
    
    @classmethod
    def calculate_score(cls, feature):
        """
        Calculate 6-criteria AHP score for a feature.
        
        Returns dict with:
        - ahp_score: weighted score [0, 1]
        - individual_scores: dict of score_criterion for each criterion
        - weights: dict of computed weights
        
        Note: Shapefile field names are truncated to 10 chars, so:
        - distance_route -> distance_r
        - distance_urbain -> distance_u
        - orientation -> orientatio
        """
        # Compute weights on first call
        if cls.WEIGHTS is None:
            cls.compute_weights()
        
        props = feature.get('properties', {})
        
        # Extract values from properties (handle shapefile field name truncation)
        pente = float(props.get('pente', 0))
        surface = float(props.get('surface', 0))
        distance_route = float(props.get('distance_route') or props.get('distance_r', 0))
        orientation = float(props.get('orientation') or props.get('orientatio', 0))
        altitude = float(props.get('altitude', 0))
        distance_urbain = float(props.get('distance_urbain') or props.get('distance_u', 0))
        
        # Calculate individual normalized scores [0, 1]
        scores = {
            'pente': cls.score_pente(pente),
            'surface': cls.score_surface(surface),
            'distance_route': cls.score_distance_route(distance_route),
            'orientation': cls.score_orientation(orientation),
            'altitude': cls.score_altitude(altitude),
            'distance_urbain': cls.score_distance_urbain(distance_urbain)
        }
        
        # Calculate weighted AHP score
        ahp_score = sum(cls.WEIGHTS[criterion] * scores[criterion] for criterion in cls.CRITERIA)
        
        return {
            'ahp_score': np.clip(float(ahp_score), 0, 1),
            'individual_scores': {f'score_{k}': float(v) for k, v in scores.items()},
            'weights': cls.WEIGHTS
        }


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
        Load shapefile, calculate 6-criteria AHP scores, and generate GeoJSON.
        Returns GeoJSON FeatureCollection with individual scores and weights.
        """
        gdf = self.load_shapefile()
        
        # Convert to GeoJSON
        geojson = json.loads(gdf.to_json())
        
        # Calculate and add AHP scores to each feature
        for feature in geojson['features']:
            result = AHPScorer.calculate_score(feature)
            
            # Main AHP score
            feature['properties']['ahp_score'] = result['ahp_score']
            feature['properties']['score_percent'] = f"{result['ahp_score'] * 100:.1f}%"
            
            # Individual criterion scores
            for criterion, score_val in result['individual_scores'].items():
                feature['properties'][criterion] = score_val
            
            # Weights (same for all features, but included for client-side use)
            feature['properties']['ahp_weights'] = result['weights']
            
            # Priority level
            score = result['ahp_score']
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
