/**
 * Cadastre Viticole Valais — Application principale
 *
 * Flux:
 *  1. Chargement des régions → dropdown
 *  2. Chargement des poids AHP → sliders
 *  3. Sélection région → fetch GeoJSON → affichage carte + stats
 *  4. Slider poids → recalcul score côté client (sans re-requête)
 *  5. Slider seuil → filtre visuel sur la carte
 */


// ============================================================
// CONFIGURATION
// ============================================================

// Couleurs par niveau de priorité (identiques côté serveur et client)
const PRIORITY_COLORS = {
    'Haute':      '#d73027',  // rouge  > 75%
    'Moyenne':    '#fc8d59',  // orange 50-75%
    'Basse':      '#fee08b',  // jaune  25-50%
    'Très Basse': '#1a9850',  // vert   < 25%
};

// Correspondance critère → score individuel dans les propriétés GeoJSON
const SCORE_FIELD = {
    'pente':           'score_pente',
    'surface':         'score_surface',
    'distance_route':  'score_distance_route',
    'orientation':     'score_orientation',
    'altitude':        'score_altitude',
    'distance_urbain': 'score_distance_urbain',
};

// Correspondance niveau de priorité → ID des éléments HTML de stats
const PRIORITY_IDS = {
    'Haute':      'haute',
    'Moyenne':    'moyenne',
    'Basse':      'basse',
    'Très Basse': 'tres-basse',
};


// ============================================================
// ÉTAT DE L'APPLICATION
// ============================================================

let currentWeights = {};       // poids AHP normalisés actuels
let currentGeojson = null;     // données GeoJSON en mémoire
let parcellesLayer = null;     // couche Leaflet des parcelles


// ============================================================
// INITIALISATION DE LA CARTE LEAFLET
// ============================================================

const map = L.map('map').setView([46.23, 7.37], 12);

// Fond de carte
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19,
}).addTo(map);

// Légende (coin supérieur droit)
const legend = L.control({ position: 'topright' });
legend.onAdd = function () {
    const div = L.DomUtil.create('div', 'legend');
    div.innerHTML = `
        <h4>Priorité d'arrachage</h4>
        <div class="legend-item"><span style="background:#d73027"></span>Haute (&gt;75%)</div>
        <div class="legend-item"><span style="background:#fc8d59"></span>Moyenne (50–75%)</div>
        <div class="legend-item"><span style="background:#fee08b"></span>Basse (25–50%)</div>
        <div class="legend-item"><span style="background:#1a9850"></span>Très Basse (&lt;25%)</div>
        <hr>
        <p class="legend-method">Méthode: AHP 6 critères</p>
    `;
    return div;
};
legend.addTo(map);


// ============================================================
// INITIALISATION AU CHARGEMENT DE LA PAGE
// ============================================================

document.addEventListener('DOMContentLoaded', async () => {
    // Charger régions + poids AHP en parallèle
    await Promise.all([
        loadRegions(),
        loadAHPWeights(),
    ]);

    // Charger la région sélectionnée par défaut (première du dropdown)
    const region = document.getElementById('region-select').value;
    if (region) loadParcelles(region);
});


// ============================================================
// GESTION DES RÉGIONS
// ============================================================

async function loadRegions() {
    const response = await fetch('/api/regions/');
    const data = await response.json();

    const select = document.getElementById('region-select');
    data.regions.forEach(region => {
        const opt = document.createElement('option');
        opt.value = region.key;
        opt.textContent = region.nom;
        select.appendChild(opt);
    });
}

// Appelé par le <select onchange>
function onRegionChange() {
    const region = document.getElementById('region-select').value;
    loadParcelles(region);
}


// ============================================================
// CHARGEMENT DES PARCELLES (requête serveur)
// ============================================================

async function loadParcelles(regionKey) {
    showLoading(true);

    // Supprimer la couche précédente
    if (parcellesLayer) {
        map.removeLayer(parcellesLayer);
        parcellesLayer = null;
    }

    try {
        const response = await fetch(`/api/parcelles/?region=${regionKey}`);

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || response.statusText);
        }

        const data = await response.json();

        if (!data.features || data.features.length === 0) {
            alert('Aucune parcelle trouvée pour cette région.');
            return;
        }

        // Stocker en mémoire pour recalcul côté client (sliders poids)
        currentGeojson = data;

        // Afficher sur la carte et centrer dessus
        renderParcelles(currentGeojson, true);

    } catch (error) {
        alert('Erreur: ' + error.message);
    } finally {
        showLoading(false);
    }
}


// ============================================================
// AFFICHAGE DES PARCELLES SUR LA CARTE
// ============================================================

/**
 * Crée la couche Leaflet GeoJSON et l'ajoute à la carte.
 * @param {Object} geojsonData - FeatureCollection GeoJSON
 * @param {boolean} fitBounds  - si true, centrer la carte sur les parcelles
 */
function renderParcelles(geojsonData, fitBounds = false) {
    const threshold = getThreshold();

    parcellesLayer = L.geoJSON(geojsonData, {
        style: (feature) => {
            const score    = feature.properties.ahp_score || 0;
            const priority = feature.properties.priority || 'Basse';
            return {
                color:       '#555',
                weight:      1,
                opacity:     0.8,
                fillColor:   PRIORITY_COLORS[priority] || '#fee08b',
                fillOpacity: score >= threshold ? 0.75 : 0.08,  // griser les parcelles sous le seuil
            };
        },
        onEachFeature: (feature, layer) => {
            // Popup construit à la demande (lazy) pour meilleures performances
            layer.bindPopup(() => buildPopup(feature.properties));
        },
    }).addTo(map);

    if (fitBounds && parcellesLayer.getBounds().isValid()) {
        map.fitBounds(parcellesLayer.getBounds(), { padding: [30, 30] });
    }

    updateStats(geojsonData.features, threshold);
}


// ============================================================
// POPUP DE DÉTAIL D'UNE PARCELLE
// ============================================================

function buildPopup(props) {
    const score  = ((props.ahp_score || 0) * 100).toFixed(1);
    const area   = props.surface ? (props.surface / 10000).toFixed(2) : 'N/A';
    const color  = priorityColor(props.priority);

    // Valeurs brutes réelles (noms tronqués shapefile)
    const altitude    = props.altitude   ? Math.round(props.altitude)                  : 'N/A';
    const pente       = props.pente      ? Number(props.pente).toFixed(1)              : 'N/A';
    const orientation = props.orientatio ? Math.round(props.orientatio) + '°'          : 'N/A';
    const distRoute   = props.distance_r ? Math.round(props.distance_r) + ' m'         : 'N/A';
    const distUrbain  = props.distance_u ? Math.round(props.distance_u) + ' m'         : 'N/A';

    // Convertir orientation en point cardinal lisible
    function toCardinal(deg) {
        const dirs = ['N','NE','E','SE','S','SO','O','NO'];
        return dirs[Math.round(deg / 45) % 8];
    }
    const cardinal = props.orientatio ? ` (${toCardinal(props.orientatio)})` : '';

    // Tableau critères: valeur réelle + score normalisé + barre colorée par score individuel
    const criteriaRows = [
        { label: 'Pente',            valeur: `${pente}°`,                scoreKey: 'score_pente',           desc: 'Raide = difficile à mécaniser' },
        { label: 'Surface',          valeur: `${area} ha`,               scoreKey: 'score_surface',          desc: 'Petite = moins rentable' },
        { label: 'Distance route',   valeur: distRoute,                  scoreKey: 'score_distance_route',   desc: 'Loin = accès difficile' },
        { label: 'Orientation',      valeur: `${orientation}${cardinal}`, scoreKey: 'score_orientation',     desc: 'Nord = moins de soleil' },
        { label: 'Altitude',         valeur: `${altitude} m`,            scoreKey: 'score_altitude',         desc: 'Haut = conditions difficiles' },
        { label: 'Dist. urbaine',    valeur: distUrbain,                 scoreKey: 'score_distance_urbain',  desc: 'Proche ville = pression foncière' },
    ].map(({ label, valeur, scoreKey, desc }) => {
        const s        = (props[scoreKey] || 0);
        const pct      = (s * 100).toFixed(0);
        const barColor = priorityColor(s > 0.75 ? 'Haute' : s > 0.50 ? 'Moyenne' : s > 0.25 ? 'Basse' : 'Très Basse');
        const bar = `<div style="background:#e0e0e0;border-radius:3px;height:6px;margin-top:3px;">
                       <div style="background:${barColor};width:${pct}%;height:6px;border-radius:3px;"></div>
                     </div>`;
        return `
            <tr>
                <td style="padding:5px 6px 2px;color:#555;font-size:12px;">
                    <b>${label}</b><br>
                    <span style="color:#888;font-size:11px;">${desc}</span>
                </td>
                <td style="padding:5px 6px 2px;text-align:right;white-space:nowrap;font-size:12px;">
                    <span style="color:#333;">${valeur}</span><br>
                    <span style="color:${barColor};font-weight:bold;">${pct}%</span>
                    ${bar}
                </td>
            </tr>`;
    }).join('');

    return `
        <div class="popup-content">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <h4 style="margin:0;">Parcelle #${props.t_id || 'N/A'}</h4>
                <span style="background:${color};color:white;padding:3px 8px;border-radius:12px;font-size:12px;font-weight:bold;">
                    ${props.priority || 'N/A'}
                </span>
            </div>

            <!-- Score AHP global bien visible -->
            <div style="background:#f5f5f5;border-radius:6px;padding:10px;margin-bottom:10px;text-align:center;">
                <div style="font-size:11px;color:#888;margin-bottom:4px;">SCORE AHP</div>
                <div style="font-size:26px;font-weight:bold;color:${color};">${score}%</div>
                <div style="background:#e0e0e0;border-radius:4px;height:8px;margin-top:6px;">
                    <div style="background:${color};width:${score}%;height:8px;border-radius:4px;"></div>
                </div>
            </div>

            <!-- Détail des 6 critères -->
            <table style="width:100%;border-collapse:collapse;">
                ${criteriaRows}
            </table>

            <div style="margin-top:8px;font-size:11px;color:#aaa;text-align:right;">
                District: ${props.district || 'N/A'} · Surface: ${area} ha
            </div>
        </div>
    `;
}

function priorityColor(priority) {
    return PRIORITY_COLORS[priority] || '#999';
}


// ============================================================
// POIDS AHP — SLIDERS + RECALCUL CÔTÉ CLIENT
// ============================================================

// 5 niveaux d'importance: position slider (0-4) → valeur numérique pour la normalisation
const LEVEL_VALUES = [0, 1, 3, 6, 10];  // 0=Pas important, 4=Critique
const LEVEL_NAMES  = ['Pas important', 'Faible', 'Moyen', 'Important', 'Critique'];
const LEVEL_COLORS = ['#aaa', '#5b8dd9', '#e6a817', '#e07b39', '#d73027'];

// Positions par défaut dérivées de la matrice AHP
// (pente=le plus critique, surface=le moins important)
const DEFAULT_POSITIONS = {
    pente:           4,  // Critique
    distance_route:  3,  // Important
    altitude:        3,  // Important
    distance_urbain: 2,  // Moyen
    orientation:     2,  // Moyen
    surface:         1,  // Faible
};

async function loadAHPWeights() {
    // Initialiser les sliders avec les positions par défaut
    for (const [criterion, position] of Object.entries(DEFAULT_POSITIONS)) {
        const slider = document.getElementById(`w-${criterion}`);
        if (slider) slider.value = position;
        updateLevelBadge(criterion, position);
    }

    // Calculer les poids initiaux depuis les positions par défaut
    computeWeightsFromSliders();

    // /api/ahp/ non utilisé côté UI, appel supprimé
}

// Appelé à chaque mouvement de slider
function onWeightChange() {
    computeWeightsFromSliders();
    if (currentGeojson) recalculateScores();
}

function computeWeightsFromSliders() {
    // Lire les positions (0-4) et convertir en valeurs numériques
    let total = 0;
    const values = {};

    for (const criterion of Object.keys(SCORE_FIELD)) {
        const pos = parseInt(document.getElementById(`w-${criterion}`).value) || 0;
        values[criterion] = LEVEL_VALUES[pos];
        total += LEVEL_VALUES[pos];
        updateLevelBadge(criterion, pos);
    }

    // Si tout est à 0 (Pas important), garder des poids égaux
    if (total === 0) {
        const equal = 1 / Object.keys(SCORE_FIELD).length;
        for (const c of Object.keys(SCORE_FIELD)) currentWeights[c] = equal;
        return;
    }

    // Normaliser: poids = valeur / somme → somme des poids = 1
    for (const criterion of Object.keys(SCORE_FIELD)) {
        currentWeights[criterion] = values[criterion] / total;
    }
}

// Met à jour le badge de niveau (texte + couleur) sous le slider
function updateLevelBadge(criterion, position) {
    const el = document.getElementById(`level-${criterion}`);
    if (!el) return;
    el.textContent = LEVEL_NAMES[position];
    el.style.background = LEVEL_COLORS[position];
}

/**
 * Recalcule le score AHP de chaque feature avec les poids courants.
 * Utilise les scores individuels déjà présents dans les propriétés GeoJSON.
 * Aucun appel serveur nécessaire.
 */
function recalculateScores() {
    currentGeojson.features.forEach(feature => {
        const props = feature.properties;

        // Nouveau score = somme pondérée des 6 scores individuels
        let newScore = 0;
        for (const [criterion, weight] of Object.entries(currentWeights)) {
            newScore += weight * (props[SCORE_FIELD[criterion]] || 0);
        }
        props.ahp_score = Math.min(1, Math.max(0, newScore));

        // Mettre à jour le niveau de priorité
        if (props.ahp_score > 0.75)      props.priority = 'Haute';
        else if (props.ahp_score > 0.50) props.priority = 'Moyenne';
        else if (props.ahp_score > 0.25) props.priority = 'Basse';
        else                              props.priority = 'Très Basse';
    });

    // Ré-afficher sans recenter (fitBounds = false)
    if (parcellesLayer) map.removeLayer(parcellesLayer);
    renderParcelles(currentGeojson, false);
}


// ============================================================
// FILTRE PAR SCORE MINIMUM
// ============================================================

function getThreshold() {
    const slider = document.getElementById('score-threshold');
    return slider ? parseInt(slider.value) / 100 : 0;
}

// Appelé à chaque mouvement du slider de seuil
function onThresholdChange() {
    const value = getThreshold();
    const label = document.getElementById('threshold-label');
    if (label) label.textContent = `${Math.round(value * 100)}%`;

    if (currentGeojson) {
        if (parcellesLayer) map.removeLayer(parcellesLayer);
        renderParcelles(currentGeojson, false);
    }
}


// ============================================================
// STATISTIQUES
// ============================================================

/**
 * Met à jour le panneau de statistiques avec les données courantes.
 * @param {Array} features   - tableau de features GeoJSON
 * @param {number} threshold - seuil de score minimum actif
 */
function updateStats(features, threshold) {
    const counts  = { 'Haute': 0, 'Moyenne': 0, 'Basse': 0, 'Très Basse': 0 };
    const areas   = { 'Haute': 0, 'Moyenne': 0, 'Basse': 0, 'Très Basse': 0 };
    let aboveThreshold = 0;

    features.forEach(f => {
        const priority = f.properties.priority || 'Basse';
        const score    = f.properties.ahp_score || 0;
        const areaha   = (f.properties.surface || 0) / 10000;  // m² → ha

        counts[priority]++;
        areas[priority] += areaha;
        if (score >= threshold) aboveThreshold++;
    });

    // Total et parcelles visibles (au-dessus du seuil)
    document.getElementById('stat-total').textContent   = features.length;
    document.getElementById('stat-visible').textContent = aboveThreshold;

    // Stats par priorité
    for (const [priority, id] of Object.entries(PRIORITY_IDS)) {
        const countEl = document.getElementById(`stat-${id}`);
        const areaEl  = document.getElementById(`area-${id}`);
        if (countEl) countEl.textContent = counts[priority];
        if (areaEl)  areaEl.textContent  = areas[priority].toFixed(1) + ' ha';
    }
}


// ============================================================
// UTILITAIRES UI
// ============================================================

function showLoading(show) {
    document.getElementById('loading').style.display = show ? 'flex' : 'none';
}

function togglePanel() {
    const panel = document.getElementById('left-panel');
    const btn   = document.getElementById('open-panel-btn');
    panel.classList.toggle('collapsed');
    // Afficher le bouton "ouvrir" seulement quand le panneau est fermé
    btn.style.display = panel.classList.contains('collapsed') ? 'block' : 'none';
}
