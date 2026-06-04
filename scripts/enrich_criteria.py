"""
Calcule les critères réels pour toutes les parcelles viticoles.

Sources de données:
  Altitude / Pente / Orientation : Copernicus GLO-30 DEM (30m résolution, gratuit)
  Distance route                 : OpenStreetMap (réseau routier réel via osmnx)
  Distance urbaine               : OpenStreetMap (lieux habités via osmnx)
  Surface                        : déjà dans le shapefile, non modifiée

Usage:
    python enrich_criteria.py

Durée estimée: 15-25 minutes (téléchargements + calculs sur 55k parcelles)

Résultat:
    data/cadastre_viticole.shp mis à jour avec les colonnes:
    altitude, pente, orientatio, distance_r, distance_u
"""

import os
import io
import shutil
import requests
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.merge import merge as rasterio_merge
from rasterio.transform import rowcol
from scipy.spatial import cKDTree
from pathlib import Path

DATA_DIR = Path('data')
DEM_DIR  = DATA_DIR / 'dem_tiles'

# ============================================================
# ÉTAPE 1 — TÉLÉCHARGEMENT DU DEM COPERNICUS GLO-30
# Tuiles nécessaires pour couvrir le Valais (lat 45-46, lon 6-8)
# URL: S3 public AWS, sans authentification
# ============================================================

DEM_TILES = [
    (45, 6), (45, 7), (45, 8),
    (46, 6), (46, 7), (46, 8),
]

DEM_URL = (
    "https://copernicus-dem-30m.s3.amazonaws.com/"
    "Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM/"
    "Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM.tif"
)


def download_dem():
    """Télécharge les tuiles DEM Copernicus GLO-30 pour le Valais."""
    print("=" * 60)
    print("ETAPE 1 — Téléchargement DEM Copernicus GLO-30 (30m)")
    print("=" * 60)

    DEM_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = []

    for lat, lon in DEM_TILES:
        url = DEM_URL.format(lat=lat, lon=lon)
        out_path = DEM_DIR / f"N{lat:02d}_E{lon:03d}.tif"

        if out_path.exists():
            print(f"  N{lat:02d}_E{lon:03d}: déjà téléchargée")
            downloaded.append(out_path)
            continue

        print(f"  N{lat:02d}_E{lon:03d}: téléchargement...", end=' ', flush=True)
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            out_path.write_bytes(r.content)
            size_mb = len(r.content) / 1024 / 1024
            print(f"OK ({size_mb:.1f} MB)")
            downloaded.append(out_path)
        except requests.HTTPError:
            print(f"absente (pas de données pour cette tuile)")
        except Exception as e:
            print(f"ERREUR: {e}")

    if not downloaded:
        raise RuntimeError("Aucune tuile DEM téléchargée.")

    print(f"  {len(downloaded)} tuiles disponibles")
    return downloaded


def build_dem(tile_paths):
    """Fusionne les tuiles en un seul DEM GeoTIFF."""
    print("\nFusion des tuiles DEM...")
    merged_path = DATA_DIR / 'valais_dem.tif'

    if merged_path.exists():
        print("  valais_dem.tif déjà existant, réutilisation.")
        return merged_path

    datasets = [rasterio.open(p) for p in tile_paths]
    mosaic, transform = rasterio_merge(datasets)
    meta = datasets[0].meta.copy()
    meta.update({'driver': 'GTiff', 'height': mosaic.shape[1],
                 'width': mosaic.shape[2], 'transform': transform})

    with rasterio.open(merged_path, 'w', **meta) as dst:
        dst.write(mosaic)

    for ds in datasets:
        ds.close()

    print(f"  DEM fusionné: {merged_path}")
    return merged_path


# ============================================================
# ÉTAPE 2 — ALTITUDE, PENTE, ORIENTATION DEPUIS LE DEM
# ============================================================

def compute_terrain_criteria(gdf, dem_path):
    """
    Pour chaque parcelle, calcule:
    - altitude   : élévation au centroïde (mètres)
    - pente      : inclinaison du terrain (degrés, 0=plat, 90=vertical)
    - orientation: exposition (degrés, 0=Nord, 90=Est, 180=Sud, 270=Ouest)

    Méthode: échantillonnage du DEM + gradient numpy (pas de GDAL requis)
    """
    print("\n" + "=" * 60)
    print("ETAPE 2 — Altitude / Pente / Orientation depuis DEM")
    print("=" * 60)

    with rasterio.open(dem_path) as src:
        dem_array = src.read(1).astype(float)
        transform = src.transform
        dem_crs   = src.crs
        nodata    = src.nodata or -9999

        # Remplacer nodata par NaN
        dem_array[dem_array == nodata] = np.nan

        # Taille des pixels en mètres (approximation depuis degrés)
        # 1 degré lat ≈ 111 000m, lon ≈ 111 000m * cos(lat)
        lat_center = 46.2  # Valais
        res_x = abs(transform.a) * 111000 * np.cos(np.radians(lat_center))
        res_y = abs(transform.e) * 111000

        # Calculer pente et orientation sur tout le DEM en une seule fois (rapide)
        print("  Calcul gradient DEM...", flush=True)
        dy, dx = np.gradient(dem_array, res_y, res_x)

        # Pente en degrés
        slope_array = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))

        # Orientation en degrés (convention: 0=Nord, 90=Est, 180=Sud, 270=Ouest)
        # arctan2(-dy, dx) donne l'angle mathématique → conversion vers convention géographique
        aspect_array = (np.degrees(np.arctan2(-dy, dx)) + 360) % 360

        print("  Conversion CRS parcelles...", flush=True)
        # Convertir les parcelles dans le CRS du DEM (WGS84)
        gdf_wgs = gdf.to_crs(dem_crs) if gdf.crs != dem_crs else gdf.copy()
        centroids = gdf_wgs.geometry.centroid

        print(f"  Echantillonnage DEM pour {len(gdf)} parcelles...", flush=True)
        altitudes    = []
        pentes       = []
        orientations = []

        for point in centroids:
            try:
                # Convertir coordonnées géographiques en indices pixel
                row, col = rowcol(transform, point.x, point.y)
                row = int(np.clip(row, 0, dem_array.shape[0] - 1))
                col = int(np.clip(col, 0, dem_array.shape[1] - 1))

                alt   = dem_array[row, col]
                slope = slope_array[row, col]
                asp   = aspect_array[row, col]

                altitudes.append(float(alt) if not np.isnan(alt) else 0.0)
                pentes.append(float(slope) if not np.isnan(slope) else 0.0)
                orientations.append(float(asp) if not np.isnan(asp) else 0.0)
            except Exception:
                altitudes.append(0.0)
                pentes.append(0.0)
                orientations.append(0.0)

    gdf = gdf.copy()
    gdf['altitude']   = altitudes
    gdf['pente']      = pentes
    gdf['orientatio'] = orientations   # tronqué à 10 chars pour shapefile

    print(f"  Altitude   : {np.mean(altitudes):.0f}m moyenne ({np.min(altitudes):.0f}-{np.max(altitudes):.0f}m)")
    print(f"  Pente      : {np.mean(pentes):.1f}° moyenne ({np.min(pentes):.1f}-{np.max(pentes):.1f}°)")
    print(f"  Orientation: {np.mean(orientations):.1f}° moyenne")

    return gdf


# ============================================================
# ÉTAPE 3 — DISTANCE AU RÉSEAU ROUTIER (OSM)
# ============================================================

def compute_road_distances(gdf):
    """
    Télécharge le réseau routier du Valais depuis OpenStreetMap
    et calcule la distance de chaque parcelle à la route la plus proche.
    """
    import osmnx as ox

    print("\n" + "=" * 60)
    print("ETAPE 3 — Distance au réseau routier (OpenStreetMap)")
    print("=" * 60)

    print("  Téléchargement réseau routier Valais (OSM)...", flush=True)

    # Télécharger toutes les routes du Valais
    # network_type='drive' = routes carrossables
    G = ox.graph_from_place('Valais, Switzerland', network_type='drive', simplify=True)

    # Extraire les arêtes (segments de route) comme GeoDataFrame
    edges = ox.graph_to_gdfs(G, nodes=False)
    edges = edges.to_crs('EPSG:2056')  # Aligner avec le cadastre
    print(f"  {len(edges)} segments de route téléchargés")

    # Convertir les arêtes en tableau de points pour KDTree (échantillonnage dense)
    print("  Construction de l'index spatial...", flush=True)
    road_points = []
    for geom in edges.geometry:
        # Interpoler des points tous les ~50m le long de chaque route
        length = geom.length
        n_points = max(2, int(length / 50))
        for i in range(n_points):
            pt = geom.interpolate(i / (n_points - 1), normalized=True)
            road_points.append([pt.x, pt.y])

    road_array = np.array(road_points)
    tree = cKDTree(road_array)

    # Calculer la distance pour chaque parcelle
    print(f"  Calcul distances pour {len(gdf)} parcelles...", flush=True)

    # S'assurer que les parcelles sont en EPSG:2056
    gdf_proj = gdf if gdf.crs.to_epsg() == 2056 else gdf.to_crs('EPSG:2056')
    centroids = gdf_proj.geometry.centroid
    centroid_coords = np.array([[pt.x, pt.y] for pt in centroids])

    distances, _ = tree.query(centroid_coords, workers=-1)

    gdf = gdf.copy()
    gdf['distance_r'] = distances.round(1)   # tronqué à 10 chars pour shapefile

    print(f"  Distance route: {distances.mean():.0f}m moyenne ({distances.min():.0f}-{distances.max():.0f}m)")
    return gdf


# ============================================================
# ÉTAPE 4 — DISTANCE AUX CENTRES URBAINS (OSM)
# ============================================================

def compute_urban_distances(gdf):
    """
    Télécharge les lieux habités du Valais depuis OpenStreetMap
    et calcule la distance de chaque parcelle au lieu habité le plus proche.
    """
    import osmnx as ox

    print("\n" + "=" * 60)
    print("ETAPE 4 — Distance aux centres urbains (OpenStreetMap)")
    print("=" * 60)

    print("  Téléchargement des lieux habités du Valais...", flush=True)

    # Télécharger villes, villages, hameaux du Valais
    places = ox.features_from_place(
        'Valais, Switzerland',
        tags={'place': ['city', 'town', 'village', 'hamlet']}
    )
    places = places[places.geometry.geom_type == 'Point'].to_crs('EPSG:2056')
    print(f"  {len(places)} lieux habités trouvés")

    # KDTree sur les centroïdes des lieux
    place_coords = np.array([[pt.x, pt.y] for pt in places.geometry])
    tree = cKDTree(place_coords)

    # S'assurer que les parcelles sont en EPSG:2056
    gdf_proj = gdf if gdf.crs.to_epsg() == 2056 else gdf.to_crs('EPSG:2056')
    centroids = gdf_proj.geometry.centroid
    centroid_coords = np.array([[pt.x, pt.y] for pt in centroids])

    print(f"  Calcul distances pour {len(gdf)} parcelles...", flush=True)
    distances, _ = tree.query(centroid_coords, workers=-1)

    gdf = gdf.copy()
    gdf['distance_u'] = distances.round(1)   # tronqué à 10 chars pour shapefile

    print(f"  Distance urbaine: {distances.mean():.0f}m moyenne ({distances.min():.0f}-{distances.max():.0f}m)")
    return gdf


# ============================================================
# ÉTAPE 5 — SAUVEGARDE
# ============================================================

def save(gdf):
    output = DATA_DIR / 'cadastre_viticole.shp'

    # Backup si pas encore fait
    backup = DATA_DIR / 'cadastre_viticole_pre_enrich.shp'
    if not backup.exists():
        print("\nBackup shapefile original...")
        for ext in ['.shp', '.dbf', '.prj', '.shx', '.cpg']:
            src = output.with_suffix(ext)
            if src.exists():
                shutil.copy(src, backup.with_suffix(ext))

    print(f"\nSauvegarde -> {output}")
    gdf.to_file(output, index=False)
    print("Fait!")


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Enrichissement des critères AHP avec données réelles")
    print("=" * 60)

    # Chargement du shapefile actuel
    cadastre_path = DATA_DIR / 'cadastre_viticole.shp'
    print(f"\nChargement cadastre: {cadastre_path}")
    gdf = gpd.read_file(cadastre_path)
    if gdf.crs is None:
        gdf = gdf.set_crs('EPSG:2056')
    print(f"{len(gdf)} parcelles chargées (CRS: {gdf.crs.to_epsg()})")

    # 1. DEM
    tile_paths = download_dem()
    dem_path   = build_dem(tile_paths)

    # 2. Terrain: altitude, pente, orientation
    gdf = compute_terrain_criteria(gdf, dem_path)

    # 3. Distance routes
    gdf = compute_road_distances(gdf)

    # 4. Distance urbaine
    gdf = compute_urban_distances(gdf)

    # 5. Sauvegarde
    save(gdf)

    # Nettoyer les tuiles DEM temporaires (garder le DEM fusionné)
    if DEM_DIR.exists():
        shutil.rmtree(DEM_DIR)
        print("Tuiles DEM temporaires supprimées.")

    print("\n" + "=" * 60)
    print("Terminé! Relancer le serveur Django.")
    print("Les critères sont maintenant basés sur des données réelles.")
    print("=" * 60)
