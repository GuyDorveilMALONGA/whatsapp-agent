/**
 * js/geoloc.js — V1.0
 * Géolocalisation passager pour signalement GPS.
 *
 * Responsabilités :
 *   - Capturer la position GPS du navigateur
 *   - Trouver l'arrêt le plus proche d'une ligne donnée
 *     (distance haversine sur les stops de routes_geometry_v13.json)
 *   - Retourner { lat, lon, nearest_stop, distance_m }
 *
 * Aucune dépendance externe. Pas de DOM ici.
 */

import { loadRoutes } from './api.js';

// ── Options géoloc ────────────────────────────────────────

const GEOLOC_OPTIONS = {
  enableHighAccuracy: true,
  timeout:            8000,
  maximumAge:         30000,   // accepter une position vieille de 30s max
};

// Rayon max pour considérer un arrêt "proche" (en mètres)
// Au-delà, on envoie les coords brutes sans nom d'arrêt
const MAX_SNAP_DISTANCE_M = 800;

// ── API publique ──────────────────────────────────────────

/**
 * Demande la position GPS et trouve l'arrêt le plus proche
 * sur la ligne spécifiée.
 *
 * @param {string} ligne  — identifiant ligne (ex: "4", "15", "TAF TAF")
 * @returns {Promise<{
 *   lat: number,
 *   lon: number,
 *   nearest_stop: string|null,
 *   distance_m: number|null,
 *   snapped: boolean,
 * }>}
 */
export async function captureAndSnap(ligne) {
  const { lat, lon } = await _getCurrentPosition();
  const snap = await _nearestStop(lat, lon, ligne);
  return { lat, lon, ...snap };
}

/**
 * Capture uniquement la position GPS, sans snap.
 * @returns {Promise<{ lat: number, lon: number }>}
 */
export async function capturePosition() {
  return _getCurrentPosition();
}

/**
 * Trouve l'arrêt le plus proche d'un point GPS sur une ligne.
 * Peut être appelé séparément si on a déjà les coords.
 *
 * @param {number} lat
 * @param {number} lon
 * @param {string} ligne
 * @returns {Promise<{ nearest_stop: string|null, distance_m: number|null, snapped: boolean }>}
 */
export async function nearestStop(lat, lon, ligne) {
  return _nearestStop(lat, lon, ligne);
}

// ── Géolocalisation ───────────────────────────────────────

function _getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new GeolocError('NOT_SUPPORTED', 'Géolocalisation non disponible sur cet appareil.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      (err) => reject(_mapGeolocError(err)),
      GEOLOC_OPTIONS,
    );
  });
}

function _mapGeolocError(err) {
  switch (err.code) {
    case 1: return new GeolocError('DENIED',    'Accès à la position refusé. Autorise la géolocalisation dans les réglages.');
    case 2: return new GeolocError('UNAVAILABLE','Position indisponible. Vérifie que le GPS est activé.');
    case 3: return new GeolocError('TIMEOUT',   'Délai dépassé pour obtenir la position. Réessaie.');
    default: return new GeolocError('UNKNOWN',  'Erreur géolocalisation inconnue.');
  }
}

export class GeolocError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
    this.name = 'GeolocError';
  }
}

// ── Snap sur arrêt ────────────────────────────────────────

async function _nearestStop(lat, lon, ligne) {
  const empty = { nearest_stop: null, distance_m: null, snapped: false };

  if (!ligne) return empty;

  let routes;
  try {
    routes = await loadRoutes();
  } catch {
    return empty;
  }

  const key      = String(ligne).toUpperCase();
  const lineData = routes[key] || routes[String(ligne)];
  if (!lineData) return empty;

  // Supports both formats: stops as strings or as objects {nom, lat, lon}
  const stops = lineData.stops || lineData.arrets || [];
  if (!stops.length) return empty;

  let bestName = null;
  let bestDist = Infinity;

  for (const stop of stops) {
    // Format objet v13 : { nom, lat, lon, ... }
    const stopLat = stop.lat ?? stop.latitude;
    const stopLon = stop.lon ?? stop.longitude ?? stop.lng;
    const stopNom = stop.nom ?? stop.name ?? (typeof stop === 'string' ? stop : null);

    if (!stopLat || !stopLon || !stopNom) continue;

    const d = _haversine(lat, lon, stopLat, stopLon);
    if (d < bestDist) {
      bestDist = d;
      bestName = stopNom;
    }
  }

  if (bestName === null) return empty;

  const snapped = bestDist <= MAX_SNAP_DISTANCE_M;
  return {
    nearest_stop: snapped ? bestName : null,
    distance_m:   Math.round(bestDist),
    snapped,
  };
}

// ── Haversine ─────────────────────────────────────────────

function _haversine(lat1, lon1, lat2, lon2) {
  const R    = 6371000;
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const dphi = ((lat2 - lat1) * Math.PI) / 180;
  const dlam = ((lon2 - lon1) * Math.PI) / 180;
  const a    = Math.sin(dphi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dlam / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
