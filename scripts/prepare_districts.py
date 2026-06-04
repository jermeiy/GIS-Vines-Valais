"""
Enrichit le cadastre viticole avec la colonne 'district'.

Ce script est à exécuter UNE SEULE FOIS avant de lancer le serveur.
Il télécharge les limites officielles des districts depuis Swisstopo
et les associe à chaque parcelle par un spatial join.

Usage:
    python prepare_districts.py

Résultat:
    data/cadastre_viticole.shp est mis à jour avec une colonne 'district'
    contenant le nom du district pour chaque parcelle.
"""

import geopandas as gpd
import requests
import zipfile
import io
import sys
import shutil
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

DATA_DIR = Path('data')

# API STAC Swisstopo — récupère automatiquement l'URL de la dernière version
STAC_API_URL = "https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.swissboundaries3d/items"

# Numéro de canton du Valais dans les données Swisstopo
VALAIS_KANTONSNR = 23

# ============================================================
# ÉTAPE 1 — Téléchargement des limites de districts
# ============================================================

def get_download_url():
    """Récupère l'URL de la dernière version de swissBOUNDARIES3D via l'API STAC."""
    response = requests.get(STAC_API_URL, timeout=30)
    response.raise_for_status()
    items = response.json().get('features', [])
    if not items:
        raise ValueError("Aucun item trouvé dans l'API STAC Swisstopo.")
    # Dernier item = version la plus récente
    latest = items[-1]
    assets = latest.get('assets', {})
    # Chercher le ZIP shapefile EPSG:2056
    for key, asset in assets.items():
        href = asset.get('href', '')
        if '2056' in href and href.endswith('.shp.zip'):
            return href
    raise ValueError(f"URL shapefile non trouvée dans les assets: {list(assets.keys())}")


def download_districts():
    """Télécharge et extrait le shapefile des districts suisses."""
    print("1. Téléchargement des limites de districts (Swisstopo)...")

    try:
        url = get_download_url()
        print(f"   URL: {url}")
        response = requests.get(url, timeout=120)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"\nErreur téléchargement: {e}")
        print("Vérifier la connexion internet et relancer le script.")
        sys.exit(1)

    print(f"   Archive téléchargée ({len(response.content) / 1024 / 1024:.1f} MB)")

    # Extraire dans un dossier temporaire
    extract_dir = DATA_DIR / 'districts_tmp'
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        zf.extractall(extract_dir)

    # Trouver le fichier .shp extrait
    shp_files = list(extract_dir.rglob('*.shp'))
    if not shp_files:
        print("Erreur: aucun fichier .shp trouvé dans l'archive.")
        sys.exit(1)

    print(f"   Extrait: {shp_files[0].name}")
    return shp_files[0]


# ============================================================
# ÉTAPE 2 — Filtrage des districts du Valais
# ============================================================

def load_valais_districts(shp_path):
    """Charge le shapefile et ne garde que les districts du Valais."""
    print("\n2. Filtrage des districts du Valais...")

    gdf = gpd.read_file(shp_path)
    print(f"   Colonnes disponibles: {gdf.columns.tolist()}")

    # Identifier la colonne canton (KANTONSNUM ou similaire)
    canton_col = None
    for col in ['KANTONSNUM', 'KT_NR', 'KANTONSNR', 'kantonsnr']:
        if col in gdf.columns:
            canton_col = col
            break

    if canton_col is None:
        print("   Colonnes trouvées:", gdf.columns.tolist())
        print("Erreur: colonne canton non trouvée. Vérifier les colonnes ci-dessus.")
        sys.exit(1)

    valais = gdf[gdf[canton_col] == VALAIS_KANTONSNR].copy()

    # Identifier la colonne nom du district
    name_col = None
    for col in ['NAME', 'BEZNAME', 'name', 'Name']:
        if col in gdf.columns:
            name_col = col
            break

    if name_col is None:
        print("Erreur: colonne nom du district non trouvée.")
        sys.exit(1)

    print(f"\n   Districts du Valais trouvés ({len(valais)}):")
    for _, row in valais.sort_values(name_col).iterrows():
        print(f"     - '{row[name_col]}'")

    # Renommer pour uniformité
    valais = valais.rename(columns={name_col: 'district'})

    return valais[['district', 'geometry']]


# ============================================================
# ÉTAPE 3 — Spatial join: parcelles ← district
# ============================================================

def add_district_column(districts_gdf):
    """Joint les districts aux parcelles viticoles par position géographique."""
    print("\n3. Chargement du cadastre viticole...")

    cadastre_path = DATA_DIR / 'cadastre_viticole.shp'
    if not cadastre_path.exists():
        print(f"Erreur: {cadastre_path} introuvable.")
        sys.exit(1)

    cadastre = gpd.read_file(cadastre_path)
    print(f"   {len(cadastre)} parcelles chargées (CRS: {cadastre.crs})")

    # Aligner les CRS
    if districts_gdf.crs != cadastre.crs:
        print(f"   Conversion CRS: {districts_gdf.crs} -> {cadastre.crs}")
        districts_gdf = districts_gdf.to_crs(cadastre.crs)

    print(f"\n4. Spatial join en cours...")
    print(f"   Cela peut prendre 1-2 minutes pour {len(cadastre)} parcelles...")

    # Chaque parcelle reçoit le nom du district qui la contient
    joined = gpd.sjoin(
        cadastre,
        districts_gdf,
        how='left',
        predicate='within'
    )

    # Nettoyage des colonnes ajoutées par le join
    joined = joined.drop(columns=['index_right'], errors='ignore')

    # Statistiques
    print(f"\n   Résultat par district:")
    counts = joined['district'].value_counts()
    for district, count in counts.items():
        print(f"     {district}: {count} parcelles")

    n_sans_district = joined['district'].isna().sum()
    if n_sans_district > 0:
        print(f"\n   Attention: {n_sans_district} parcelles sans district (sur les limites)")

    return joined


# ============================================================
# ÉTAPE 4 — Sauvegarde
# ============================================================

def save_result(gdf):
    """Sauvegarde le shapefile enrichi."""
    output_path = DATA_DIR / 'cadastre_viticole.shp'

    # Backup de l'original si pas encore fait
    backup_path = DATA_DIR / 'cadastre_viticole_original.shp'
    if not backup_path.exists():
        print(f"\n5. Backup de l'original -> {backup_path.name}")
        for ext in ['.shp', '.dbf', '.prj', '.shx', '.cpg']:
            src = output_path.with_suffix(ext)
            if src.exists():
                shutil.copy(src, backup_path.with_suffix(ext))

    print(f"\n5. Sauvegarde -> {output_path}")
    gdf.to_file(output_path, index=False)
    print("   Fait!")


# ============================================================
# NETTOYAGE
# ============================================================

def cleanup():
    """Supprime le dossier temporaire."""
    tmp_dir = DATA_DIR / 'districts_tmp'
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
        print("   Dossier temporaire supprimé.")


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Préparation des districts viticoles du Valais")
    print("=" * 60)

    shp_path = download_districts()
    districts = load_valais_districts(shp_path)
    cadastre_enrichi = add_district_column(districts)
    save_result(cadastre_enrichi)
    cleanup()

    print("\n" + "=" * 60)
    print("Terminé! Relancer le serveur Django.")
    print("Les districts sont maintenant disponibles dans le dropdown.")
    print("=" * 60)
