/**
 * js/signal.js — V3.7
 * V3.7 : FIX _loadRoutes — wrapper j.lignes correct + fallback j
 *        FIX _loadArrets — résolution clé ligne robuste
 *        FIX _snapToStop — idem résolution clé
 *        Structure JSON : { lignes: { "1": { arrets: [{nom, lat, lon}] }, "4": {...} } }
 */

import * as store  from './store.js';
import * as Toast  from './toast.js';
import { API_BASE, LIGNES_CONNUES, SESSION_PREFIX } from './constants.js';
import { generateUUID } from './utils.js';
import { incrementScore } from './mylines.js';

// ── État ──────────────────────────────────────────────────
let _selectedLigne   = null;
let _selectedQual    = null;
let _geolocData      = null;
let _geolocPending   = false;
let _pendingLigne    = null;
let _pendingTimer    = null;
let _mapSignal       = null;
let _userMarker      = null;
let _mapReady        = false;
let _allLinesVisible = false;
let _onSuccessRef    = null;

// Autocomplete
let _dropdownEl  = null;
let _arretsList  = [];

const SESSION_ID = `${SESSION_PREFIX}${generateUUID()}`;

const DEFAULT_PRIORITY = ['1', '4', '7', '15'];

function _getPriorityLines() {
  try {
    const favs = JSON.parse(localStorage.getItem('xetu_fav_lines') || '[]');
    const recent = favs.filter(l => LIGNES_CONNUES.has(l)).slice(0, 4);
    if (recent.length === 4) return recent;
    const fill = DEFAULT_PRIORITY.filter(l => !recent.includes(l));
    return [...recent, ...fill].slice(0, 4);
  } catch {
    return DEFAULT_PRIORITY;
  }
}

// ── Init ──────────────────────────────────────────────────

export function initSignal({ onSuccess }) {
  _onSuccessRef = onSuccess;
  _buildLigneGrid();
  _attachEvents(onSuccess);
  store.subscribe('favLines', () => _buildLigneGrid());
}

export function onScreenEnter() {
  if (!_mapReady) { _initMap(); _mapReady = true; }
  if (!_geolocData && !_geolocPending) _startAutoGPS();
}

// ── Carte ─────────────────────────────────────────────────

function _initMap() {
  _mapSignal = L.map('map-signal', { zoomControl: false, attributionControl: false })
    .setView([14.716, -17.467], 14);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, subdomains: 'abc',
  }).addTo(_mapSignal);
}

function _updateUserMarker(lat, lon) {
  if (!_mapSignal) return;
  if (_userMarker) _mapSignal.removeLayer(_userMarker);
  const icon = L.divIcon({
    html: `<div style="width:16px;height:16px;border-radius:50%;background:#3b82f6;border:3px solid #fff;box-shadow:0 2px 8px rgba(59,130,246,0.7)"></div>`,
    iconAnchor: [8, 8], className: 'xetu-bus-marker',
  });
  _userMarker = L.marker([lat, lon], { icon }).addTo(_mapSignal);
  _mapSignal.setView([lat, lon], 15);
}

// ── GPS auto ──────────────────────────────────────────────

async function _startAutoGPS() {
  if (_geolocPending || _geolocData) return;
  if (!navigator.geolocation) {
    _showGeoStatus('⚠️ GPS non disponible — entre l\'arrêt manuellement', 'geo-warn');
    return;
  }
  _geolocPending = true;
  _showGpsSpinner(true);
  _updateSendBtn();
  try {
    const pos = await new Promise((resolve, reject) =>
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true, timeout: 8000, maximumAge: 30000,
      })
    );
    const { latitude: lat, longitude: lon } = pos.coords;
    _geolocData = { lat, lon, nearest_stop: null, snapped: false, distance_m: null };
    _updateUserMarker(lat, lon);
    _showGpsSpinner(false);
    _showMapLabel(true);
    _showGeoStatus('📍 Position GPS capturée', 'geo-ok');
    const _gpsBtn = document.getElementById('btn-gps');
    if (_gpsBtn) { _gpsBtn.disabled = false; _gpsBtn.textContent = '✓ GPS'; }
    if (_selectedLigne) await _snapAndFill(lat, lon, _selectedLigne);
    if (_pendingLigne) {
      clearTimeout(_pendingTimer);
      _pendingTimer  = null;
      _selectedLigne = _pendingLigne;
      _pendingLigne  = null;
      await _handleSend(_onSuccessRef);
    }
  } catch (err) {
    _geolocData = null;
    _showGpsSpinner(false);
    let msg = 'GPS indisponible — entre l\'arrêt manuellement';
    if (err.code === 1) msg = 'GPS refusé — entre l\'arrêt à la main';
    else if (err.code === 3) msg = 'GPS trop lent — entre l\'arrêt manuellement';
    _showGeoStatus(`⚠️ ${msg}`, 'geo-warn');
  } finally {
    _geolocPending = false;
    _updateSendBtn();
  }
}

async function _snapAndFill(lat, lon, ligne) {
  try {
    const snap = await _snapToStop(lat, lon, ligne);
    if (snap.snapped && snap.name) {
      _geolocData.nearest_stop = snap.name;
      _geolocData.snapped      = true;
      _geolocData.distance_m   = snap.dist;
      const el = document.getElementById('arret-input');
      if (el && !el.value.trim()) el.value = snap.name;
      _showGeoStatus(`📍 ${snap.name} · à ${snap.dist} m`, 'geo-ok');
      _updateSendBtn();
    }
  } catch { /* silencieux */ }
}

// ── GPS manuel ────────────────────────────────────────────

async function _handleGPS() {
  if (_geolocPending) return;
  const btn = document.getElementById('btn-gps');
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
  _geolocData = null; _geolocPending = true;
  try {
    const pos = await new Promise((resolve, reject) => {
      if (!navigator.geolocation) { reject(new Error('NOT_SUPPORTED')); return; }
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true, timeout: 10000, maximumAge: 0,
      });
    });
    const { latitude: lat, longitude: lon } = pos.coords;
    _geolocData = { lat, lon, nearest_stop: null, snapped: false, distance_m: null };
    _updateUserMarker(lat, lon);
    _showMapLabel(true);
    if (_selectedLigne) await _snapAndFill(lat, lon, _selectedLigne);
    else _showGeoStatus('📍 Position capturée · sélectionne une ligne', 'geo-ok');
    if (btn) btn.textContent = '✓ GPS';
  } catch (err) {
    _geolocData = null;
    let msg = 'GPS indisponible.';
    if (err.code === 1) msg = 'GPS refusé. Active la localisation.';
    else if (err.code === 3) msg = 'Délai GPS dépassé.';
    _showGeoStatus(`⚠️ ${msg}`, 'geo-err');
    if (btn) { btn.disabled = false; btn.textContent = '📍 GPS'; }
  } finally {
    _geolocPending = false;
    _updateSendBtn();
  }
}

// ── Grille ────────────────────────────────────────────────

function _buildLigneGrid() {
  const grid = document.getElementById('ligne-grid');
  if (!grid) return;

  const priority = _getPriorityLines();
  const otherCount = [...LIGNES_CONNUES].length - priority.length;

  let html = `<div class="sg-grid-wrap">
    <div class="sg-priority-grid">`;

  priority.forEach(l => {
    const sel = l === _selectedLigne ? ' sg-chip--selected' : '';
    html += `<button class="sg-chip${sel}" data-ligne="${l}">${l}</button>`;
  });

  html += `</div>
    <button class="sg-expand-btn" id="btn-all-lines">
      <span>Toutes les lignes (+${otherCount})</span>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
           style="transition:transform 0.2s;${_allLinesVisible ? 'transform:rotate(180deg)' : ''}">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>`;

  if (_allLinesVisible) {
    html += `<div class="sg-search-wrap">
      <input type="text" id="ligne-search-input" class="sg-search"
             placeholder="Chercher une ligne…" autocomplete="off" maxlength="10">
    </div>
    <div class="sg-all-grid" id="all-lines-grid">`;
    _getSortedLines().forEach(l => {
      const sel = l === _selectedLigne ? ' sg-chip--selected' : '';
      html += `<button class="sg-chip${sel}" data-ligne="${l}">${l}</button>`;
    });
    html += `</div>`;
  }

  html += `</div>`;
  grid.innerHTML = html;
  _attachGridEvents(grid);
}

function _getSortedLines(filter = '') {
  let all = [...LIGNES_CONNUES].sort((a, b) => {
    const na = parseFloat(a), nb = parseFloat(b);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return a.localeCompare(b);
  });
  if (filter) {
    const f = filter.toLowerCase();
    all = all.filter(l => l.toLowerCase().includes(f));
  }
  return all;
}

function _attachGridEvents(grid) {
  grid.querySelectorAll('[data-ligne]').forEach(btn => {
    btn.addEventListener('click', () => {
      grid.querySelectorAll('[data-ligne]').forEach(b => b.classList.remove('sg-chip--selected'));
      btn.classList.add('sg-chip--selected');
      _selectLigne(btn.dataset.ligne);
    });
  });

  grid.querySelector('#btn-all-lines')?.addEventListener('click', () => {
    _allLinesVisible = !_allLinesVisible;
    _buildLigneGrid();
    if (_allLinesVisible) setTimeout(() => document.getElementById('ligne-search-input')?.focus(), 50);
  });

  grid.querySelector('#ligne-search-input')?.addEventListener('input', (e) => {
    const filter  = e.target.value.trim();
    const allGrid = document.getElementById('all-lines-grid');
    if (!allGrid) return;
    allGrid.innerHTML = _getSortedLines(filter).map(l => {
      const sel = l === _selectedLigne ? ' sg-chip--selected' : '';
      return `<button class="sg-chip${sel}" data-ligne="${l}">${l}</button>`;
    }).join('');
    allGrid.querySelectorAll('[data-ligne]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('[data-ligne]').forEach(b => b.classList.remove('sg-chip--selected'));
        btn.classList.add('sg-chip--selected');
        _selectLigne(btn.dataset.ligne);
      });
    });
  });
}

// ── Sélection ligne ───────────────────────────────────────

function _selectLigne(ligne) {
  _selectedLigne = ligne;
  _saveFavoriteLine(ligne);
  _updateSendBtn();
  _loadArrets(ligne);
  if (_geolocData?.lat) {
    _snapAndFill(_geolocData.lat, _geolocData.lon, ligne).then(() => _updateSendBtn());
  }
}

// ── Résolution clé ligne dans le JSON ─────────────────────
// Structure : { "1": {...}, "4": {...}, "16A": {...}, "TAF TAF": {...} }
// Les clés sont exactement les numéros de ligne tels quels.

function _resolveLineData(routes, ligne) {
  if (!routes || !ligne) return null;
  const l = String(ligne);
  return routes[l]
      || routes[l.toUpperCase()]
      || routes[l.toLowerCase()]
      || routes[String(parseInt(l))]   // "04" → "4"
      || null;
}

// ── Cache routes ──────────────────────────────────────────

let _routesCache = null;

async function _loadRoutes() {
  if (_routesCache) return _routesCache;

  const paths = [
    '/data/routes_geometry_v13_fixed2.json',
    './data/routes_geometry_v13_fixed2.json',
    '/routes_geometry_v13_fixed2.json',
    './routes_geometry_v13_fixed2.json',
  ];

  for (const path of paths) {
    try {
      const r = await fetch(path);
      if (!r.ok) continue;
      const j = await r.json();
      // Structure réelle : { version, generated_at, source, lignes: { "1": {...}, "4": {...} } }
      _routesCache = j.lignes || j.routes || j;
      console.log('[Signal] Routes chargées depuis', path,
        '— lignes:', Object.keys(_routesCache).length);
      return _routesCache;
    } catch {
      continue;
    }
  }

  console.error('[Signal] Impossible de charger routes_geometry_v13_fixed2.json');
  _routesCache = {};
  return _routesCache;
}

// ── Autocomplete arrêts ───────────────────────────────────

async function _loadArrets(ligne) {
  const routes   = await _loadRoutes();
  const lineData = _resolveLineData(routes, ligne);

  if (!lineData) {
    console.warn('[Signal] Ligne introuvable dans routes:', ligne);
    _arretsList = [];
    return;
  }

  // Structure arrêt : { nom, lat, lon, confidence, temps_vers_suivant_sec }
  const stops = lineData.arrets || lineData.stops || [];
  _arretsList = stops.map(s => s.nom || s.name).filter(Boolean);
  console.log('[Signal] Arrêts chargés — ligne', ligne, ':', _arretsList.length);
}

function _showDropdown(matches) {
  _removeDropdown();
  if (!matches.length) return;

  const input = document.getElementById('arret-input');
  if (!input) return;

  const dd = document.createElement('div');
  dd.id        = 'arret-dropdown';
  dd.className = 'arret-dropdown';

  matches.slice(0, 6).forEach(name => {
    const item = document.createElement('div');
    item.className   = 'arret-dropdown-item';
    item.textContent = name;
    item.addEventListener('mousedown', (e) => {
      e.preventDefault();
      input.value = name;
      _removeDropdown();
      _updateSendBtn();
      if (_geolocData?.lat) {
        _snapAndFill(_geolocData.lat, _geolocData.lon, _selectedLigne);
      }
    });
    item.addEventListener('touchend', (e) => {
      e.preventDefault();
      input.value = name;
      _removeDropdown();
      _updateSendBtn();
    });
    dd.appendChild(item);
  });

  input.parentElement.style.position = 'relative';
  input.parentElement.appendChild(dd);
  _dropdownEl = dd;
}

function _removeDropdown() {
  if (_dropdownEl) { _dropdownEl.remove(); _dropdownEl = null; }
}

function _onArretInput(e) {
  _updateSendBtn();
  const val = e.target.value.trim().toLowerCase();
  if (!val) { _removeDropdown(); return; }

  if (!_arretsList.length && _selectedLigne) {
    _loadArrets(_selectedLigne).then(() => {
      const matches = _arretsList.filter(n => n.toLowerCase().includes(val));
      _showDropdown(matches);
    });
    return;
  }

  const matches = _arretsList.filter(n => n.toLowerCase().includes(val));
  _showDropdown(matches);
}

function _onArretFocus() {
  if (!_selectedLigne) return;

  const show = () => {
    const val     = document.getElementById('arret-input')?.value.trim().toLowerCase() || '';
    const matches = val
      ? _arretsList.filter(n => n.toLowerCase().includes(val))
      : _arretsList;
    _showDropdown(matches);
  };

  if (!_arretsList.length) {
    _loadArrets(_selectedLigne).then(show);
  } else {
    show();
  }
}

// ── Snap GPS → arrêt le plus proche ──────────────────────

async function _snapToStop(lat, lon, ligne) {
  const routes   = await _loadRoutes();
  const lineData = _resolveLineData(routes, ligne);
  if (!lineData) return { snapped: false };

  const stops = lineData.arrets || lineData.stops || [];
  let best = null, bestDist = Infinity;

  for (const s of stops) {
    if (s.lat == null || s.lon == null) continue;
    const d = _haversine(lat, lon, s.lat, s.lon);
    if (d < bestDist) { bestDist = d; best = s.nom || s.name || null; }
  }

  const dist = Math.round(bestDist);
  return bestDist <= 800
    ? { snapped: true, name: best, dist }
    : { snapped: false, dist };
}

// ── Haversine ─────────────────────────────────────────────

function _haversine(a, b, c, d) {
  const R = 6371000, p1 = a * Math.PI / 180, p2 = c * Math.PI / 180;
  const dp = (c - a) * Math.PI / 180, dl = (d - b) * Math.PI / 180;
  const x  = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

// ── UI helpers ────────────────────────────────────────────

function _showGpsSpinner(show) {
  const spinner = document.getElementById('gps-spinner');
  if (!spinner) return;
  spinner.hidden = !show;
  spinner.style.display = show ? 'flex' : 'none';
}

function _showMapLabel(active) {
  const label = document.getElementById('signal-map-label');
  if (!label) return;
  label.hidden = false;
  label.innerHTML = active
    ? `<span class="pos-dot pos-dot--active"></span> Ta position GPS`
    : `<span class="pos-dot pos-dot--wait"></span> Position en attente`;
}

function _showGeoStatus(text, cls) {
  const el = document.getElementById('geoloc-status');
  if (!el) return;
  el.textContent = text;
  el.className   = `geoloc-status ${cls}`;
  el.hidden      = false;
}

function _updateSendBtn() {
  const arret  = document.getElementById('arret-input')?.value.trim() || '';
  const hasGps = !!(_geolocData?.lat);
  const ok     = !!_selectedLigne && (arret.length >= 2 || hasGps);
  const btn    = document.getElementById('btn-send');
  const hint   = document.getElementById('send-hint');
  if (btn) { btn.disabled = !ok; btn.classList.toggle('btn-send--pulse', ok); }
  if (hint) {
    if (!_selectedLigne)                          hint.textContent = 'Sélectionne une ligne';
    else if (_geolocPending)                      hint.textContent = '⏳ GPS en cours…';
    else if (!ok)                                 hint.textContent = 'Indique l\'arrêt ou attends le GPS';
    else if (hasGps && _geolocData?.nearest_stop) hint.textContent = `📍 ${_geolocData.nearest_stop}`;
    else if (hasGps)                              hint.textContent = '📍 Position GPS prête';
    else                                          hint.textContent = 'Prêt à envoyer';
  }
}

// ── Qualité ───────────────────────────────────────────────

function _initQualityTags() {
  document.getElementById('btn-quality-toggle')?.addEventListener('click', () => {
    const panel = document.getElementById('quality-panel');
    const btn   = document.getElementById('btn-quality-toggle');
    if (!panel) return;
    const isOpen = !panel.hidden;
    panel.hidden = isOpen;
    if (btn) btn.textContent = isOpen ? '＋ Ajouter une observation (optionnel)' : '－ Masquer';
  });
  document.querySelectorAll('.quality-tag').forEach(tag => {
    tag.addEventListener('click', () => {
      const isSel = tag.classList.contains('selected');
      document.querySelectorAll('.quality-tag').forEach(t => t.classList.remove('selected'));
      _selectedQual = isSel ? null : tag.dataset.val;
      if (!isSel) tag.classList.add('selected');
    });
  });
}

// ── Envoi ─────────────────────────────────────────────────

async function _handleSend(onSuccess) {
  const arretRaw = document.getElementById('arret-input')?.value.trim() || '';
  const hasGps   = !!(_geolocData?.lat);
  if (!_selectedLigne || (!arretRaw && !hasGps)) return;

  const arret = arretRaw || _geolocData?.nearest_stop || 'Position GPS';
  const btn   = document.getElementById('btn-send');
  if (btn) { btn.disabled = true; btn.textContent = 'Envoi…'; btn.classList.remove('btn-send--pulse'); }

  const payload = {
    ligne:      _selectedLigne,
    arret,
    source:     hasGps ? 'web_geoloc' : 'web_dashboard',
    client_ts:  new Date().toISOString(),
    session_id: SESSION_ID,
  };
  if (_selectedQual) payload.observation = _selectedQual;
  if (hasGps) { payload.lat = _geolocData.lat; payload.lon = _geolocData.lon; }

  try {
    const res = await fetch(`${API_BASE}/api/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.status === 201 || res.status === 200) {
      Toast.success(`✅ Bus ${_selectedLigne} signalé !`);
      incrementScore();
      _reset();
      onSuccess?.();
    } else if (res.status === 429) {
      Toast.error('⏱ Trop de signalements. Réessaie dans quelques min.');
      if (btn) { btn.disabled = false; btn.textContent = 'Envoyer le signalement'; }
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (err) {
    Toast.error('❌ Envoi échoué. Vérifie ta connexion.');
    console.error('[Signal]', err);
    if (btn) { btn.disabled = false; btn.textContent = 'Envoyer le signalement'; }
  } finally {
    _updateSendBtn();
  }
}

// ── Reset ─────────────────────────────────────────────────

function _reset() {
  _selectedLigne = null; _selectedQual = null;
  _geolocData = null; _geolocPending = false;
  _pendingLigne = null; _allLinesVisible = false;
  _arretsList = [];
  clearTimeout(_pendingTimer); _pendingTimer = null;

  const arretInput = document.getElementById('arret-input');
  if (arretInput) arretInput.value = '';
  _removeDropdown();

  const geoStatus = document.getElementById('geoloc-status');
  if (geoStatus) geoStatus.hidden = true;

  const gpsBtn = document.getElementById('btn-gps');
  if (gpsBtn) { gpsBtn.disabled = false; gpsBtn.textContent = '📍 GPS'; }

  document.querySelectorAll('.quality-tag').forEach(b => b.classList.remove('selected'));

  const qualPanel = document.getElementById('quality-panel');
  if (qualPanel) qualPanel.hidden = true;

  const qualBtn = document.getElementById('btn-quality-toggle');
  if (qualBtn) qualBtn.textContent = '＋ Ajouter une observation (optionnel)';

  if (_mapSignal && _userMarker) { _mapSignal.removeLayer(_userMarker); _userMarker = null; }
  _showMapLabel(false);

  const mapLabel = document.getElementById('signal-map-label');
  if (mapLabel) mapLabel.hidden = false;

  _buildLigneGrid();
  _updateSendBtn();
}

// ── Favoris ───────────────────────────────────────────────

function _saveFavoriteLine(ligne) {
  try {
    const raw  = localStorage.getItem('xetu_fav_lines') || '[]';
    const favs = JSON.parse(raw);
    if (!favs.includes(ligne)) {
      const newFavs = [ligne, ...favs].slice(0, 4);
      localStorage.setItem('xetu_fav_lines', JSON.stringify(newFavs));
      store.set('favLines', newFavs);
    }
  } catch {}
}

// ── Events ────────────────────────────────────────────────

function _attachEvents(onSuccess) {
  document.getElementById('btn-gps')?.addEventListener('click', _handleGPS);
  document.getElementById('btn-send')?.addEventListener('click', () => _handleSend(onSuccess));
  _initQualityTags();

  const arretInput = document.getElementById('arret-input');
  if (arretInput) {
    arretInput.addEventListener('input',   _onArretInput);
    arretInput.addEventListener('focus',   _onArretFocus);
    arretInput.addEventListener('blur',    () => setTimeout(_removeDropdown, 150));
    arretInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') _removeDropdown();
      if (e.key === 'ArrowDown') {
        const first = _dropdownEl?.querySelector('.arret-dropdown-item');
        if (first) { e.preventDefault(); first.focus(); }
      }
    });
  }
}