/**
 * js/api.js
 * Couche données — fetch Railway + mapping + fallback mock.
 * Dépend de : constants.js, utils.js
 *
 * V6.0 — Migration routes_geometry_v13.json
 *   - loadRoutes() : charge routes_geometry_v13.json (77 lignes · 3129 arrêts)
 *   - Accès via json.routes (structure v13) au lieu de json.routes (inchangé)
 *   - Cache mémoire maintenu
 */

import { API_BASE, LIGNE_NAMES } from './constants.js';
import { safeFetch } from './utils.js';

// ── DONNÉES MOCK (fallback si Railway down) ───────────────

const MOCK_BUSES = [
  { id:1, ligne:'15',      position:'Liberté 6',    lat:14.7167, lng:-17.4677, reporter:'M. D.',    minutes_ago:2,  name:'Parcelles → Plateau' },
  { id:2, ligne:'8',       position:'Sandaga',       lat:14.6847, lng:-17.4395, reporter:'F. S.',    minutes_ago:5,  name:'Pikine → Palais' },
  { id:3, ligne:'4',       position:'Colobane',      lat:14.6921, lng:-17.4512, reporter:'I. K.',    minutes_ago:8,  name:'HLM → Terminus Leclerc' },
  { id:4, ligne:'232',     position:'Grand Yoff',    lat:14.7312, lng:-17.4589, reporter:'A. B.',    minutes_ago:3,  name:'Guédiawaye → Plateau' },
  { id:5, ligne:'7',       position:'UCAD',          lat:14.6934, lng:-17.4659, reporter:'O. N.',    minutes_ago:12, name:'Yoff → Gare Routière' },
  { id:6, ligne:'2',       position:'Petersen',      lat:14.6788, lng:-17.4401, reporter:'R. F.',    minutes_ago:1,  name:'Rufisque → Plateau' },
  { id:7, ligne:'327',     position:"Patte d'Oie",   lat:14.7089, lng:-17.4734, reporter:'C. M.',    minutes_ago:18, name:'Keur Massar → Plateau' },
  { id:8, ligne:'1',       position:"Jet d'eau",     lat:14.7023, lng:-17.4445, reporter:'N. T.',    minutes_ago:6,  name:'Liberté 5 → Terminus Palais' },
  { id:9, ligne:'TAF TAF', position:'Diamniadio',    lat:14.7200, lng:-17.0800, reporter:'B. N.',    minutes_ago:9,  name:'Dakar → AIBD Express' },
];

const MOCK_LEADERBOARD = [
  { rank:1, name:'Mamadou Diallo', zone:'Liberté · Dieuppeul', count:142, badges:['Sentinelle L5','Expert Nord'], avatar:'👨🏿' },
  { rank:2, name:'Fatou Sow',      zone:'Médina · HLM',        count:118, badges:['Queen Médina'],                avatar:'👩🏿' },
  { rank:3, name:'Ibou Konaté',    zone:'Parcelles · Pikine',  count:97,  badges:['Banlieue King'],               avatar:'🧑🏿' },
  { rank:4, name:'Aissatou Ba',    zone:'Grand Yoff · Castor', count:84,  badges:['Régulier'],                    avatar:'👩🏾' },
  { rank:5, name:'Omar Ndiaye',    zone:'Plateau · Centre',    count:71,  badges:['Centrevillain'],               avatar:'👨🏾' },
];

const MOCK_STATS = { signalements_today: 247, contributors: 89 };

// ── ID stable par ligne ───────────────────────────────────
let _busIdCounter = 1;
const _busIdMap   = {};

// ── CACHE routes v13 ──────────────────────────────────────
let _routesCache = null;

// ── MAPPING Railway → Dashboard ──────────────────────────

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
        reporter:    b.signale_par ? `****${b.signale_par}` : 'Anonyme',
        minutes_ago: Math.round(b.minutes_depuis_signalement || 0),
        qualite:     b.au_terminus ? 'au terminus' : null,
      };
    });
}

function _mapLeaderboard(rawLb) {
  return rawLb.map(u => ({
    rank:   u.rang,
    name:   u.pseudo,
    zone:   '—',
    count:  u.nb_signalements,
    badges: [u.badge?.label || 'Nouveau'],
    avatar: ['👨🏿','👩🏿','🧑🏿','👩🏾','👨🏾','👩🏽'][u.rang % 6],
  }));
}

// ── ROUTES V13 ────────────────────────────────────────────

/**
 * Charge routes_geometry_v13.json une seule fois (cache mémoire).
 * Retourne l'objet routes : { "1": { name, stops, geometry, ... }, ... }
 */
export async function loadRoutes() {
  if (_routesCache) return _routesCache;

  try {
    const res = await fetch('./data/routes_geometry_v13.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    _routesCache = json.routes || {};
    console.log(`[Api] routes_geometry_v13 chargé — ${Object.keys(_routesCache).length} lignes`);
  } catch (err) {
    console.warn('[Api] Impossible de charger routes_geometry_v13.json :', err.message);
    _routesCache = {};
  }

  return _routesCache;
}

/**
 * Retourne les données d'une ligne spécifique depuis le cache v13.
 * { stops: [{name, lat, lon, confidence}], geometry: [[lat,lon],...] | null }
 */
export async function getLineData(lineId) {
  const routes = await loadRoutes();
  return routes[String(lineId).toUpperCase()] || null;
}

// ── FONCTIONS PUBLIQUES ───────────────────────────────────

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

export async function fetchAll() {
  const results = await Promise.allSettled([
    fetchBuses(),
    fetchLeaderboard(),
  ]);

  const busData = results[0].status === 'fulfilled'
    ? results[0].value
    : { buses: MOCK_BUSES };

  const lbData = results[1].status === 'fulfilled'
    ? results[1].value
    : { leaderboard: MOCK_LEADERBOARD, stats: { signalements_today: '—', contributors: '—' } };

  if (results[0].status === 'rejected')
    console.warn('[Api] /api/buses erreur:', results[0].reason?.message);
  if (results[1].status === 'rejected')
    console.warn('[Api] /api/leaderboard erreur:', results[1].reason?.message);

  return {
    buses:       busData.buses,
    leaderboard: lbData.leaderboard,
    stats:       lbData.stats,
  };
}