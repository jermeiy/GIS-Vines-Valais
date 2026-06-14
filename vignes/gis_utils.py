"""
Utilitaires GIS — cadastre viticole valaisan.

Flux:
  shapefile (55k parcelles)
  → filtre par district (colonne 'district' ou bbox fallback)
  → 6 scores individuels normalisés [0-1] par parcelle
  → score AHP = somme pondérée
  → GeoJSON servi au frontend
"""

import os
import json
import geopandas as gpd
import numpy as np
from django.conf import settings


# ============================================================
# DISTRICTS DU VALAIS
# district_name = valeur exacte dans la colonne 'district' du shapefile
# bbox          = fallback si prepare_districts.py n'a pas été lancé
# centre/zoom   = position initiale de la carte Leaflet
# ============================================================
REGIONS = {
    # Clé → nom affiché, nom exact dans la colonne 'district' du shapefile, centre carte
    # Les noms district_name correspondent aux valeurs Swisstopo (swissBOUNDARIES3D)
    'sion':       {'nom': 'District de Sion',        'district_name': 'Sion',         'centre': [46.23, 7.37], 'zoom': 12},
    'sierre':     {'nom': 'District de Sierre',       'district_name': 'Sierre',        'centre': [46.29, 7.54], 'zoom': 12},
    'conthey':    {'nom': 'District de Conthey',      'district_name': 'Conthey',       'centre': [46.19, 7.22], 'zoom': 12},
    'martigny':   {'nom': 'District de Martigny',     'district_name': 'Martigny',      'centre': [46.10, 7.07], 'zoom': 12},
    'monthey':    {'nom': 'District de Monthey',      'district_name': 'Monthey',       'centre': [46.32, 6.87], 'zoom': 12},
    'st_maurice': {'nom': 'District de St-Maurice',   'district_name': 'Saint-Maurice', 'centre': [46.22, 6.98], 'zoom': 12},
    'leuk':       {'nom': 'District de Loèche',       'district_name': 'Leuk',          'centre': [46.31, 7.63], 'zoom': 11},
    'viege':      {'nom': 'District de Viège',        'district_name': 'Visp',          'centre': [46.29, 7.88], 'zoom': 11},
    'herens':     {'nom': "District d'Hérens",        'district_name': 'Hérens',        'centre': [46.10, 7.45], 'zoom': 11},
    'entremont':  {'nom': "District d'Entremont",     'district_name': 'Entremont',     'centre': [46.00, 7.20], 'zoom': 11},
    'brigue':     {'nom': 'District de Brigue',       'district_name': 'Brig',          'centre': [46.32, 7.98], 'zoom': 12},
    'raron':      {'nom': 'District de Rarogne',      'district_name': 'Raron',         'centre': [46.34, 7.87], 'zoom': 11},
    'conches':    {'nom': 'District de Conches',      'district_name': 'Goms',          'centre': [46.50, 8.20], 'zoom': 11},
}

# Cache GeoJSON par district (vidé au redémarrage)
_cache = {}


# ============================================================
# POIDS AHP
# Calculés depuis la matrice de comparaison par paires au chargement
# du module. La matrice encode l'importance relative de chaque critère.
# ============================================================

# A[i][j] = "le critère i est X fois plus important que le critère j"
_PAIRWISE = np.array([
    #  pente  surf  d_rte  orien  altit  d_urb
    [  1.0,   2.0,  3.0,   2.0,   2.0,   1.0],  # pente
    [  0.5,   1.0,  0.5,   0.5,   0.5,   2.0],  # surface
    [  0.33,  2.0,  1.0,   2.0,   2.0,   1.0],  # distance_route
    [  0.5,   2.0,  0.5,   1.0,   0.5,   1.0],  # orientation
    [  0.5,   2.0,  0.5,   2.0,   1.0,   1.0],  # altitude
    [  1.0,   0.5,  1.0,   1.0,   1.0,   1.0],  # distance_urbain
], dtype=float)

_CRITERIA = ['pente', 'surface', 'distance_route', 'orientation', 'altitude', 'distance_urbain']

# Normalise colonnes → moyenne lignes = poids (méthode vecteur propre approchée)
AHP_WEIGHTS = {
    _CRITERIA[i]: float(w)
    for i, w in enumerate((_PAIRWISE / _PAIRWISE.sum(axis=0)).mean(axis=1))
}


# ============================================================
# SCORES INDIVIDUELS
# Score élevé [0→1] = parcelle candidate à l'arrachage
# ============================================================

def _norm(value, min_val, max_val):
    """Normalise une valeur entre 0 et 1 selon les bornes du dataset réel."""
    if max_val == min_val:
        return 0.5
    return float(np.clip((value - min_val) / (max_val - min_val), 0, 1))


def compute_scores(props):
    """
    Calcule les 6 scores individuels [0-1] d'une parcelle.
    Noms tronqués à 10 chars dans le shapefile: orientatio, distance_r, distance_u.
    """
    pente      = float(props.get('pente', 0))
    surface    = float(props.get('surface', 0))
    dist_route = float(props.get('distance_r', 0))
    orient     = float(props.get('orientatio', 0))
    altitude   = float(props.get('altitude', 0))
    dist_urb   = float(props.get('distance_u', 0))

    # Orientation: nord (180°) = score max, sud (0°/360°) = score min
    o = orient % 360
    score_orient = float(np.clip(1 - min(abs(o - 180), 360 - abs(o - 180)) / 180, 0, 1))

    return {
        'score_pente':           _norm(pente,      0,   63),
        'score_surface':    1 -  _norm(surface,    100, 50000),  # inversé: petite = mauvais
        'score_distance_route':  _norm(dist_route, 0,   4000),
        'score_orientation':     score_orient,
        'score_altitude':        _norm(altitude,   390, 1100),
        'score_distance_urbain': 1 - _norm(dist_urb, 0, 4400),  # inversé: proche = mauvais
    }


def compute_ahp_score(scores):
    """Score AHP = somme pondérée des 6 scores. Clé = 'score_' + nom critère."""
    return float(np.clip(
        sum(AHP_WEIGHTS[c] * scores[f'score_{c}'] for c in _CRITERIA),
        0, 1
    ))


def get_priority(score):
    if score > 0.75: return 'Haute'
    if score > 0.50: return 'Moyenne'
    if score > 0.25: return 'Basse'
    return 'Très Basse'


# ============================================================
# CHARGEMENT DU SHAPEFILE
# ============================================================

def load_district(region_key):
    """Charge et filtre les parcelles du district depuis le shapefile."""
    path = os.path.join(settings.BASE_DIR, 'data', 'cadastre_viticole.shp')
    if not os.path.exists(path):
        raise FileNotFoundError(f"Shapefile introuvable: {path}")

    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs('EPSG:2056')
    gdf = gdf.to_crs('EPSG:4326')

    if 'district' not in gdf.columns:
        raise RuntimeError(
            "Colonne 'district' absente du shapefile. "
            "Lancer scripts/prepare_districts.py d'abord."
        )

    district_name = REGIONS[region_key]['district_name']
    gdf = gdf[gdf['district'] == district_name]
    print(f"District '{district_name}': {len(gdf)} parcelles")
    return gdf


def build_geojson(region_key):
    """Génère le GeoJSON enrichi avec scores AHP pour un district."""
    gdf = load_district(region_key)
    geojson = json.loads(gdf.to_json())

    for feature in geojson['features']:
        scores = compute_scores(feature['properties'])
        score  = compute_ahp_score(scores)
        feature['properties'].update(scores)
        feature['properties']['ahp_score'] = score
        feature['properties']['priority']  = get_priority(score)

    return geojson


# ============================================================
# POINT D'ENTRÉE (utilisé par views.py)
# ============================================================

def get_geojson_for_region(region_key):
    """Retourne le GeoJSON d'un district avec cache en mémoire."""
    if region_key not in _cache:
        _cache[region_key] = build_geojson(region_key)
    return _cache[region_key]
