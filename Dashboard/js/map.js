/**
 * js/map.js — Xëtu V6.1
 * Carte Leaflet : tracés de toutes les lignes + markers bus animés
 * sur leur itinéraire réel + overlay arrêts sur filtre.
 *
 * NOUVEAUTÉS V6.1 :
 *   - _drawGtfsTestLines() : L1 + L4 tracées en gras au chargement
 *     avec tous leurs arrêts affichés en permanence (données GTFS embarquées).
 *     Tooltip hover = nom arrêt + coordonnées GPS exactes.
 *     Résiste à clearLineOverlay() — couche dédiée _gtfsStopMarkers[].
 *
 * V6.0 :
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

// Overlay ligne filtrée (effacé par clearLineOverlay)
let _stopMarkers = [];
let _traceLayer  = null;

// Couche GTFS test — séparée, jamais effacée par clearLineOverlay
let _gtfsStopMarkers = [];

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

  // Lignes de test GTFS (L1 + L4) — arrêts permanents avec coords
  _drawGtfsTestLines();

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

// ── LIGNES GTFS TEST (L1 + L4) — arrêts permanents ───────
// Données GTFS embarquées directement : confidence=1.0, coords vérifiées.
// Couche séparée (_gtfsStopMarkers) — résiste à clearLineOverlay().
// Tooltip hover/tap : nom arrêt + coordonnées GPS exactes.

const _GTFS_DATA = {
  '1': {
    color: '#00D67F',
    label: 'L1 — Parcelles Assainies → Leclerc',
    trace: [[14.760337,-17.438687],[14.763941,-17.441183],[14.762826,-17.446516],[14.759832,-17.448105],[14.758248,-17.447765],[14.7543,-17.446884],[14.750523,-17.44654],[14.75005,-17.447991],[14.750294,-17.449628],[14.750618,-17.451216],[14.751909,-17.454321],[14.751324,-17.456147],[14.750278,-17.457885],[14.746395,-17.466589],[14.744906,-17.468876],[14.740498,-17.471506],[14.735673,-17.473248],[14.729656,-17.472863],[14.725906,-17.471813],[14.722566,-17.471226],[14.719751,-17.471389],[14.712285,-17.471903],[14.70925,-17.471285],[14.705035,-17.470294],[14.700212,-17.46885],[14.695885,-17.465384],[14.693566,-17.46262],[14.691574,-17.460204],[14.689322,-17.457816],[14.686677,-17.455513],[14.68354,-17.452374],[14.681512,-17.450239],[14.67856,-17.447046],[14.675097,-17.443519],[14.670725,-17.440327],[14.669174,-17.43795],[14.669499,-17.432616],[14.669905,-17.431704],[14.674246,-17.432611],[14.673962,-17.431671],[14.671893,-17.427341],[14.672123,-17.427338]],
    arrets: [{"nom":"Terminus Parcelles Assainies","lat":14.764233,"lon":-17.440017},{"nom":"Sapeur Pompier des Parcelles Assainies","lat":14.76275,"lon":-17.44095},{"nom":"Unite 9","lat":14.7626,"lon":-17.446467},{"nom":"Hlm Grand medine","lat":14.75985,"lon":-17.448017},{"nom":"Ecole Dior","lat":14.758267,"lon":-17.447683},{"nom":"Acapes","lat":14.756333,"lon":-17.447317},{"nom":"Unite 24","lat":14.7543,"lon":-17.446883},{"nom":"Boulangerie Mandela 3","lat":14.750483,"lon":-17.446283},{"nom":"Marche Grand Medine Bv","lat":14.7501,"lon":-17.447983},{"nom":"Telecentre Niuma","lat":14.750367,"lon":-17.449617},{"nom":"Parking Stade L.S.S Bv","lat":14.750617,"lon":-17.451217},{"nom":"Boulangerie Dedi","lat":14.751917,"lon":-17.454317},{"nom":"Cite Keur Damel Bv","lat":14.7514,"lon":-17.4562},{"nom":"Mosquee Nord Foire Bv","lat":14.7502,"lon":-17.45785},{"nom":"Foire de Dakar Bv","lat":14.746417,"lon":-17.4666},{"nom":"Cfpt Bv","lat":14.744933,"lon":-17.4689},{"nom":"Sipres Bv","lat":14.740533,"lon":-17.4716},{"nom":"Sapco sur la VDN Bv","lat":14.735683,"lon":-17.473283},{"nom":"Cimetiere Saint Lazarre","lat":14.72965,"lon":-17.472883},{"nom":"Sacree Coeur 3 extension","lat":14.7259,"lon":-17.471833},{"nom":"Novomed Sacree Coeur 3","lat":14.722567,"lon":-17.471183},{"nom":"Avant Case des tout petits sur la Vdn","lat":14.71975,"lon":-17.471383},{"nom":"Bimao sur la VDN Bv","lat":14.712283,"lon":-17.471917},{"nom":"Africatel sur la Vdn","lat":14.70925,"lon":-17.471283},{"nom":"Cite Mermoz sur la Vdn","lat":14.705033,"lon":-17.4703},{"nom":"Station Mobile Vdn","lat":14.7002,"lon":-17.468883},{"nom":"Hopitale Fann Bv","lat":14.695867,"lon":-17.4654},{"nom":"Universite Cheikh A Diop","lat":14.69355,"lon":-17.462633},{"nom":"Cesti Bv","lat":14.691517,"lon":-17.46025},{"nom":"Ecole Manguiers Bv","lat":14.689333,"lon":-17.4578},{"nom":"Police Medina","lat":14.686617,"lon":-17.455567},{"nom":"Rue 31 x Blaise Diagne","lat":14.68345,"lon":-17.452467},{"nom":"Marche Tillene Bv","lat":14.6815,"lon":-17.45025},{"nom":"Rue 11 x Blaise Diagne Bv","lat":14.679667,"lon":-17.448317},{"nom":"Stade Iba Mar Diop","lat":14.678483,"lon":-17.447117},{"nom":"Credit Foncier Bv","lat":14.675067,"lon":-17.44355},{"nom":"El Malick Sandaga","lat":14.670667,"lon":-17.440483},{"nom":"Peytavin Sandaga","lat":14.6689,"lon":-17.437933},{"nom":"Avenue Ponty (Plaza)","lat":14.669384,"lon":-17.434782},{"nom":"Cbao (Avenue Ponty)","lat":14.669487,"lon":-17.432615},{"nom":"Place de l'independance","lat":14.669908,"lon":-17.43165},{"nom":"Esso Port","lat":14.674233,"lon":-17.432633},{"nom":"Embarcadere","lat":14.674117,"lon":-17.43155},{"nom":"Mole 1 (Port de dakar)","lat":14.671833,"lon":-17.42735},{"nom":"Terminus Leclerc","lat":14.672133,"lon":-17.4273}],
  },
  '4': {
    color: '#4FC3F7',
    label: 'L4 — Liberté 5 → Leclerc',
    trace: [[14.72318,-17.458638],[14.724542,-17.457012],[14.727674,-17.45657],[14.727036,-17.452502],[14.721926,-17.453323],[14.719571,-17.453681],[14.717644,-17.458175],[14.715337,-17.460237],[14.71113,-17.463928],[14.70779,-17.466325],[14.705231,-17.464304],[14.703899,-17.463073],[14.699115,-17.456685],[14.698255,-17.456924],[14.695569,-17.455836],[14.693524,-17.453754],[14.692787,-17.452037],[14.690763,-17.450324],[14.685879,-17.452937],[14.683389,-17.452521],[14.68139,-17.450353],[14.678418,-17.447178],[14.675015,-17.443599],[14.670718,-17.440353],[14.668673,-17.439616],[14.665476,-17.436642],[14.6699,-17.431776],[14.673065,-17.430706],[14.672177,-17.42735]],
    arrets: [{"nom":"Terminus Dieuppeul","lat":14.723283,"lon":-17.459117},{"nom":"Cite Derkle","lat":14.72455,"lon":-17.457067},{"nom":"Ecole Derkle Bv","lat":14.727667,"lon":-17.456517},{"nom":"Pharmacie Derkle","lat":14.727033,"lon":-17.452483},{"nom":"Cite Marine Bv","lat":14.724367,"lon":-17.452917},{"nom":"1er Arret Dieuppeul","lat":14.721917,"lon":-17.453267},{"nom":"2eme Arret Dieuppeul","lat":14.719567,"lon":-17.45365},{"nom":"Sapeur Pompier","lat":14.717667,"lon":-17.4582},{"nom":"Sacre Coeur 1 Bv","lat":14.715233,"lon":-17.460117},{"nom":"College Sacre coeur","lat":14.71355,"lon":-17.461767},{"nom":"Paroisse Sacre Coeur","lat":14.71115,"lon":-17.46395},{"nom":"SOS Village","lat":14.707783,"lon":-17.466333},{"nom":"Karack Mosquee","lat":14.70525,"lon":-17.464283},{"nom":"1er Arret Thierno S N Tall","lat":14.702517,"lon":-17.461733},{"nom":"2eme Arret Thierno S N Tall","lat":14.699983,"lon":-17.459567},{"nom":"3eme Arret Thierno S N Tall","lat":14.69845,"lon":-17.458117},{"nom":"4eme Arret Thierno S N Tall","lat":14.695583,"lon":-17.455817},{"nom":"Immeuble Seydi Jamil Hlm Fass","lat":14.693533,"lon":-17.45375},{"nom":"Marche Fass","lat":14.692833,"lon":-17.452017},{"nom":"Direction des Hlms","lat":14.69075,"lon":-17.4503},{"nom":"Travaux Communaux Fass Bv","lat":14.688567,"lon":-17.451433},{"nom":"Supermache Sham","lat":14.68585,"lon":-17.452883},{"nom":"Rue 31 x Blaise Diagne","lat":14.68345,"lon":-17.452467},{"nom":"Marche Tillene Bv","lat":14.6815,"lon":-17.45025},{"nom":"Rue 11 x Blaise Diagne Bv","lat":14.679667,"lon":-17.448317},{"nom":"Stade Iba Mar Diop","lat":14.678483,"lon":-17.447117},{"nom":"Credit Foncier Bv","lat":14.675067,"lon":-17.44355},{"nom":"El Malick Sandaga","lat":14.670667,"lon":-17.440483},{"nom":"Direction Asecna","lat":14.668667,"lon":-17.439633},{"nom":"Cathedrale","lat":14.66545,"lon":-17.43665},{"nom":"Place de l'independance","lat":14.669908,"lon":-17.43165},{"nom":"Police Municipale","lat":14.672983,"lon":-17.430767},{"nom":"Terminus Leclerc","lat":14.672133,"lon":-17.4273}],
  },
};

function _drawGtfsTestLines() {
  for (const [ligneId, data] of Object.entries(_GTFS_DATA)) {
    const { color, label, trace, arrets } = data;

    // Polyline GTFS en gras par-dessus le tracé de fond
    L.polyline(trace, {
      color,
      weight:   6,
      opacity:  0.9,
      lineJoin: 'round',
      lineCap:  'round',
    })
    .addTo(_map)
    .bindTooltip(label, {
      sticky:    true,
      className: 'trace-tooltip gtfs-trace-tooltip',
      opacity:   1,
    });

    // Arrêts
    arrets.forEach((stop, idx) => {
      const isTerminus  = idx === 0 || idx === arrets.length - 1;
      const radius      = isTerminus ? 9 : 5;
      const fillColor   = isTerminus ? color : '#ffffff';
      const tooltipHtml =
        `<b>L${ligneId} — ${stop.nom}</b>` +
        `<br><span class="gtfs-coords">${stop.lat.toFixed(6)}, ${stop.lon.toFixed(6)}</span>` +
        (isTerminus ? `<br><span class="gtfs-terminus-badge">Terminus</span>` : '');

      const circle = L.circleMarker([stop.lat, stop.lon], {
        radius,
        color,
        weight:      isTerminus ? 3 : 2,
        fillColor,
        fillOpacity: isTerminus ? 1 : 0.92,
        pane:        'markerPane',  // au-dessus des polylines
      })
      .addTo(_map)
      .bindTooltip(tooltipHtml, {
        direction:  'top',
        offset:     [0, -radius - 3],
        className:  'stop-tooltip gtfs-stop-tooltip',
        permanent:  false,
        opacity:    1,
      });

      // Mobile : tap ouvre le tooltip
      circle.on('click', () => circle.openTooltip());

      _gtfsStopMarkers.push(circle);
    });

    console.log(`[Map] GTFS L${ligneId} — ${arrets.length} arrêts tracés`);
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
    html: `<div class="bus-marker ${isSelected ? 'bus-marker--selected' : ''}"
                style="width:${size}px;height:${size}px;background:${color};border-radius:50%;
                       display:flex;align-items:center;justify-content:center;
                       font-weight:700;font-size:${isSelected ? 14 : 12}px;color:#fff;
                       border:2px solid rgba(255,255,255,0.8);
                       box-shadow:0 2px 8px rgba(0,0,0,0.4);">
               ${bus.ligne}
             </div>`,
    iconSize:   [size, size],
    iconAnchor: [size / 2, size / 2],
  });

  const marker = L.marker([bus.lat, bus.lng], { icon, zIndexOffset: isSelected ? 1000 : 0 })
    .addTo(_map)
    .bindPopup(_buildPopupHtml(bus), {
      className:   'bus-popup',
      maxWidth:    260,
      closeButton: false,
    });

  marker.on('click', () => {
    store.set('selectedBus', bus);
    if (_onBusSelect) _onBusSelect(bus);
  });

  return { marker, bus };
}

// ── ANIMATIONS BUS ────────────────────────────────────────

const _BUS_ANIM_SPEED = 0.00003; // degrés/frame ≈ 3m/frame

function _startBusAnimation(bus) {
  const trace = _allTraces[String(bus.ligne)];
  if (!trace || trace.coords.length < 2) return;

  const coords = trace.coords;
  const state  = { idx: 0, progress: Math.random(), rafId: null, stopped: false };
  _animations[bus.id] = state;

  function step() {
    if (state.stopped) return;

    const a = coords[state.idx];
    const b = coords[state.idx + 1];

    if (!a || !b) {
      state.idx = 0;
      state.progress = 0;
      state.rafId = requestAnimationFrame(step);
      return;
    }

    const dist = Math.sqrt(_distSq(a[0], a[1], b[0], b[1]));
    const step_progress = dist > 0 ? _BUS_ANIM_SPEED / dist : 0.01;

    state.progress += step_progress;
    if (state.progress >= 1) {
      state.progress -= 1;
      state.idx++;
      if (state.idx >= coords.length - 1) {
        state.idx = 0;
      }
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
 * Ne touche PAS à _gtfsStopMarkers.
 */
export function showLineOverlay(lineData) {
  clearLineOverlay();
  if (!lineData) return;

  const stops = (lineData.stops || lineData.arrets || []).filter(s => (s.confidence ?? 1) >= 0.5);
  const color  = _getLineColor(lineData.line_id || '');

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
  // _gtfsStopMarkers intentionnellement non effacés ici
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