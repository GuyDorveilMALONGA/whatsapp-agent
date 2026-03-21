/**
 * js/api.js — V1.1 App Passager
 * Adapté depuis api.js V6.1 du dashboard.
 * Retiré : mock data, getLineData(), logique desktop.
 * Conservé : fetchBuses(), fetchLeaderboard(), loadRoutes().
 *
 * V1.1 : routes_geometry_v13_fixed2.json (98 corrections + coupes boucles OSRM)
 */

import { API_BASE, LIGNE_NAMES } from './constants.js';
import { safeFetch } from './utils.js';

// ── Cache routes v13 ──────────────────────────────────────
let _routesCache = null;

// ── Mapping Railway → App ─────────────────────────────────

let _busIdCounter = 1;
const _busIdMap   = {};

function _mapBuses(rawBuses) {
  return rawBuses
    .filter(b => b.lat && b.lon)
    .map(b => {
      if (!_busIdMap[b.ligne]) _busIdMap[b.ligne] = _busIdCounter++;
      return {
        id:          _busIdMap[b.ligne],
        ligne:       b.ligne,
        name:        LIGNE_NAMES[b.ligne] || `Ligne ${b.ligne}`,
        position:    b.arret_estime || b.arret_signale || '—',
        lat:         b.lat,
        lng:         b.lon,
        minutes_ago: Math.round(b.minutes_depuis_signalement || 0),
      };
    });
}

function _mapLeaderboard(rawLb) {
  return rawLb.map(u => ({
    rank:  u.rang,
    name:  u.pseudo,
    count: u.nb_signalements,
    badge: u.badge?.label || 'Contributeur',
  }));
}

// ── Routes v13 ────────────────────────────────────────────

export async function loadRoutes() {
  if (_routesCache) return _routesCache;
  try {
    const res = await fetch('./data/routes_geometry_v13_fixed2.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    _routesCache = json.lignes || json.routes || {};
    console.log(`[Api] routes_geometry_v13_fixed2 chargé — ${Object.keys(_routesCache).length} lignes`);
  } catch (err) {
    console.warn('[Api] Impossible de charger routes_geometry_v13_fixed2.json :', err.message);
    _routesCache = {};
  }
  return _routesCache;
}

// ── Fetch ─────────────────────────────────────────────────

export async function fetchBuses() {
  const data = await safeFetch(`${API_BASE}/api/buses`);
  return { buses: _mapBuses(data.buses || []) };
}

export async function fetchLeaderboard() {
  const data = await safeFetch(`${API_BASE}/api/leaderboard`);
  return {
    leaderboard: _mapLeaderboard(data.leaderboard || []),
    stats: {
      signalements_today: data.stats?.total_signalements_aujourd_hui ?? '—',
      contributors:       data.stats?.nb_contributeurs               ?? '—',
    },
  };
}