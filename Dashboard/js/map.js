/**
 * js/map.js — Xëtu V6.0
 * Carte Leaflet : tracés de toutes les lignes + markers bus animés
 * sur leur itinéraire réel + overlay arrêts sur filtre.
 *
 * NOUVEAUTÉS V6.0 :
 *   - Affiche tous les tracés au chargement (depuis data/routes_geometry_v13.json)
 *   - Chaque ligne a une couleur unique et cohérente
 *   - Un bus signalé = point animé qui avance doucement sur le tracé réel
 *   - Filtre ligne → mise en valeur du tracé + dimming des autres
 *   - Overlay arrêts amélioré sur filtre ligne
 */

import * as store from './store.js';
import { getAgeColor, getAgeClass, formatAgeShort, formatAge } from './utils.js';
import { LIGNE_NAMES } from './constants.js';
import { loadRoutes } from './api.js';

// ── État ──────────────────────────────────────────────────
let _map         = null;
let _markers     = {};       // { busId: { marker, bus } }
let _onBusSelect = null;

// Overlay ligne filtrée
let _stopMarkers = [];
let _traceLayer  = null;

// Tracés de fond
let _allTraces   = {};       // { ligneId: { polyline, coords[] } }

// Animations bus
let _animations  = {};       // { busId: { rafId, idx, progress, stopped } }

// ── Palette 20 couleurs distinctes ───────────────────────
const LINE_PALETTE = [
  '#FF6B35','#00D67F','#4FC3F7','#FFD166','#EF476F',
  '#06D6A0','#118AB2','#FFB347','#A78BFA','#E76F51',
  '#457B9D','#F4D35E','#3A86FF','#FB5607','#8338EC',
  '#06A77D','#D62246','#4CC9F0','#F77F00','#FCBF49',
];

const _lineColors = {};
let   _colorIdx   = 0;

function _getLineColor(ligneId) {
  if (!_lineColors[ligneId]) {
    _lineColors[ligneId] = LINE_PALETTE[_colorIdx % LINE_PALETTE.length];
    _colorIdx++;
  }
  return _lineColors[ligneId];
}

// ── Fournisseurs de tuiles ────────────────────────────────
const TILE_PROVIDERS = [
  {
    url:  'https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png',
    opts: { attribution: '© Stadia Maps © OpenMapTiles © OpenStreetMap', maxZoom: 20 },
  },
  {
    url:  'https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png',
    opts: { attribution: '© OpenStreetMap France', maxZoom: 20, subdomains: 'abc' },
  },
  {
    url:  'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    opts: { attribution: '© OpenStreetMap contributors', maxZoom: 19 },
  },
];

let _tileLayer = null;

function _loadTileProvider(index) {
  if (index >= TILE_PROVIDERS.length) {
    console.error('[Map] Aucun fournisseur de tuiles disponible.');
    return;
  }
  if (_tileLayer) _map.removeLayer(_tileLayer);
  const p = TILE_PROVIDERS[index];
  _tileLayer = L.tileLayer(p.url, p.opts);
  _tileLayer.on('tileerror', () => {
    console.warn(`[Map] Fournisseur ${index} échoue, essai suivant...`);
    _loadTileProvider(index + 1);
  });
  _tileLayer.addTo(_map);
}

// ── INIT ─────────────────────────────────────────────────

export async function init(containerId, onBusSelect) {
  _onBusSelect = onBusSelect;

  _map = L.map(containerId, {
    center:             [14.716, -17.467],
    zoom:               13,
    zoomControl:        true,
    attributionControl: true,
  });

  _loadTileProvider(0);

  // Dessiner tous les tracés en fond
  await _drawAllTraces();

  // Abonnements store
  store.subscribe('buses', (buses) => {
    const filtered = _applyFilter(buses, store.get('filteredLine'));
    _syncMarkers(filtered, store.get('selectedBus')?.id ?? null);
  });

  store.subscribe('filteredLine', (line) => {
    const filtered = _applyFilter(store.get('buses'), line);
    _syncMarkers(filtered, store.get('selectedBus')?.id ?? null);
    _updateTracesOpacity(line);
  });

  store.subscribe('selectedBus', (bus) => {
    if (bus) flyToBus(bus);
    const filtered = _applyFilter(store.get('buses'), store.get('filteredLine'));
    _syncMarkers(filtered, bus?.id ?? null);
  });
}

// ── TRACÉS DE FOND ────────────────────────────────────────

const BLACKLIST = [
  [13.998777, -16.004102],
  [14.598825, -17.059735],
  [14.619785, -17.047305],
];

function _pointValide(p) {
  for (const [lat, lon] of BLACKLIST) {
    if (Math.abs(p.lat - lat) < 0.0001 && Math.abs(p.lon - lon) < 0.0001) return false;
  }
  return p.lat >= 14.55 && p.lat <= 14.95 && p.lon >= -17.65 && p.lon <= -16.5;
}

async function _drawAllTraces() {
  let routes;
  try {
    routes = await loadRoutes();
  } catch (e) {
    console.warn('[Map] Impossible de charger les tracés :', e.message);
    return;
  }

  if (!routes || Object.keys(routes).length === 0) return;

  for (const [ligneId, route] of Object.entries(routes)) {
    const geometry = (route.geometry || route.trace?.map(p => ({ lat: p[0], lon: p[1] })) || []).filter(_pointValide);
    if (geometry.length < 2) continue;

    const color  = _getLineColor(ligneId);
    const coords = geometry.map(p => [p.lat, p.lon]);

    const polyline = L.polyline(coords, {
      color,
      weight:   3,
      opacity:  0.45,
      lineJoin: 'round',
      lineCap:  'round',
    }).addTo(_map);

    // Clic sur tracé → filtre la ligne
    polyline.on('click', () => {
      store.set('filteredLine', ligneId);
    });

    polyline.bindTooltip(`Ligne ${ligneId}`, {
      sticky:    true,
      className: 'trace-tooltip',
      opacity:   0.9,
    });

    _allTraces[ligneId] = { polyline, coords };
  }

  console.log(`[Map] ${Object.keys(_allTraces).length} tracés affichés`);
}

function _updateTracesOpacity(activeLine) {
  for (const [ligneId, data] of Object.entries(_allTraces)) {
    if (!activeLine) {
      data.polyline.setStyle({ opacity: 0.45, weight: 3 });
    } else if (ligneId === String(activeLine)) {
      data.polyline.setStyle({ opacity: 0.9, weight: 5 });
    } else {
      data.polyline.setStyle({ opacity: 0.10, weight: 2 });
    }
  }
}

// ── MARKERS BUS ───────────────────────────────────────────

function _applyFilter(buses, line) {
  if (!line) return buses;
  return buses.filter(b => String(b.ligne) === String(line));
}

function _syncMarkers(buses, selectedId) {
  const newIds = new Set(buses.map(b => String(b.id)));

  // Supprimer markers absents
  Object.keys(_markers).forEach(id => {
    if (!newIds.has(String(id))) {
      _stopAnimation(id);
      _map.removeLayer(_markers[id].marker);
      delete _markers[id];
    }
  });

  // Créer / mettre à jour
  buses.forEach(bus => {
    if (_markers[bus.id]) {
      _map.removeLayer(_markers[bus.id].marker);
      _stopAnimation(bus.id);
    }
    const isSelected = String(selectedId) === String(bus.id);
    _markers[bus.id] = _createMarker(bus, isSelected);
    _startBusAnimation(bus);
  });
}

function _createMarker(bus, isSelected) {
  const color = _getLineColor(bus.ligne);
  const size  = isSelected ? 44 : 36;

  const icon = L.divIcon({
    className: '',
    html: `
      <div class="bus-marker" style="
        width:${size}px;
        height:${size}px;
        background:${color};
        box-shadow: 0 0 ${isSelected ? 20 : 8}px ${color}99,
                    0 0 ${isSelected ? 40 : 16}px ${color}44;
        font-size:${isSelected ? 12 : 10}px;
        border: 2px solid rgba(255,255,255,0.25);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        color: white;
        cursor: pointer;
        transition: transform 0.15s ease;
        position: relative;
      ">${bus.ligne}</div>
      ${isSelected ? `
      <div style="
        position: absolute;
        top: ${-(size / 2 + 8)}px;
        left: ${-(size / 2 + 8)}px;
        width: ${size + 16}px;
        height: ${size + 16}px;
        border: 2px solid ${color};
        border-radius: 50%;
        animation: markerPulse 1.5s ease-out infinite;
        opacity: 0.6;
        pointer-events: none;
      "></div>` : ''}
    `,
    iconSize:   [size, size],
    iconAnchor: [size / 2, size / 2],
  });

  const marker = L.marker([bus.lat, bus.lng], {
    icon,
    zIndexOffset: isSelected ? 1000 : 0,
  })
  .addTo(_map)
  .bindPopup(_buildPopupHtml(bus), { maxWidth: 260 });

  marker.on('click', () => {
    marker.openPopup();
    if (_onBusSelect) _onBusSelect(bus.id);
  });

  return { marker, bus };
}

// ── ANIMATION SUR TRACÉ ───────────────────────────────────

/**
 * Anime le marker du bus le long du tracé réel de sa ligne.
 * 1. Trouve le point du tracé le plus proche de la position signalée
 * 2. Fait avancer le marker depuis ce point à vitesse constante
 */
function _startBusAnimation(bus) {
  const traceData = _allTraces[bus.ligne] || _allTraces[String(bus.ligne)];
  if (!traceData || traceData.coords.length < 2) return;

  const coords = traceData.coords;

  // Trouver le segment le plus proche de la position du bus
  let closestIdx = 0;
  let minDist    = Infinity;

  for (let i = 0; i < coords.length - 1; i++) {
    const d = _distSq(bus.lat, bus.lng, coords[i][0], coords[i][1]);
    if (d < minDist) { minDist = d; closestIdx = i; }
  }

  const state = {
    idx:      closestIdx,
    progress: 0,
    stopped:  false,
    rafId:    null,
  };

  _animations[bus.id] = state;

  // Vitesse : ~25 km/h en ville → environ 0.003 fraction de segment / seconde
  // Un segment moyen ≈ 50m, donc 0.003 / 50m * 25000m/h = cohérent
  const SPEED_PER_MS = 0.000035;

  let lastTs = null;

  function step(ts) {
    if (state.stopped) return;

    if (!lastTs) lastTs = ts;
    const dt = Math.min(ts - lastTs, 100); // cap 100ms pour éviter les sauts
    lastTs = ts;

    state.progress += SPEED_PER_MS * dt;

    if (state.progress >= 1) {
      state.progress -= 1;
      state.idx++;
      if (state.idx >= coords.length - 1) {
        state.idx = 0; // boucle sur le tracé
      }
    }

    const a = coords[state.idx];
    const b = coords[state.idx + 1];

    if (!a || !b) {
      state.idx = 0;
      state.progress = 0;
      state.rafId = requestAnimationFrame(step);
      return;
    }

    const lat = a[0] + (b[0] - a[0]) * state.progress;
    const lon = a[1] + (b[1] - a[1]) * state.progress;

    const mk = _markers[bus.id]?.marker;
    if (mk) mk.setLatLng([lat, lon]);

    state.rafId = requestAnimationFrame(step);
  }

  state.rafId = requestAnimationFrame(step);
}

function _stopAnimation(busId) {
  const anim = _animations[busId];
  if (!anim) return;
  anim.stopped = true;
  if (anim.rafId) cancelAnimationFrame(anim.rafId);
  delete _animations[busId];
}

function _distSq(lat1, lon1, lat2, lon2) {
  const dlat = lat1 - lat2;
  const dlon = lon1 - lon2;
  return dlat * dlat + dlon * dlon;
}

// ── POPUP ─────────────────────────────────────────────────

function _buildPopupHtml(bus) {
  const ageShort  = formatAgeShort(bus.minutes_ago);
  const ageClass  = getAgeClass(bus.minutes_ago);
  const ageFull   = formatAge(bus.minutes_ago);
  const lineName  = LIGNE_NAMES[bus.ligne] || `Ligne ${bus.ligne}`;
  const lineColor = _getLineColor(bus.ligne);

  return `
    <div class="popup-content">
      <div class="popup-header">
        <span class="popup-ligne" style="color:${lineColor}">Bus ${bus.ligne}</span>
        <span class="popup-name">${lineName}</span>
      </div>
      <div class="popup-pos">📍 ${bus.position}</div>
      <div class="popup-meta">
        <span class="popup-age ${ageClass}" title="${ageFull}">${ageShort}</span>
        <span>· Signalé par ${bus.reporter}</span>
      </div>
      <div class="popup-actions">
        <button class="popup-btn-details" onclick="window._onPopupDetails(${bus.id})">
          Détails ▸
        </button>
        <button class="popup-btn-confirm"
          onclick="window._onPopupConfirm(${bus.id}, this)"
          aria-label="Confirmer la présence du bus ${bus.ligne} à ${bus.position}">
          ✅ Confirmer
        </button>
      </div>
    </div>
  `;
}

// ── OVERLAY LIGNE (filtre actif) ──────────────────────────

/**
 * showLineOverlay : appelé depuis app.js quand un filtre est actif.
 * Affiche les arrêts de la ligne filtrée par-dessus le tracé.
 */
export function showLineOverlay(lineData) {
  clearLineOverlay();
  if (!lineData) return;

  const stops = (lineData.stops || lineData.arrets || []).filter(s => (s.confidence ?? 1) >= 0.5);
  const color  = _getLineColor(lineData.line_id || '');

  // Arrêts
  stops.forEach((stop, idx) => {
    const isTerminus  = idx === 0 || idx === stops.length - 1;
    const radius      = isTerminus ? 8 : 5;
    const fillColor   = isTerminus ? color : '#ffffff';
    const fillOpacity = isTerminus ? 1 : 0.9;

    const circle = L.circleMarker([stop.lat, stop.lon], {
      radius,
      color,
      weight:      isTerminus ? 3 : 2,
      fillColor,
      fillOpacity,
    })
    .addTo(_map)
    .bindTooltip(stop.nom || stop.name, {
      direction:  'top',
      offset:     [0, -radius - 2],
      className:  'stop-tooltip',
      permanent:  false,
      opacity:    0.95,
    });

    _stopMarkers.push(circle);
  });

  // Zoom sur la ligne si des arrêts existent
  if (stops.length > 0) {
    const bounds = L.latLngBounds(stops.map(s => [s.lat, s.lon]));
    _map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
  }
}

export function clearLineOverlay() {
  _stopMarkers.forEach(m => _map.removeLayer(m));
  _stopMarkers = [];

  if (_traceLayer) {
    _map.removeLayer(_traceLayer);
    _traceLayer = null;
  }
}

// ── EXPORTS ───────────────────────────────────────────────

export function flyToBus(bus) {
  _map.flyTo([bus.lat, bus.lng], 15, { duration: 0.8 });
  const entry = _markers[bus.id];
  if (entry) entry.marker.openPopup();
}

export function pulseMarker(busId) {
  const entry = _markers[busId];
  if (!entry) return;
  const el = entry.marker.getElement()?.querySelector('.bus-marker');
  if (el) {
    el.classList.remove('pulse');
    void el.offsetWidth;
    el.classList.add('pulse');
    setTimeout(() => el.classList.remove('pulse'), 3000);
  }
}

export function getMap() { return _map; }
