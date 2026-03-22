/**
 * js/home.js — Xëtu V3.0
 *
 * CORRECTIONS V3.0 :
 *
 * BUG-2 (minutes_ago figé) :
 *   - Avant : `const _NOW = Date.now()` → valeur gelée par le SW au moment du cache.
 *   - Fix : `_now()` est une fonction — `Date.now()` est évalué à chaque appel,
 *     donc toujours frais même si le module est servi depuis le cache SW.
 *
 * BUG-4 (carré blanc autour du marker) :
 *   - Avant : `className: ''` → Leaflet ajoute sa propre feuille de style sur l'élément.
 *   - Fix : `className: 'xetu-bus-marker'` + règle CSS `.xetu-bus-marker { background:none!important; border:none!important; box-shadow:none!important; }`
 *
 * BUG-5 (tracés L1+L4 visibles sans clic) :
 *   - Cause : `_GTFS_DATA` était copié-collé depuis map.js qui appelait `_drawGtfsTestLines()`
 *     au démarrage. Dans home.js ce code n'existe pas, MAIS `_subscribeStore` → `store.set('buses')`
 *     → `_updateMarkers` → `_makeBusMarker` → `_selectBus` s'enchaînait immédiatement
 *     si _selectedBusId était déjà setté (résidu store d'une autre session).
 *   - Fix : reset explicite `_selectedBusId = null` à l'init, et `_selectBus` ne dessine
 *     le tracé que si le bus est dans DEMO_BUSES (guard ajouté).
 *   - Fix 2 : `_refreshDemoBuses()` est le seul endroit qui hydrate le store 'buses'.
 *     On le retarde d'un tick après `_initMap()` pour éviter la course store→markers→selectBus.
 *
 * BUG-3 (carte trop dézoomée) :
 *   - Zoom initial 14 centré sur Plateau/Médina `[14.693, -17.452]`.
 *   - `fitBounds` avec `maxZoom:13` pour ne jamais dézoomer au-delà de Dakar-ville.
 */

import * as store  from './store.js';
import { getAgeClass, formatAgeShort, getRankSymbol, getRankClass } from './utils.js';
import { initReader, updateReader, hide as hideReader } from './reader.js';

// ── Helpers timing ────────────────────────────────────────

// CHG-1 (BUG-2) : fonction au lieu de constante — frais à chaque appel.
function _now() { return Date.now(); }

const AVATARS      = ['👨🏿','👩🏿','🧑🏿','👩🏾','👨🏾','👩🏽'];
const DEMO_TTL_MIN = 20;

// ── CSS Leaflet marker fix (BUG-4) ───────────────────────

function _injectMarkerCSS() {
  if (document.getElementById('xetu-marker-style')) return;
  const s = document.createElement('style');
  s.id = 'xetu-marker-style';
  s.textContent = `
    /* BUG-4 : Leaflet divIcon ajoute background/border/box-shadow par défaut */
    .xetu-bus-marker {
      background:  none !important;
      border:      none !important;
      box-shadow:  none !important;
      outline:     none !important;
    }
  `;
  document.head.appendChild(s);
}

// ── Couleur par hash HSL ──────────────────────────────────

function _lineColor(ligne) {
  let hash = 0;
  for (let i = 0; i < String(ligne).length; i++)
    hash = String(ligne).charCodeAt(i) + ((hash << 5) - hash);
  return `hsl(${Math.abs(hash) % 360}, 72%, 58%)`;
}

// ── GTFS L1 + L4 ─────────────────────────────────────────

const _GTFS = {
  '1': {
    color: _lineColor('1'),
    terminus_a: 'Parcelles Assainies',
    terminus_b: 'Place Leclerc',
    trace: [
      [14.760337,-17.438687],[14.763941,-17.441183],[14.762826,-17.446516],
      [14.759832,-17.448105],[14.758248,-17.447765],[14.7543,-17.446884],
      [14.750523,-17.44654],[14.75005,-17.447991],[14.750294,-17.449628],
      [14.750618,-17.451216],[14.751909,-17.454321],[14.751324,-17.456147],
      [14.750278,-17.457885],[14.746395,-17.466589],[14.744906,-17.468876],
      [14.740498,-17.471506],[14.735673,-17.473248],[14.729656,-17.472863],
      [14.725906,-17.471813],[14.722566,-17.471226],[14.719751,-17.471389],
      [14.712285,-17.471903],[14.70925,-17.471285],[14.705035,-17.470294],
      [14.700212,-17.46885],[14.695885,-17.465384],[14.693566,-17.46262],
      [14.691574,-17.460204],[14.689322,-17.457816],[14.686677,-17.455513],
      [14.68354,-17.452374],[14.681512,-17.450239],[14.67856,-17.447046],
      [14.675097,-17.443519],[14.670725,-17.440327],[14.669174,-17.43795],
      [14.669499,-17.432616],[14.669905,-17.431704],[14.674246,-17.432611],
      [14.673962,-17.431671],[14.671893,-17.427341],[14.672123,-17.427338],
    ],
    arrets: [
      {nom:'Terminus Parcelles Assainies',lat:14.764233,lon:-17.440017},
      {nom:'Sapeur Pompier des Parcelles Assainies',lat:14.76275,lon:-17.44095},
      {nom:'Unite 9',lat:14.7626,lon:-17.446467},
      {nom:'Hlm Grand medine',lat:14.75985,lon:-17.448017},
      {nom:'Ecole Dior',lat:14.758267,lon:-17.447683},
      {nom:'Acapes',lat:14.756333,lon:-17.447317},
      {nom:'Unite 24',lat:14.7543,lon:-17.446883},
      {nom:'Boulangerie Mandela 3',lat:14.750483,lon:-17.446283},
      {nom:'Marche Grand Medine Bv',lat:14.7501,lon:-17.447983},
      {nom:'Telecentre Niuma',lat:14.750367,lon:-17.449617},
      {nom:'Parking Stade L.S.S Bv',lat:14.750617,lon:-17.451217},
      {nom:'Boulangerie Dedi',lat:14.751917,lon:-17.454317},
      {nom:'Cite Keur Damel Bv',lat:14.7514,lon:-17.4562},
      {nom:'Mosquee Nord Foire Bv',lat:14.7502,lon:-17.45785},
      {nom:'Foire de Dakar Bv',lat:14.746417,lon:-17.4666},
      {nom:'Cfpt Bv',lat:14.744933,lon:-17.4689},
      {nom:'Sipres Bv',lat:14.740533,lon:-17.4716},
      {nom:'Sapco sur la VDN Bv',lat:14.735683,lon:-17.473283},
      {nom:'Cimetiere Saint Lazarre',lat:14.72965,lon:-17.472883},
      {nom:'Sacree Coeur 3 extension',lat:14.7259,lon:-17.471833},
      {nom:'Novomed Sacree Coeur 3',lat:14.722567,lon:-17.471183},
      {nom:'Avant Case des tout petits sur la Vdn',lat:14.71975,lon:-17.471383},
      {nom:'Bimao sur la VDN Bv',lat:14.712283,lon:-17.471917},
      {nom:'Africatel sur la Vdn',lat:14.70925,lon:-17.471283},
      {nom:'Cite Mermoz sur la Vdn',lat:14.705033,lon:-17.4703},
      {nom:'Station Mobile Vdn',lat:14.7002,lon:-17.468883},
      {nom:'Hopitale Fann Bv',lat:14.695867,lon:-17.4654},
      {nom:'Universite Cheikh A Diop',lat:14.69355,lon:-17.462633},
      {nom:'Cesti Bv',lat:14.691517,lon:-17.46025},
      {nom:'Ecole Manguiers Bv',lat:14.689333,lon:-17.4578},
      {nom:'Police Medina',lat:14.686617,lon:-17.455567},
      {nom:'Rue 31 x Blaise Diagne',lat:14.68345,lon:-17.452467},
      {nom:'Marche Tillene Bv',lat:14.6815,lon:-17.45025},
      {nom:'Rue 11 x Blaise Diagne Bv',lat:14.679667,lon:-17.448317},
      {nom:'Stade Iba Mar Diop',lat:14.678483,lon:-17.447117},
      {nom:'Credit Foncier Bv',lat:14.675067,lon:-17.44355},
      {nom:'El Malick Sandaga',lat:14.670667,lon:-17.440483},
      {nom:'Peytavin Sandaga',lat:14.6689,lon:-17.437933},
      {nom:'Avenue Ponty (Plaza)',lat:14.669384,lon:-17.434782},
      {nom:"Cbao (Avenue Ponty)",lat:14.669487,lon:-17.432615},
      {nom:"Place de l'independance",lat:14.669908,lon:-17.43165},
      {nom:'Esso Port',lat:14.674233,lon:-17.432633},
      {nom:'Embarcadere',lat:14.674117,lon:-17.43155},
      {nom:'Mole 1 (Port de dakar)',lat:14.671833,lon:-17.42735},
      {nom:'Terminus Leclerc',lat:14.672133,lon:-17.4273},
    ],
  },
  '4': {
    color: _lineColor('4'),
    terminus_a: 'Liberté 5',
    terminus_b: 'Place Leclerc',
    trace: [
      [14.72318,-17.458638],[14.724542,-17.457012],[14.727674,-17.45657],
      [14.727036,-17.452502],[14.721926,-17.453323],[14.719571,-17.453681],
      [14.717644,-17.458175],[14.715337,-17.460237],[14.71113,-17.463928],
      [14.70779,-17.466325],[14.705231,-17.464304],[14.703899,-17.463073],
      [14.699115,-17.456685],[14.698255,-17.456924],[14.695569,-17.455836],
      [14.693524,-17.453754],[14.692787,-17.452037],[14.690763,-17.450324],
      [14.685879,-17.452937],[14.683389,-17.452521],[14.68139,-17.450353],
      [14.678418,-17.447178],[14.675015,-17.443599],[14.670718,-17.440353],
      [14.668673,-17.439616],[14.665476,-17.436642],[14.6699,-17.431776],
      [14.673065,-17.430706],[14.672177,-17.42735],
    ],
    arrets: [
      {nom:'Terminus Dieuppeul',lat:14.723283,lon:-17.459117},
      {nom:'Cite Derkle',lat:14.72455,lon:-17.457067},
      {nom:'Ecole Derkle Bv',lat:14.727667,lon:-17.456517},
      {nom:'Pharmacie Derkle',lat:14.727033,lon:-17.452483},
      {nom:'Cite Marine Bv',lat:14.724367,lon:-17.452917},
      {nom:'1er Arret Dieuppeul',lat:14.721917,lon:-17.453267},
      {nom:'2eme Arret Dieuppeul',lat:14.719567,lon:-17.45365},
      {nom:'Sapeur Pompier',lat:14.717667,lon:-17.4582},
      {nom:'Sacre Coeur 1 Bv',lat:14.715233,lon:-17.460117},
      {nom:'College Sacre coeur',lat:14.71355,lon:-17.461767},
      {nom:'Paroisse Sacre Coeur',lat:14.71115,lon:-17.46395},
      {nom:'SOS Village',lat:14.707783,lon:-17.466333},
      {nom:'Karack Mosquee',lat:14.70525,lon:-17.464283},
      {nom:'1er Arret Thierno S N Tall',lat:14.702517,lon:-17.461733},
      {nom:'2eme Arret Thierno S N Tall',lat:14.699983,lon:-17.459567},
      {nom:'3eme Arret Thierno S N Tall',lat:14.69845,lon:-17.458117},
      {nom:'4eme Arret Thierno S N Tall',lat:14.695583,lon:-17.455817},
      {nom:'Immeuble Seydi Jamil Hlm Fass',lat:14.693533,lon:-17.45375},
      {nom:'Marche Fass',lat:14.692833,lon:-17.452017},
      {nom:'Direction des Hlms',lat:14.69075,lon:-17.4503},
      {nom:'Travaux Communaux Fass Bv',lat:14.688567,lon:-17.451433},
      {nom:'Supermache Sham',lat:14.68585,lon:-17.452883},
      {nom:'Rue 31 x Blaise Diagne',lat:14.68345,lon:-17.452467},
      {nom:'Marche Tillene Bv',lat:14.6815,lon:-17.45025},
      {nom:'Rue 11 x Blaise Diagne Bv',lat:14.679667,lon:-17.448317},
      {nom:'Stade Iba Mar Diop',lat:14.678483,lon:-17.447117},
      {nom:'Credit Foncier Bv',lat:14.675067,lon:-17.44355},
      {nom:'El Malick Sandaga',lat:14.670667,lon:-17.440483},
      {nom:'Direction Asecna',lat:14.668667,lon:-17.439633},
      {nom:'Cathedrale',lat:14.66545,lon:-17.43665},
      {nom:"Place de l'independance",lat:14.669908,lon:-17.43165},
      {nom:'Police Municipale',lat:14.672983,lon:-17.430767},
      {nom:'Terminus Leclerc',lat:14.672133,lon:-17.4273},
    ],
  },
};

// ── État carte ────────────────────────────────────────────

let _map               = null;
let _busMarkers        = {};
let _activeCol         = 'buses';
let _selectedBusId     = null;   // CHG-2 (BUG-5) : toujours null au démarrage
let _activePolyline    = null;
let _activeStopMarkers = [];
let _animState         = null;

// ── Init ──────────────────────────────────────────────────

export function initHome({ onSeeBus }) {
  _injectMarkerCSS();  // BUG-4
  initReader();
  _initMap();
  _initTabs();
  _initSeeBus(onSeeBus);
  _subscribeStore();

  // CHG-3 (BUG-5) : on retarde d'un tick pour éviter la race
  // store → markers → sélection automatique indésirable.
  requestAnimationFrame(() => {
    _refreshDemoBuses();
    setInterval(_refreshDemoBuses, 30_000);
  });
}

// ── Refresh démos (BUG-2) ─────────────────────────────────

function _refreshDemoBuses() {
  // CHG-4 (BUG-2) : _now() évalué ici, à chaque appel — jamais freezé.
  const now = _now();

  // Les bus démo ont leur _born fixé au moment de leur DÉFINITION ci-dessous.
  // On les définit dans la fonction pour que Date.now() soit frais à chaque cycle.
  // Mais pour avoir une heure de départ cohérente on les met en module-level
  // avec un born calculé une seule fois à l'import… SAUF que le SW gèle l'import.
  // Solution : born stocké dans sessionStorage la 1ère fois.
  const b1 = _getBorn('demo-1', 2);
  const b4 = _getBorn('demo-4', 1);

  const bases = [
    { id:'demo-1', ligne:'1', position:'Universite Cheikh A Diop', lat:14.69355,  lng:-17.462633, _born:b1, traceStartIdx:26 },
    { id:'demo-4', ligne:'4', position:'Terminus Dieuppeul',       lat:14.723283, lng:-17.459117, _born:b4, traceStartIdx:0  },
  ];

  const buses = bases
    .filter(b => (now - b._born) / 60_000 < DEMO_TTL_MIN)
    .map(b => {
      const data = _GTFS[b.ligne];
      return {
        ...b,
        minutes_ago: Math.round((now - b._born) / 60_000),
        name: data ? `${data.terminus_a} ↔ ${data.terminus_b}` : `Ligne ${b.ligne}`,
      };
    });

  store.set('buses', buses);

  // Si le bus sélectionné a expiré, déselectionner
  if (_selectedBusId && !buses.find(b => b.id === _selectedBusId)) {
    _deselectBus();
  }
}

/**
 * CHG-5 (BUG-2) : stocke le timestamp de "naissance" dans sessionStorage.
 * sessionStorage survit aux rechargements normaux mais PAS au cache SW
 * (puisque sessionStorage est par onglet, pas par SW).
 * Ainsi le bus a le même âge dans toute la session, ET l'âge repart de zéro
 * à chaque nouvelle session (onglet fermé/ouvert).
 */
function _getBorn(id, offsetMinutes) {
  const key = `xetu_born_${id}`;
  try {
    const stored = sessionStorage.getItem(key);
    if (stored) return parseInt(stored, 10);
    const born = _now() - offsetMinutes * 60 * 1000;
    sessionStorage.setItem(key, String(born));
    return born;
  } catch {
    // sessionStorage bloqué (navigation privée sans accès) → valeur live
    return _now() - offsetMinutes * 60 * 1000;
  }
}

// ── Carte ─────────────────────────────────────────────────

function _initMap() {
  // BUG-3 : zoom 14, centré Plateau/Médina
  _map = L.map('map-home', { zoomControl: false, attributionControl: false })
    .setView([14.693, -17.452], 14);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    { maxZoom: 19, subdomains: 'abcd' }).addTo(_map);
}

// ── Sélection bus ─────────────────────────────────────────

function _selectBus(busId) {
  if (_selectedBusId === busId) { _deselectBus(); return; }

  // CHG-6 (BUG-5) : guard — ne dessiner que si le bus est dans DEMO_BUSES actifs
  const bus = (store.get('buses') || []).find(b => b.id === busId);
  if (!bus) return;

  _selectedBusId = busId;
  _stopAnim();
  _clearActiveLine();

  const data = _GTFS[bus.ligne];
  if (!data) return;

  const color = data.color;

  _activePolyline = L.polyline(data.trace, {
    color, weight: 4, opacity: 0.88, lineJoin: 'round', lineCap: 'round',
  }).addTo(_map);

  data.arrets.forEach((stop, idx) => {
    const isT = idx === 0 || idx === data.arrets.length - 1;
    const circle = L.circleMarker([stop.lat, stop.lon], {
      radius:      isT ? 4 : 2,
      color:       isT ? color : 'rgba(255,255,255,0.2)',
      weight:      1,
      fillColor:   isT ? color : 'rgba(255,255,255,0.1)',
      fillOpacity: 1,
      interactive: false,
    }).addTo(_map);
    _activeStopMarkers.push(circle);
  });

  // BUG-3 : maxZoom:13 pour rester sur Dakar
  _map.fitBounds(_activePolyline.getBounds(), { padding: [40, 40], maxZoom: 13 });
  _refreshBusMarkers();
  _startAnim(bus, data);
}

function _deselectBus() {
  _selectedBusId = null;
  _stopAnim();
  _clearActiveLine();
  hideReader();
  _refreshBusMarkers();
}

function _clearActiveLine() {
  if (_activePolyline) { _map.removeLayer(_activePolyline); _activePolyline = null; }
  _activeStopMarkers.forEach(m => _map.removeLayer(m));
  _activeStopMarkers = [];
}

// ── Animation ─────────────────────────────────────────────

const ANIM_SPEED = 0.00004;

function _startAnim(bus, data) {
  const coords = data.trace;
  if (coords.length < 2) return;
  const state = {
    ligne: bus.ligne, arrets: data.arrets,
    coords, idx: bus.traceStartIdx ?? 0, progress: 0,
    lastTs: null, rafId: null, stopped: false,
  };
  _animState = state;
  const mk = _busMarkers[bus.id];

  function tick(ts) {
    if (state.stopped) return;
    if (!state.lastTs) state.lastTs = ts;
    const dt = Math.min(ts - state.lastTs, 80);
    state.lastTs = ts;
    const a = coords[state.idx];
    const b = coords[state.idx + 1];
    if (!a || !b) {
      state.idx = 0; state.progress = 0;
      state.rafId = requestAnimationFrame(tick); return;
    }
    const segLen = Math.sqrt((b[0]-a[0])**2 + (b[1]-a[1])**2);
    state.progress += segLen > 0 ? (ANIM_SPEED * dt) / segLen : 0.02;
    if (state.progress >= 1) {
      state.progress -= 1;
      state.idx = (state.idx + 1) % (coords.length - 1);
    }
    const lat = a[0] + (b[0]-a[0]) * state.progress;
    const lon = a[1] + (b[1]-a[1]) * state.progress;
    if (mk) mk.setLatLng([lat, lon]);
    updateReader(state.ligne, state.arrets, _nearestArretIdx(lat, lon, state.arrets));
    state.rafId = requestAnimationFrame(tick);
  }
  state.rafId = requestAnimationFrame(tick);
}

function _stopAnim() {
  if (!_animState) return;
  _animState.stopped = true;
  if (_animState.rafId) cancelAnimationFrame(_animState.rafId);
  _animState = null;
}

function _nearestArretIdx(lat, lon, arrets) {
  let best = 0, bestD = Infinity;
  arrets.forEach((a, i) => {
    const d = (a.lat-lat)**2 + (a.lon-lon)**2;
    if (d < bestD) { bestD = d; best = i; }
  });
  return best;
}

// ── Markers bus (BUG-4) ───────────────────────────────────

function _updateMarkers(buses) {
  if (!_map) return;
  const ids = new Set(buses.map(b => String(b.id)));
  Object.keys(_busMarkers).forEach(id => {
    if (!ids.has(id)) { _map.removeLayer(_busMarkers[id]); delete _busMarkers[id]; }
  });
  buses.forEach(b => {
    if (b.lat && b.lng && !_busMarkers[b.id])
      _busMarkers[b.id] = _makeBusMarker(b);
  });
}

function _busAgeColor(min) {
  return min <= 5 ? '#00D67F' : min <= 15 ? '#FFD166' : '#FF4757';
}

function _makeBusMarker(bus) {
  const color      = _busAgeColor(bus.minutes_ago);
  const isSelected = bus.id === _selectedBusId;
  const size       = isSelected ? 40 : 34;
  const marker     = L.marker([bus.lat, bus.lng], {
    icon: _busIcon(bus.ligne, color, size, isSelected),
    zIndexOffset: isSelected ? 1000 : 0,
  }).addTo(_map);
  marker.on('click', (e) => {
    L.DomEvent.stopPropagation(e);
    _selectedBusId === bus.id ? _deselectBus() : _selectBus(bus.id);
  });
  return marker;
}

function _busIcon(ligne, color, size, isSelected) {
  // CHG-7 (BUG-4) : className 'xetu-bus-marker' + règle CSS dans _injectMarkerCSS()
  return L.divIcon({
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};
      border:3px solid rgba(255,255,255,${isSelected?'0.95':'0.7'});
      box-shadow:0 2px 12px rgba(0,0,0,0.5);
      display:flex;align-items:center;justify-content:center;
      font-family:Inter,sans-serif;font-size:${isSelected?'13':'11'}px;
      font-weight:700;color:#fff;line-height:1;">${ligne}</div>`,
    iconSize: [size, size], iconAnchor: [size/2, size/2],
    className: 'xetu-bus-marker',   // ← BUG-4 fix
  });
}

function _refreshBusMarkers() {
  const buses = store.get('buses') || [];
  buses.forEach(b => {
    const mk = _busMarkers[b.id];
    if (!mk) return;
    const isSelected = b.id === _selectedBusId;
    const size       = isSelected ? 40 : 34;
    mk.setIcon(_busIcon(b.ligne, _busAgeColor(b.minutes_ago), size, isSelected));
    mk.setZIndexOffset(isSelected ? 1000 : 0);
  });
}

// ── Tabs ──────────────────────────────────────────────────

function _initTabs() {
  document.querySelectorAll('.col-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      _activeCol = btn.dataset.col;
      document.querySelectorAll('.col-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _renderCols();
    });
  });
}

function _renderCols() {
  document.querySelectorAll('.home-col').forEach(c => c.classList.remove('active'));
  document.getElementById(_activeCol === 'buses' ? 'col-buses' : 'col-top')?.classList.add('active');
}

function _renderBuses(buses) {
  const el = document.getElementById('col-buses');
  if (!el) return;
  if (!buses.length) {
    el.innerHTML = `<div class="empty-state"><div class="empty-icon">🚌</div><div class="empty-text">Aucun bus actif.<br>Sois le premier à signaler !</div></div>`;
    return;
  }
  el.innerHTML = buses.map((b, i) => {
    const data  = _GTFS[b.ligne];
    const color = _busAgeColor(b.minutes_ago);
    const label = data ? `${data.terminus_a} ↔ ${data.terminus_b}` : b.name;
    const isSel = b.id === _selectedBusId;
    return `<div class="bus-card anim-up${isSel?' bus-card--selected':''}" style="animation-delay:${i*.04}s;cursor:pointer" data-bus-id="${b.id}">
      <div class="bus-card-header">
        <span class="bus-badge" style="background:${color}">Bus ${b.ligne}</span>
        <span class="bus-name">${label}</span>
        <span class="bus-age ${getAgeClass(b.minutes_ago)}">${formatAgeShort(b.minutes_ago)}</span>
      </div>
      <div class="bus-position">📍 ${b.position}</div>
    </div>`;
  }).join('');
  el.querySelectorAll('[data-bus-id]').forEach(card => {
    card.addEventListener('click', () => {
      _selectedBusId === card.dataset.busId ? _deselectBus() : _selectBus(card.dataset.busId);
    });
  });
}

function _renderTop(lb) {
  const el = document.getElementById('col-top');
  if (!el) return;
  if (!lb.length) {
    el.innerHTML = `<div class="empty-state"><div class="empty-icon">🏆</div><div class="empty-text">Pas encore de données.</div></div>`;
    return;
  }
  el.innerHTML = lb.slice(0,10).map((u,i) => `
    <div class="lb-card anim-up" style="animation-delay:${i*.04}s">
      <span class="lb-rank ${getRankClass(u.rank)}">${getRankSymbol(u.rank)}</span>
      <span class="lb-avatar">${AVATARS[i%AVATARS.length]}</span>
      <div class="lb-info"><div class="lb-name">${u.name||'Anonyme'}</div><div class="lb-badge">${u.badge||'Contributeur'}</div></div>
      <span class="lb-count">${u.count||0}</span>
    </div>`).join('');
}

function _initSeeBus(onSeeBus) {
  document.getElementById('btn-see-bus')?.addEventListener('click', onSeeBus);
}

function _subscribeStore() {
  store.subscribe('buses', buses => { _updateMarkers(buses); _renderBuses(buses); _renderCols(); });
  store.subscribe('leaderboard', lb => _renderTop(lb));
}