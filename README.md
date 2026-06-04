# Vigne HES — Aide à la décision d'arrachage

Application web GIS d'aide à la décision pour l'arrachage de vignes en Valais.  
Visualise et classifie les parcelles viticoles selon une analyse multicritère AHP (6 critères).

## Fonctionnalités

- Sélection par district
- Score AHP calculé depuis données réelles (DEM Copernicus, OSM)
- Ajustement interactif de l'importance des critères (sliders)
- Filtre par score minimum
- Statistiques par niveau de priorité (nb parcelles + surface)
- Popup détaillé par parcelle (valeurs réelles + scores individuels)

## Critères d'analyse

| Critère | Source | Logique |
|---------|--------|---------|
| Pente | Copernicus DEM 30m | Raide = difficile à mécaniser |
| Surface | Cadastre viticole Shape | Petite = moins rentable |
| Distance route | OpenStreetMap | Loin = accès difficile |
| Orientation | Copernicus DEM 30m | Nord = moins de soleil |
| Altitude | Copernicus DEM 30m | Haut = conditions difficiles |
| Distance urbaine | OpenStreetMap | Proche ville = pression foncière |

---

## Installation et premier lancement

### 1. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 2. Préparer les données (une seule fois)

Ces deux scripts enrichissent le shapefile de base avec les districts et les critères réels.  
**À lancer dans l'ordre, une seule fois.**

```bash
# Ajoute la colonne 'district' à chaque parcelle (Swisstopo, ~2 min)
python scripts/prepare_districts.py

# Calcule altitude, pente, orientation, distances réelles (DEM + OSM, ~20 min)
python scripts/enrich_criteria.py
```

### 3. Lancer le serveur

```bash
python manage.py runserver
```

Ouvrir [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## Structure du projet

```
├── config/                  Configuration Django
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── vignes/                  Application principale
│   ├── gis_utils.py         Chargement shapefile + calcul AHP
│   ├── views.py             Endpoints API
│   └── urls.py              Routes
├── scripts/                 Scripts de préparation (one-shot)
│   ├── prepare_districts.py Spatial join districts Swisstopo
│   └── enrich_criteria.py   Enrichissement critères (DEM + OSM)
├── static/
│   ├── app.js               Logique frontend (carte, sliders, recalcul)
│   └── style.css
├── templates/
│   └── index.html
├── data/
│   └── cadastre_viticole.shp  Shapefile enrichi (55k parcelles)
└── requirements.txt
```

## API

| Endpoint | Description |
|----------|-------------|
| `GET /` | Page principale |
| `GET /api/parcelles/?region=leuk` | GeoJSON d'un district avec scores AHP |
| `GET /api/regions/` | Liste des districts disponibles |

## Technologies

- **Backend** : Django, GeoPandas, NumPy
- **Données** : Swisstopo swissBOUNDARIES3D, Copernicus GLO-30 DEM, OpenStreetMap
- **Frontend** : Leaflet.js, JavaScript vanilla
