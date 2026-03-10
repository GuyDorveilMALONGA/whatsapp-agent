/**
 * js/api.js
 * Couche données — fetch Railway + mapping + fallback mock.
 * Dépend de : constants.js, utils.js
 */

import { API_BASE, LIGNE_NAMES } from './constants.js';
import { safeFetch } from './utils.js';

// ── DONNÉES MOCK (fallback si Railway down) ───────────────

const MOCK_BUSES = [
  { id:1, ligne:'15',  position:'Liberté 6',    lat:14.7167, lng:-17.4677, reporter:'M. D.',    minutes_ago:2,  name:'Parcelles → Plateau' },
  { id:2, ligne:'8',   position:'Sandaga',       lat:14.6847, lng:-17.4395, reporter:'F. S.',    minutes_ago:5,  name:'Pikine → Palais' },
  { id:3, ligne:'4',   position:'Colobane',      lat:14.6921, lng:-17.4512, reporter:'I. K.',    minutes_ago:8,  name:'HLM → Terminus Leclerc' },
  { id:4, ligne:'232', position:'Grand Yoff',    lat:14.7312, lng:-17.4589, reporter:'A. B.',    minutes_ago:3,  name:'Guédiawaye → Plateau' },
  { id:5, ligne:'7',   position:'UCAD',          lat:14.6934, lng:-17.4659, reporter:'O. N.',    minutes_ago:12, name:'Yoff → Gare Routière' },
  { id:6, ligne:'2',   position:'Petersen',      lat:14.6788, lng:-17.4401, reporter:'R. F.',    minutes_ago:1,  name:'Rufisque → Plateau' },
  { id:7, ligne:'327', position:"Patte d'Oie",   lat:14.7089, lng:-17.4734, reporter:'C. M.',    minutes_ago:18, name:'Keur Massar → Plateau' },
  { id:8, ligne:'1',   position:"Jet d'eau",     lat:14.7023, lng:-17.4445, reporter:'N. T.',    minutes_ago:6,  name:'Liberté 5 → Terminus Palais' },
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
const _busIdMap = {};

// ── MODE MOCK (activé automatiquement si Railway KO) ──────
let _useMock = false;

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
        reporter:    b.signale_par ? `****${b.signale_par.slice(-2)}` : 'Anonyme',
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

// ── FONCTIONS PUBLIQUES ───────────────────────────────────

export async function fetchBuses() {
  if (_useMock) {
    return { buses: MOCK_BUSES, stats: MOCK_STATS };
  }
  const data = await safeFetch(`${API_BASE}/api/buses`);
  return {
    buses: _mapBuses(data.buses || []),
    stats: {
      signalements_today: data.stats?.signalements_today ?? '—',
      contributors:       data.stats?.contributors       ?? '—',
    },
  };
}

export async function fetchLeaderboard() {
  if (_useMock) return MOCK_LEADERBOARD;
  const data = await safeFetch(`${API_BASE}/api/leaderboard`);
  return _mapLeaderboard(data.leaderboard || []);
}

export async function fetchAll() {
  try {
    const [busData, leaderboard] = await Promise.all([
      fetchBuses(),
      fetchLeaderboard(),
    ]);
    return { ...busData, leaderboard };
  } catch (err) {
    console.warn('[Api] Erreur Railway, fallback mock:', err.message || err.code);
    _useMock = true;
    return { buses: MOCK_BUSES, stats: MOCK_STATS, leaderboard: MOCK_LEADERBOARD };
  }
}
