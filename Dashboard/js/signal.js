/**
 * js/signal.js — V3.0
 * Flux signalement 2 gestes pour démo Dem Dikk.
 *
 * CHG-1 : GPS automatique dès que l'écran s'ouvre (IntersectionObserver)
 * CHG-2 : Grille hiérarchisée — 6 prioritaires (56px) > favoris > "Toutes" avec recherche
 * CHG-3 : Envoi immédiat ligne tapée + GPS prêt. Si GPS en cours → file d'attente 3s max
 * CHG-4 : Qualité optionnelle visuellement secondaire (collapse/expand)
 */

import * as store  from './store.js';
import * as Toast  from './toast.js';
import { GeolocError } from './geoloc.js';
import { API_BASE, LIGNES_CONNUES, SESSION_PREFIX } from './constants.js';
import { generateUUID } from './utils.js';
import { incrementScore } from './mylines.js';

// ── État module ───────────────────────────────────────────
let _selectedLigne   = null;
let _selectedQual    = null;
let _geolocData      = null;      // { lat, lon, nearest_stop, snapped, distance_m }
let _geolocPending   = false;     // GPS en cours de recherche
let _pendingLigne    = null;      // ligne tapée pendant que GPS tourne
let _pendingTimer    = null;      // timer 3s max d'attente GPS
let _mapSignal       = null;
let _userMarker      = null;
let _mapReady        = false;
let _allLinesVisible = false;     // état accordéon "Toutes les lignes"
let _onSuccessRef    = null;      // callback conservée pour envoi auto

const SESSION_ID = `${SESSION_PREFIX}${generateUUID()}`;

// Lignes prioritaires — toujours en haut, chips plus grandes
const PRIORITY_LINES = ['1', '4', '7', '8', '10', '15'];

// ── Init ──────────────────────────────────────────────────

export function initSignal({ onSuccess }) {
  _onSuccessRef = onSuccess;
  _buildLigneGrid();
  _attachEvents(onSuccess);
  store.subscribe('favLines', () => _buildLigneGrid());

  // CHG-1 : GPS automatique quand l'écran signal devient visible
  const screen = document.getElementById('screen-signal');
  if (screen) {
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        if (!_mapReady) { _initMap(); _mapReady = true; }
        if (!_geolocData && !_geolocPending) _startAutoGPS();
      }
    });
    observer.observe(screen);
  }

  // Backup : déclenché par le bouton "Je vois un bus ici"
  document.getElementById('btn-see-bus')?.addEventListener('click', () => {
    setTimeout(() => {
      if (!_geolocData && !_geolocPending) _startAutoGPS();
    }, 150);
  }, { capture: true });
}

// ── Carte ─────────────────────────────────────────────────

function _initMap() {
  _mapSignal = L.map('map-signal', { zoomControl: false, attributionControl: false })
    .setView([14.716, -17.467], 14);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    { maxZoom: 19, subdomains: 'abcd' }).addTo(_mapSignal);
}

function _updateUserMarker(lat, lon) {
  if (!_mapSignal) return;
  if (_userMarker) _mapSignal.removeLayer(_userMarker);
  const icon = L.divIcon({
    html: `<div style="width:16px;height:16px;border-radius:50%;background:#3b82f6;border:3px solid #fff;box-shadow:0 2px 8px rgba(59,130,246,0.7)"></div>`,
    iconAnchor: [8, 8], className: '',
  });
  _userMarker = L.marker([lat, lon], { icon }).addTo(_mapSignal);
  _mapSignal.setView([lat, lon], 15);
}

// ── GPS automatique (CHG-1) ───────────────────────────────

async function _startAutoGPS() {
  if (_geolocPending || _geolocData) return;

  _geolocPending = true;
  _showGpsSpinner(true);
  _updateSendBtn();

  try {
    const position = await new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new GeolocError('NOT_SUPPORTED', 'GPS non disponible'));
        return;
      }
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
        timeout: 8000,
        maximumAge: 30000,
      });
    });

    const lat = position.coords.latitude;
    const lon = position.coords.longitude;
    _geolocData = { lat, lon, nearest_stop: null, snapped: false, distance_m: null };

    _updateUserMarker(lat, lon);
    _showMapLabel(true);
    _showGpsSpinner(false);
    _showGeoStatus('📍 Position GPS capturée', 'geo-ok');

    // Snap si une ligne est déjà sélectionnée
    if (_selectedLigne) {
      await _snapAndFill(lat, lon, _selectedLigne);
    }

    // CHG-3 : une ligne était en attente → envoyer maintenant
    if (_pendingLigne) {
      clearTimeout(_pendingTimer);
      _pendingTimer = null;
      const ligneToSend = _pendingLigne;
      _pendingLigne = null;
      _selectedLigne = ligneToSend;
      await _handleSend(_onSuccessRef);
    }

  } catch (err) {
    _geolocData = null;
    _showGpsSpinner(false);
    let msg = 'GPS indisponible — précise l\'arrêt manuellement';
    if (err.code === 1) msg = 'GPS refusé — entre l\'arrêt à la main';
    else if (err.code === 3) msg = 'GPS trop lent — entre l\'arrêt manuellement';
    _showGeoStatus(`⚠️ ${msg}`, 'geo-warn');
    // Non bloquant : l'utilisateur peut saisir l'arrêt
  } finally {
    _geolocPending = false;
    _updateSendBtn();
  }
}

// Snap + pré-remplir champ arrêt
async function _snapAndFill(lat, lon, ligne) {
  try {
    const snap = await _snapToStop(lat, lon, ligne);
    if (snap.snapped && snap.name) {
      _geolocData.nearest_stop = snap.name;
      _geolocData.snapped      = true;
      _geolocData.distance_m   = snap.dist;
      const arretInput = document.getElementById('arret-input');
      if (arretInput && !arretInput.value.trim()) {
        arretInput.value = snap.name;
      }
      _showGeoStatus(`📍 ${snap.name} · à ${snap.dist} m`, 'geo-ok');
      _updateSendBtn();
    }
  } catch { /* snap échoué silencieusement */ }
}

// ── Bouton GPS manuel (fallback si auto échoué) ───────────

async function _handleGPS() {
  if (_geolocPending) return;

  const btn = document.getElementById('btn-gps');
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }

  _geolocData    = null;
  _geolocPending = true;

  try {
    if (navigator.permissions) {
      const perm = await navigator.permissions.query({ name: 'geolocation' });
      if (perm.state === 'denied') throw new GeolocError('DENIED', 'GPS refusé. Active la localisation.');
    }

    const position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true, timeout: 10000, maximumAge: 0,
      });
    });

    const lat = position.coords.latitude;
    const lon = position.coords.longitude;
    _geolocData = { lat, lon, nearest_stop: null, snapped: false, distance_m: null };
    _updateUserMarker(lat, lon);
    _showMapLabel(true);

    if (_selectedLigne) {
      await _snapAndFill(lat, lon, _selectedLigne);
    } else {
      _showGeoStatus('📍 Position capturée · sélectionne une ligne', 'geo-ok');
    }

    if (btn) btn.textContent = '✓ GPS';

  } catch (err) {
    _geolocData = null;
    let msg = 'GPS indisponible.';
    if (err instanceof GeolocError) msg = err.message;
    else if (err.code === 1) msg = 'GPS refusé. Active la localisation dans Réglages.';
    else if (err.code === 2) msg = 'Position indisponible.';
    else if (err.code === 3) msg = 'Délai GPS dépassé.';
    _showGeoStatus(`⚠️ ${msg}`, 'geo-err');
    if (btn) { btn.disabled = false; btn.textContent = '📍 GPS'; }
  } finally {
    _geolocPending = false;
    _updateSendBtn();
  }
}

// ── Grille hiérarchisée (CHG-2) ───────────────────────────

function _buildLigneGrid() {
  const grid = document.getElementById('ligne-grid');
  if (!grid) return;

  let favs = [];
  try { favs = JSON.parse(localStorage.getItem('xetu_fav_lines') || '[]').slice(0, 3); }
  catch {}

  // Favoris qui ne sont pas déjà dans les prioritaires
  const favExtra = favs.filter(l => !PRIORITY_LINES.includes(l));

  let html = '';

  // ── Section 1 : lignes prioritaires (toujours visibles) ──
  html += `<div class="ligne-section">`;
  html += `<div class="ligne-section-label">Lignes fréquentes</div>`;
  html += `<div class="ligne-chips-row">`;
  PRIORITY_LINES.forEach(l => {
    html += `<button class="ligne-chip ligne-chip--priority${l === _selectedLigne ? ' selected' : ''}" data-ligne="${l}">${l}</button>`;
  });
  html += `</div></div>`;

  // ── Section 2 : favoris personnels (si hors prioritaires) ──
  if (favExtra.length > 0) {
    html += `<div class="ligne-section">`;
    html += `<div class="ligne-section-label">Mes favoris</div>`;
    html += `<div class="ligne-chips-row">`;
    favExtra.forEach(l => {
      html += `<button class="ligne-chip${l === _selectedLigne ? ' selected' : ''}" data-ligne="${l}">${l}</button>`;
    });
    html += `</div></div>`;
  }

  // ── Section 3 : accordéon "Toutes les lignes" ──
  const otherCount = LIGNES_CONNUES.size - PRIORITY_LINES.length;
  html += `<div class="ligne-section">`;
  html += `<button class="btn-all-lines" id="btn-all-lines">
    <span>Toutes les lignes (+${otherCount})</span>
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="chevron-all${_allLinesVisible ? ' rotated' : ''}">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  </button>`;

  if (_allLinesVisible) {
    html += `<div class="ligne-search-wrap">
      <input type="text" id="ligne-search-input" class="ligne-search-input"
             placeholder="Chercher une ligne…" autocomplete="off" maxlength="20">
    </div>`;
    html += `<div class="ligne-chips-row ligne-chips-all" id="all-lines-grid">`;
    _getSortedLines().forEach(l => {
      html += `<button class="ligne-chip${l === _selectedLigne ? ' selected' : ''}" data-ligne="${l}">${l}</button>`;
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
  // Chips de ligne — toutes sections
  grid.querySelectorAll('[data-ligne]').forEach(btn => {
    btn.addEventListener('click', () => {
      grid.querySelectorAll('.ligne-chip').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      _selectLigne(btn.dataset.ligne);
    });
  });

  // Accordéon "Toutes les lignes"
  grid.querySelector('#btn-all-lines')?.addEventListener('click', () => {
    _allLinesVisible = !_allLinesVisible;
    _buildLigneGrid();
    if (_allLinesVisible) {
      setTimeout(() => document.getElementById('ligne-search-input')?.focus(), 50);
    }
  });

  // Recherche dans toutes les lignes
  grid.querySelector('#ligne-search-input')?.addEventListener('input', (e) => {
    const filter  = e.target.value.trim();
    const allGrid = document.getElementById('all-lines-grid');
    if (!allGrid) return;
    const filtered = _getSortedLines(filter);
    allGrid.innerHTML = filtered.map(l =>
      `<button class="ligne-chip${l === _selectedLigne ? ' selected' : ''}" data-ligne="${l}">${l}</button>`
    ).join('');
    allGrid.querySelectorAll('[data-ligne]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.ligne-chip').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        _selectLigne(btn.dataset.ligne);
      });
    });
  });
}

// ── Sélection ligne + envoi immédiat (CHG-3) ─────────────

function _selectLigne(ligne) {
  _selectedLigne = ligne;
  _saveFavoriteLine(ligne);
  _updateSendBtn();

  // Snap GPS sur cette ligne si position déjà connue mais pas encore snappée
  if (_geolocData?.lat && !_geolocData.snapped) {
    _snapAndFill(_geolocData.lat, _geolocData.lon, ligne).then(() => _updateSendBtn());
  }

  // GPS en cours → enregistrer la ligne, attendre max 3s
  if (_geolocPending) {
    _pendingLigne = ligne;
    clearTimeout(_pendingTimer);
    _showGeoStatus('⏳ Localisation GPS en cours…', 'geo-warn');
    _pendingTimer = setTimeout(() => {
      // Timeout 3s : GPS trop lent, envoyer sans position précise
      _pendingLigne = null;
      _pendingTimer = null;
      _handleSend(_onSuccessRef);
    }, 3000);
    return;
  }

  // GPS déjà prêt + arrêt connu → envoi immédiat
  const arret = document.getElementById('arret-input')?.value.trim() || '';
  if (_geolocData?.lat && (_geolocData.snapped || arret.length >= 2)) {
    _handleSend(_onSuccessRef);
  }
}

// ── Snap sur arrêt ────────────────────────────────────────

async function _snapToStop(lat, lon, ligne) {
  const routes = await _loadRoutes();
  const key      = String(ligne).toUpperCase();
  const lineData = routes[key] || routes[String(ligne)];
  if (!lineData) return { snapped: false };

  const stops = lineData.arrets || lineData.stops || [];
  let best = null, bestDist = Infinity;
  for (const s of stops) {
    if (!s.lat || !s.lon) continue;
    const d = _haversine(lat, lon, s.lat, s.lon);
    if (d < bestDist) { bestDist = d; best = s.nom || s.name || null; }
  }
  const dist = Math.round(bestDist);
  return bestDist <= 800 ? { snapped: true, name: best, dist } : { snapped: false, dist };
}

let _routesCache = null;
async function _loadRoutes() {
  if (_routesCache) return _routesCache;
  try {
    const r = await fetch('./data/routes_geometry_v13_fixed2.json');
    const j = await r.json();
    _routesCache = j.lignes || j.routes || {};
  } catch { _routesCache = {}; }
  return _routesCache;
}

function _haversine(a, b, c, d) {
  const R = 6371000, p1 = a * Math.PI / 180, p2 = c * Math.PI / 180;
  const dp = (c - a) * Math.PI / 180, dl = (d - b) * Math.PI / 180;
  const x  = Math.sin(dp/2)**2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

// ── Helpers UI ────────────────────────────────────────────

function _showGpsSpinner(show) {
  const spinner = document.getElementById('gps-spinner');
  if (spinner) spinner.hidden = !show;
  const label = document.getElementById('signal-map-label');
  if (label && show) {
    label.innerHTML = `<span class="pos-dot pos-dot--locating"></span> Localisation en cours…`;
  }
}

function _showMapLabel(active) {
  const dot   = document.getElementById('signal-pos-dot');
  const label = document.getElementById('signal-map-label');
  if (dot)   dot.className = `pos-dot ${active ? 'pos-dot--active' : 'pos-dot--wait'}`;
  if (label && active) {
    label.innerHTML = `<span class="pos-dot pos-dot--active"></span> Ta position GPS`;
  }
}

function _showGeoStatus(text, cls) {
  const el = document.getElementById('geoloc-status');
  if (!el) return;
  el.textContent = text;
  el.className   = `geoloc-status ${cls}`;
  el.hidden      = false;
}

// ── Bouton envoyer ────────────────────────────────────────

function _updateSendBtn() {
  const arret  = document.getElementById('arret-input')?.value.trim() || '';
  const hasGps = !!(_geolocData?.lat);
  const ok     = !!_selectedLigne && (arret.length >= 2 || hasGps);
  const btn    = document.getElementById('btn-send');
  const hint   = document.getElementById('send-hint');

  if (btn) {
    btn.disabled = !ok;
    btn.classList.toggle('btn-send--pulse', ok);
  }

  if (hint) {
    if (_geolocPending && !_selectedLigne) {
      hint.textContent = '⏳ GPS en cours… sélectionne une ligne';
    } else if (!_selectedLigne) {
      hint.textContent = 'Sélectionne une ligne';
    } else if (!ok) {
      hint.textContent = 'Indique l\'arrêt ou attends le GPS';
    } else if (hasGps && _geolocData?.nearest_stop) {
      hint.textContent = `📍 ${_geolocData.nearest_stop}`;
    } else if (hasGps) {
      hint.textContent = '📍 Position GPS sera envoyée';
    } else {
      hint.textContent = 'Prêt à envoyer';
    }
  }
}

// ── Qualité optionnelle (CHG-4 : collapse/expand) ─────────

function _initQualityTags() {
  document.getElementById('btn-quality-toggle')?.addEventListener('click', () => {
    const panel = document.getElementById('quality-panel');
    const btn   = document.getElementById('btn-quality-toggle');
    if (!panel) return;
    const isOpen = !panel.hidden;
    panel.hidden = isOpen;
    if (btn) btn.textContent = isOpen
      ? '＋ Ajouter une observation (optionnel)'
      : '－ Masquer les observations';
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

  const btn = document.getElementById('btn-send');
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
      method: 'POST', headers: { 'Content-Type': 'application/json' },
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
  _selectedLigne   = null;
  _selectedQual    = null;
  _geolocData      = null;
  _geolocPending   = false;
  _pendingLigne    = null;
  _allLinesVisible = false;
  clearTimeout(_pendingTimer);
  _pendingTimer = null;

  const arretInput = document.getElementById('arret-input');
  if (arretInput) arretInput.value = '';
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
  const dot   = document.getElementById('signal-pos-dot');
  const label = document.getElementById('signal-map-label');
  if (dot)   dot.className = 'pos-dot pos-dot--wait';
  if (label) label.innerHTML = `<span class="pos-dot pos-dot--wait"></span> Position en attente`;
  _buildLigneGrid();
  _updateSendBtn();
}

// ── Favoris ───────────────────────────────────────────────

function _saveFavoriteLine(ligne) {
  try {
    const raw  = localStorage.getItem('xetu_fav_lines') || '[]';
    const favs = JSON.parse(raw);
    if (!favs.includes(ligne)) {
      const newFavs = [ligne, ...favs].slice(0, 3);
      localStorage.setItem('xetu_fav_lines', JSON.stringify(newFavs));
      store.set('favLines', newFavs);
    }
  } catch {}
}

// ── Events ────────────────────────────────────────────────

function _attachEvents(onSuccess) {
  document.getElementById('btn-gps')?.addEventListener('click', _handleGPS);
  document.getElementById('arret-input')?.addEventListener('input', _updateSendBtn);
  document.getElementById('btn-send')?.addEventListener('click', () => _handleSend(onSuccess));
  _initQualityTags();
}