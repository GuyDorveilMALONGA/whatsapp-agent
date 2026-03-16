/**
 * js/home.js — V1.0
 * Écran Accueil : carte bus, liste bus actifs, top signaleurs, toggle.
 */

import * as store from './store.js';
import { getAgeClass, formatAgeShort, getRankSymbol, getRankClass } from './utils.js';

const AVATARS = ['👨🏿','👩🏿','🧑🏿','👩🏾','👨🏾','👩🏽'];

let _map         = null;
let _busMarkers  = {};
let _activeCol   = 'buses';

// ── Init ──────────────────────────────────────────────────

export function initHome({ onSeeBus }) {
  _initMap();
  _initTabs();
  _initSeeBus(onSeeBus);
  _subscribeStore();
}

// ── Carte ─────────────────────────────────────────────────

function _initMap() {
  _map = L.map('map-home', { zoomControl: false, attributionControl: false })
    .setView([14.716, -17.467], 13);

  L.tileLayer(
    'https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png',
    { maxZoom: 19 }
  ).addTo(_map);
}

function _updateMarkers(buses) {
  if (!_map) return;

  Object.values(_busMarkers).forEach(m => _map.removeLayer(m));
  _busMarkers = {};

  buses.forEach(b => {
    if (!b.lat || !b.lng) return;
    const color = b.minutes_ago <= 5 ? '#00D67F'
                : b.minutes_ago <= 15 ? '#FFD166'
                : '#FF4757';

    const icon = L.divIcon({
      html: `<div style="
        background:${color};color:#fff;
        font-family:'Syne',sans-serif;font-size:10px;font-weight:700;
        padding:3px 7px;border-radius:6px;border:2px solid #fff;
        box-shadow:0 2px 8px rgba(0,0,0,0.5);white-space:nowrap">
        ${b.ligne}
      </div>`,
      iconAnchor: [20, 14],
      className: '',
    });

    _busMarkers[b.id] = L.marker([b.lat, b.lng], { icon })
      .bindPopup(`<b>Bus ${b.ligne}</b><br>${b.position}<br>
        <span style="color:${color}">${formatAgeShort(b.minutes_ago)}</span>`)
      .addTo(_map);
  });

  if (buses.length > 0) {
    const lats = buses.filter(b => b.lat).map(b => b.lat);
    const lngs = buses.filter(b => b.lng).map(b => b.lng);
    if (lats.length) {
      _map.setView([
        lats.reduce((a, b) => a + b, 0) / lats.length,
        lngs.reduce((a, b) => a + b, 0) / lngs.length,
      ], 13);
    }
  }
}

// ── Tabs bus / top ────────────────────────────────────────

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
  const busCols = document.querySelectorAll('.home-col');
  busCols.forEach(c => c.classList.remove('active'));

  if (_activeCol === 'buses') {
    document.getElementById('col-buses').classList.add('active');
  } else {
    document.getElementById('col-top').classList.add('active');
  }
}

// ── Rendu bus ─────────────────────────────────────────────

function _renderBuses(buses) {
  const el = document.getElementById('col-buses');
  if (!el) return;

  if (!buses.length) {
    el.innerHTML = `<div class="empty-state">
      <div class="empty-icon">🚌</div>
      <div class="empty-text">Aucun bus actif.<br>Sois le premier à signaler !</div>
    </div>`;
    return;
  }

  el.innerHTML = buses.map((b, i) => `
    <div class="bus-card anim-up" style="animation-delay:${i * 0.04}s">
      <div class="bus-card-header">
        <span class="bus-badge">Bus ${b.ligne}</span>
        <span class="bus-name">${b.name}</span>
        <span class="bus-age ${getAgeClass(b.minutes_ago)}">${formatAgeShort(b.minutes_ago)}</span>
      </div>
      <div class="bus-position">📍 ${b.position}</div>
    </div>
  `).join('');
}

// ── Rendu leaderboard ─────────────────────────────────────

function _renderTop(leaderboard) {
  const el = document.getElementById('col-top');
  if (!el) return;

  if (!leaderboard.length) {
    el.innerHTML = `<div class="empty-state">
      <div class="empty-icon">🏆</div>
      <div class="empty-text">Pas encore de données.</div>
    </div>`;
    return;
  }

  el.innerHTML = leaderboard.slice(0, 10).map((u, i) => `
    <div class="lb-card anim-up" style="animation-delay:${i * 0.04}s">
      <span class="lb-rank ${getRankClass(u.rank)}">${getRankSymbol(u.rank)}</span>
      <span class="lb-avatar">${AVATARS[i % AVATARS.length]}</span>
      <div class="lb-info">
        <div class="lb-name">${u.name || 'Anonyme'}</div>
        <div class="lb-badge">${u.badge || 'Contributeur'}</div>
      </div>
      <span class="lb-count">${u.count || 0}</span>
    </div>
  `).join('');
}

// ── Bouton "Je vois un bus ici" ───────────────────────────

function _initSeeBus(onSeeBus) {
  const btn = document.getElementById('btn-see-bus');
  if (btn) btn.addEventListener('click', onSeeBus);
}

// ── Store subscriptions ───────────────────────────────────

function _subscribeStore() {
  store.subscribe('buses', (buses) => {
    _updateMarkers(buses);
    _renderBuses(buses);
    _renderCols();
  });

  store.subscribe('leaderboard', (lb) => {
    _renderTop(lb);
  });
}
