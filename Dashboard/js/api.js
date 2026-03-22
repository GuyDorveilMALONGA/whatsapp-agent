/**
 * js/api.js — V1.2 App Passager
 *
 * CHG-1 (FIX B1) : _mapBuses() calcule traceStartIdx
 *   Snap du point GPS du signalement (b.lat, b.lon) sur le segment
 *   le plus proche du tracé GTFS via projection orthogonale.
 *   home.js _startAnim() utilise bus.traceStartIdx ?? 0 comme point
 *   de départ — il était toujours undefined avant ce fix.
 *   Tracés GTFS L1 et L4 embarqués ici (même données que home.js,
 *   dupliqués pour éviter un import circulaire).
 *   Lignes sans tracé GTFS → traceStartIdx = 0 (comportement inchangé).
 *
 * V1.1 : routes_geometry_v13_fixed2.json (98 corrections + coupes boucles OSRM)
 */

import { API_BASE, LIGNE_NAMES } from './constants.js';
import { safeFetch } from './utils.js';

// ── Cache routes v13 ──────────────────────────────────────
let _routesCache = null;

// ── Tracés GTFS L1 + L4 pour calcul traceStartIdx ────────
// Dupliqués depuis home.js — à synchroniser si home.js change ses tracés.
const _GTFS_TRACES = {
  '1': [
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
  '4': [
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
};

/**
 * CHG-1 : Snap d'un point GPS sur le segment le plus proche d'un tracé.
 * Projection orthogonale sur chaque segment [a, b] — plus précis qu'un
 * simple plus proche voisin aux angles du tracé.
 * Distance euclidienne au carré (pas de sqrt — assez précis sur ~12km).
 *
 * @param {number} lat
 * @param {number} lon
 * @param {Array<[number, number]>} trace
 * @returns {number} index i tel que le point snappé est entre trace[i] et trace[i+1]
 */
function _snapToTrace(lat, lon, trace) {
  if (!trace || trace.length < 2) return 0;

  let bestIdx  = 0;
  let bestDist = Infinity;

  for (let i = 0; i < trace.length - 1; i++) {
    const [alat, alon] = trace[i];
    const [blat, blon] = trace[i + 1];

    const abLat   = blat - alat;
    const abLon   = blon - alon;
    const abLenSq = abLat * abLat + abLon * abLon;

    // Paramètre t ∈ [0, 1] de la projection de (lat, lon) sur [a, b]
    let t = 0;
    if (abLenSq > 0) {
      t = ((lat - alat) * abLat + (lon - alon) * abLon) / abLenSq;
      t = Math.max(0, Math.min(1, t));
    }

    const closestLat = alat + t * abLat;
    const closestLon = alon + t * abLon;
    const dist = (lat - closestLat) ** 2 + (lon - closestLon) ** 2;

    if (dist < bestDist) {
      bestDist = dist;
      bestIdx  = i;
    }
  }

  return bestIdx;
}

// ── Mapping Railway → App ─────────────────────────────────

let _busIdCounter = 1;
const _busIdMap   = {};

function _mapBuses(rawBuses) {
  return rawBuses
    .filter(b => b.lat && b.lon)
    .map(b => {
      if (!_busIdMap[b.ligne]) _busIdMap[b.ligne] = _busIdCounter++;

      // CHG-1 : snap sur le tracé GTFS si disponible pour cette ligne
      const trace         = _GTFS_TRACES[String(b.ligne)];
      const traceStartIdx = trace
        ? _snapToTrace(b.lat, b.lon, trace)
        : 0;

      return {
        id:             _busIdMap[b.ligne],
        ligne:          b.ligne,
        name:           LIGNE_NAMES[b.ligne] || `Ligne ${b.ligne}`,
        position:       b.arret_estime || b.arret_signale || '—',
        lat:            b.lat,
        lng:            b.lon,
        minutes_ago:    Math.round(b.minutes_depuis_signalement || 0),
        traceStartIdx,
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