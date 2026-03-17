/**
 * js/signal.js — V2.0 Sprint Final
 * Grille : favoris 3 + bouton + → toutes lignes.
 * Score incrémenté après envoi.
 * Placeholder arrêt corrigé.
 */

import * as store  from './store.js';
import * as Toast  from './toast.js';
import { captureAndSnap, GeolocError } from './geoloc.js';
import { API_BASE, LIGNES_CONNUES, SESSION_PREFIX } from './constants.js';
import { generateUUID } from './utils.js';
import { incrementScore } from './mylines.js';

let _selectedLigne = null;
let _selectedQual  = null;
let _geolocData    = null;
let _mapSignal     = null;
let _userMarker    = null;
let _mapReady      = false;

const SESSION_ID = `${SESSION_PREFIX}${generateUUID()}`;

// ── Init ──────────────────────────────────────────────────

export function initSignal({ onSuccess }) {
  _buildLigneGrid();
  _attachEvents(onSuccess);
  store.subscribe('favLines', () => _buildLigneGrid());

  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !_mapReady) {
      _initMap(); _mapReady = true; observer.disconnect();
    }
  });
  const screen = document.getElementById('screen-signal');
  if (screen) observer.observe(screen);
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

// ── Grille : 3 favoris + bouton + ─────────────────────────

function _buildLigneGrid() {
  const grid = document.getElementById('ligne-grid');
  if (!grid) return;

  let favs = [];
  try { favs = JSON.parse(localStorage.getItem('xetu_fav_lines') || '[]').slice(0, 3); }
  catch {}
  if (!favs.length) favs = ['4', '15', '7'];

  grid.innerHTML = favs.map(l =>
    `<button class="ligne-chip${l === _selectedLigne ? ' selected' : ''}" data-ligne="${l}">${l}</button>`
  ).join('') + `<button class="ligne-chip ligne-chip--plus" data-action="more">+</button>`;

  _attachGridEvents(grid);
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
    `<button class="ligne-chip${l === _selectedLigne ? ' selected' : ''}" data-ligne="${l}">${l}</button>`
  ).join('');
  _attachGridEvents(grid);
}

function _attachGridEvents(grid) {
  grid.querySelectorAll('[data-ligne]').forEach(btn => {
    btn.addEventListener('click', () => {
      grid.querySelectorAll('.ligne-chip').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      _selectedLigne = btn.dataset.ligne;
      _saveFavoriteLine(_selectedLigne);
      _updateSendBtn();
    });
  });
  grid.querySelector('[data-action="more"]')?.addEventListener('click', _showAllLines);
}

// ── GPS ───────────────────────────────────────────────────

async function _handleGPS() {
  const btn    = document.getElementById('btn-gps');
  const status = document.getElementById('geoloc-status');
  if (!btn || !status) return;
  btn.disabled = true; btn.textContent = '⏳';
  _geolocData = null; status.hidden = true;

  try {
    const result = await captureAndSnap(_selectedLigne || null);
    _geolocData = result;
    _updateUserMarker(result.lat, result.lon);

    const dot   = document.getElementById('signal-pos-dot');
    const label = document.getElementById('signal-map-label');
    if (dot)   dot.className = 'pos-dot pos-dot--active';
    if (label) label.innerHTML = `<span class="pos-dot pos-dot--active"></span> Ta position GPS`;

    if (result.snapped && result.nearest_stop) {
      document.getElementById('arret-input').value = result.nearest_stop;
      _showGeoStatus(`📍 ${result.nearest_stop} · à ${result.distance_m} m`, 'geo-ok');
      btn.textContent = '✓ GPS';
    } else {
      _showGeoStatus(`📍 Position capturée · saisis l'arrêt`, 'geo-warn');
      btn.textContent = '📍 GPS'; btn.disabled = false;
    }
    _updateSendBtn();
  } catch (err) {
    _geolocData = null;
    const msg = err instanceof GeolocError ? err.message : 'GPS indisponible.';
    _showGeoStatus(`⚠️ ${msg}`, 'geo-err');
    btn.disabled = false; btn.textContent = '📍 GPS';
  }
}

function _showGeoStatus(text, cls) {
  const el = document.getElementById('geoloc-status');
  if (!el) return;
  el.textContent = text; el.className = `geoloc-status ${cls}`; el.hidden = false;
}

// ── Qualité ───────────────────────────────────────────────

function _initQualityTags() {
  document.querySelectorAll('.quality-tag').forEach(tag => {
    tag.addEventListener('click', () => {
      const isSel = tag.classList.contains('selected');
      document.querySelectorAll('.quality-tag').forEach(t => t.classList.remove('selected'));
      _selectedQual = isSel ? null : tag.dataset.val;
      if (!isSel) tag.classList.add('selected');
    });
  });
}

// ── Send btn ──────────────────────────────────────────────

function _updateSendBtn() {
  const arret = document.getElementById('arret-input')?.value.trim() || '';
  const ok    = !!_selectedLigne && arret.length >= 2;
  const btn   = document.getElementById('btn-send');
  const hint  = document.getElementById('send-hint');
  if (btn)  btn.disabled = !ok;
  if (hint) hint.textContent = !_selectedLigne ? 'Sélectionne une ligne pour continuer'
    : arret.length < 2 ? 'Indique l\'arrêt où tu vois le bus'
    : _geolocData ? '📍 Position GPS sera envoyée' : 'Signalement sans GPS';
}

// ── Envoi ─────────────────────────────────────────────────

async function _handleSend(onSuccess) {
  const arret = document.getElementById('arret-input')?.value.trim() || '';
  if (!_selectedLigne || arret.length < 2) return;

  const btn = document.getElementById('btn-send');
  if (btn) { btn.disabled = true; btn.textContent = 'Envoi en cours…'; }

  const payload = {
    ligne: _selectedLigne, arret,
    source: _geolocData ? 'web_geoloc' : 'web_dashboard',
    client_ts: new Date().toISOString(), session_id: SESSION_ID,
  };
  if (_selectedQual)    payload.observation = _selectedQual;
  if (_geolocData?.lat) { payload.lat = _geolocData.lat; payload.lon = _geolocData.lon; }

  try {
    const res = await fetch(`${API_BASE}/api/report`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.status === 201 || res.status === 200) {
      Toast.success(`✅ Bus ${_selectedLigne} signalé à ${arret} !`);
      incrementScore(); // incrémenter le score
      _reset(); onSuccess?.();
    } else if (res.status === 429) {
      Toast.error('⏱ Trop de signalements. Réessaie dans quelques min.');
    } else { throw new Error(`HTTP ${res.status}`); }
  } catch (err) {
    Toast.error('❌ Envoi échoué. Vérifie ta connexion.');
    console.error('[Signal]', err);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Envoyer le signalement'; }
    _updateSendBtn();
  }
}

// ── Reset ─────────────────────────────────────────────────

function _reset() {
  _selectedLigne = null; _selectedQual = null; _geolocData = null;
  const arretInput = document.getElementById('arret-input');
  if (arretInput) arretInput.value = '';
  const geoStatus = document.getElementById('geoloc-status');
  if (geoStatus) geoStatus.hidden = true;
  const gpsBtn = document.getElementById('btn-gps');
  if (gpsBtn) { gpsBtn.disabled = false; gpsBtn.textContent = '📍 GPS'; }
  document.querySelectorAll('.quality-tag').forEach(b => b.classList.remove('selected'));
  if (_mapSignal && _userMarker) { _mapSignal.removeLayer(_userMarker); _userMarker = null; }
  const dot   = document.getElementById('signal-pos-dot');
  const label = document.getElementById('signal-map-label');
  if (dot)   dot.className = 'pos-dot pos-dot--wait';
  if (label) label.innerHTML = `<span class="pos-dot pos-dot--wait"></span> Position en attente`;
  _buildLigneGrid(); _updateSendBtn();
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
