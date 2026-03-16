/**
 * js/signal.js — V1.0
 * Écran Signalement : carte GPS, grille lignes, arrêt, qualité, envoi.
 */

import * as store  from './store.js';
import * as Toast  from './toast.js';
import { captureAndSnap, GeolocError } from './geoloc.js';
import { loadRoutes } from './api.js';
import { API_BASE, LIGNES_CONNUES, LIGNE_NAMES, SESSION_PREFIX } from './constants.js';
import { generateUUID } from './utils.js';

// ── Lignes affichées dans la grille (top 11 + Autres) ────
const LIGNES_GRID = ['1','2','4','5','6','7','8','9','10','11','13','15','16A','TAF TAF','TO1'];

// ── State ────────────────────────────────────────────────
let _selectedLigne = null;
let _selectedQual  = null;
let _geolocData    = null;
let _mapSignal     = null;
let _userMarker    = null;
let _mapReady      = false;

const SESSION_ID = `${SESSION_PREFIX}${generateUUID()}`;

// ── Init ─────────────────────────────────────────────────

export function initSignal({ onSuccess }) {
  _buildLigneGrid();
  _attachEvents(onSuccess);

  // Initialiser la carte au premier affichage de l'écran
  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !_mapReady) {
      _initMap();
      _mapReady = true;
      observer.disconnect();
    }
  });
  const screen = document.getElementById('screen-signal');
  if (screen) observer.observe(screen);
}

// ── Carte mini ────────────────────────────────────────────

function _initMap() {
  _mapSignal = L.map('map-signal', { zoomControl: false, attributionControl: false })
    .setView([14.716, -17.467], 14);

  L.tileLayer(
    'https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png',
    { maxZoom: 19 }
  ).addTo(_mapSignal);
}

function _updateUserMarker(lat, lon) {
  if (!_mapSignal) return;
  if (_userMarker) _mapSignal.removeLayer(_userMarker);

  const icon = L.divIcon({
    html: `<div style="width:14px;height:14px;border-radius:50%;
      background:#3b82f6;border:3px solid #fff;
      box-shadow:0 2px 8px rgba(59,130,246,0.6)"></div>`,
    iconAnchor: [7, 7],
    className: '',
  });

  _userMarker = L.marker([lat, lon], { icon }).addTo(_mapSignal);
  _mapSignal.setView([lat, lon], 15);
}

// ── Grille lignes ─────────────────────────────────────────

function _buildLigneGrid() {
  const grid = document.getElementById('ligne-grid');
  if (!grid) return;

  const chips = LIGNES_GRID.slice(0, 11).map(l =>
    `<button class="ligne-chip" data-ligne="${l}">${l}</button>`
  ).join('');

  grid.innerHTML = chips +
    `<button class="ligne-chip" data-action="more" style="font-size:11px;font-weight:500">Autres</button>`;

  grid.querySelectorAll('[data-ligne]').forEach(btn => {
    btn.addEventListener('click', () => {
      grid.querySelectorAll('.ligne-chip').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      _selectedLigne = btn.dataset.ligne;
      // Sauvegarder dans les lignes favorites
      _saveFavoriteLine(_selectedLigne);
      _updateSendBtn();
    });
  });

  grid.querySelector('[data-action="more"]')?.addEventListener('click', _showAllLines);
}

function _showAllLines() {
  const grid = document.getElementById('ligne-grid');
  if (!grid) return;

  const all = [...LIGNES_CONNUES].sort((a, b) => {
    const na = parseFloat(a), nb = parseFloat(b);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return a.localeCompare(b);
  });

  grid.innerHTML = all.map(l =>
    `<button class="ligne-chip${l === _selectedLigne ? ' selected' : ''}"
      data-ligne="${l}">${l}</button>`
  ).join('');

  grid.querySelectorAll('[data-ligne]').forEach(btn => {
    btn.addEventListener('click', () => {
      grid.querySelectorAll('.ligne-chip').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      _selectedLigne = btn.dataset.ligne;
      _saveFavoriteLine(_selectedLigne);
      _updateSendBtn();
    });
  });
}

// ── GPS ───────────────────────────────────────────────────

async function _handleGPS() {
  const btn    = document.getElementById('btn-gps');
  const status = document.getElementById('geoloc-status');
  if (!btn || !status) return;

  btn.disabled    = true;
  btn.textContent = '⏳';
  _geolocData     = null;
  status.hidden   = true;

  try {
    const result = await captureAndSnap(_selectedLigne || null);
    _geolocData   = result;

    _updateUserMarker(result.lat, result.lon);

    // Mettre à jour label carte
    const dot   = document.getElementById('signal-pos-dot');
    const label = document.getElementById('signal-map-label');
    if (dot)   { dot.className = 'pos-dot pos-dot--active'; }
    if (label) { label.innerHTML = `<span class="pos-dot pos-dot--active"></span> Ta position GPS`; }

    if (result.snapped && result.nearest_stop) {
      document.getElementById('arret-input').value = result.nearest_stop;
      _showGeoStatus(`📍 ${result.nearest_stop} · à ${result.distance_m} m`, 'geo-ok');
      btn.textContent = '✓ GPS';
    } else if (result.distance_m !== null) {
      _showGeoStatus(`📍 Position capturée · arrêt le plus proche à ${result.distance_m} m`, 'geo-warn');
      btn.textContent = '📍 GPS';
      btn.disabled    = false;
    } else {
      _showGeoStatus('📍 Position capturée · saisis l\'arrêt manuellement', 'geo-warn');
      btn.textContent = '📍 GPS';
      btn.disabled    = false;
    }

    _updateSendBtn();

  } catch (err) {
    _geolocData = null;
    const msg = err instanceof GeolocError ? err.message : 'Impossible d\'obtenir la position.';
    _showGeoStatus(`⚠️ ${msg}`, 'geo-err');
    btn.disabled    = false;
    btn.textContent = '📍 GPS';
  }
}

function _showGeoStatus(text, cls) {
  const el = document.getElementById('geoloc-status');
  if (!el) return;
  el.textContent = text;
  el.className   = `geoloc-status ${cls}`;
  el.hidden      = false;
}

// ── Qualité ───────────────────────────────────────────────

function _initQualityTags() {
  document.querySelectorAll('.quality-tag').forEach(tag => {
    tag.addEventListener('click', () => {
      const isSelected = tag.classList.contains('selected');
      document.querySelectorAll('.quality-tag').forEach(t => t.classList.remove('selected'));
      _selectedQual = isSelected ? null : tag.dataset.val;
      if (!isSelected) tag.classList.add('selected');
    });
  });
}

// ── Bouton envoyer ────────────────────────────────────────

function _updateSendBtn() {
  const arret = document.getElementById('arret-input')?.value.trim() || '';
  const ok    = !!_selectedLigne && arret.length >= 2;

  const btn  = document.getElementById('btn-send');
  const hint = document.getElementById('send-hint');
  if (btn)  btn.disabled    = !ok;
  if (hint) hint.textContent = !_selectedLigne
    ? 'Sélectionne une ligne pour continuer'
    : arret.length < 2
    ? 'Indique l\'arrêt où tu vois le bus'
    : _geolocData
    ? '📍 Position GPS sera envoyée'
    : 'Signalement sans GPS';
}

// ── Envoi ─────────────────────────────────────────────────

async function _handleSend(onSuccess) {
  const arret = document.getElementById('arret-input')?.value.trim() || '';
  if (!_selectedLigne || arret.length < 2) return;

  const btn = document.getElementById('btn-send');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Envoi en cours…'; }

  const payload = {
    ligne:      _selectedLigne,
    arret,
    source:     _geolocData ? 'web_geoloc' : 'web_dashboard',
    client_ts:  new Date().toISOString(),
    session_id: SESSION_ID,
  };
  if (_selectedQual)   payload.observation = _selectedQual;
  if (_geolocData?.lat) { payload.lat = _geolocData.lat; payload.lon = _geolocData.lon; }

  try {
    const res = await fetch(`${API_BASE}/api/report`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });

    if (res.status === 201 || res.status === 200) {
      Toast.success(`✅ Bus ${_selectedLigne} signalé à ${arret} !`);
      _reset();
      onSuccess?.();
    } else if (res.status === 429) {
      Toast.error('⏱ Trop de signalements. Réessaie dans quelques min.');
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (err) {
    Toast.error('❌ Envoi échoué. Vérifie ta connexion.');
    console.error('[Signal] Erreur envoi:', err);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '📡 Envoyer le signalement'; }
    _updateSendBtn();
  }
}

// ── Reset formulaire ──────────────────────────────────────

function _reset() {
  _selectedLigne = null;
  _selectedQual  = null;
  _geolocData    = null;

  const arretInput = document.getElementById('arret-input');
  if (arretInput) arretInput.value = '';

  const geoStatus = document.getElementById('geoloc-status');
  if (geoStatus) geoStatus.hidden = true;

  const gpsBtn = document.getElementById('btn-gps');
  if (gpsBtn) { gpsBtn.disabled = false; gpsBtn.textContent = '📍 GPS'; }

  document.querySelectorAll('.ligne-chip').forEach(b => b.classList.remove('selected'));
  document.querySelectorAll('.quality-tag').forEach(b => b.classList.remove('selected'));

  if (_mapSignal && _userMarker) {
    _mapSignal.removeLayer(_userMarker);
    _userMarker = null;
  }

  const dot   = document.getElementById('signal-pos-dot');
  const label = document.getElementById('signal-map-label');
  if (dot)   dot.className = 'pos-dot pos-dot--wait';
  if (label) label.innerHTML = `<span class="pos-dot pos-dot--wait"></span> Position en attente`;

  _updateSendBtn();
}

// ── Favoris localStorage ──────────────────────────────────

function _saveFavoriteLine(ligne) {
  try {
    const raw  = localStorage.getItem('xetu_fav_lines') || '[]';
    const favs = JSON.parse(raw);
    if (!favs.includes(ligne)) {
      favs.unshift(ligne);
      localStorage.setItem('xetu_fav_lines', JSON.stringify(favs.slice(0, 3)));
      // Notifier mylines
      store.set('favLines', favs.slice(0, 3));
    }
  } catch { /* localStorage bloqué */ }
}

// ── Attach events ─────────────────────────────────────────

function _attachEvents(onSuccess) {
  document.getElementById('btn-gps')
    ?.addEventListener('click', _handleGPS);

  document.getElementById('arret-input')
    ?.addEventListener('input', _updateSendBtn);

  document.getElementById('btn-send')
    ?.addEventListener('click', () => _handleSend(onSuccess));

  _initQualityTags();
}
