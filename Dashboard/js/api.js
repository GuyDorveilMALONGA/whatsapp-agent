/**
 * js/api.js
 * Couche données — mock + fetch API Railway.
 */

const Config = {
  API_BASE:    'https://web-production-ccab8.up.railway.app',
  WA_NUMBER:   '221XXXXXXXXX',
  USE_MOCK:    false,           // ← Railway est prêt
  REFRESH_SEC: 30,
};

// ── DONNÉES MOCK (fallback si Railway down) ───────────────

const MOCK_BUSES = [
  { id:1, ligne:'15',  position:'Liberté 6',    lat:14.7167, lng:-17.4677, reporter:'Mamadou D.',  minutes_ago:2,  name:'Parcelles → Plateau' },
  { id:2, ligne:'8',   position:'Sandaga',       lat:14.6847, lng:-17.4395, reporter:'Fatou S.',    minutes_ago:5,  name:'Pikine → Palais' },
  { id:3, ligne:'4',   position:'Colobane',      lat:14.6921, lng:-17.4512, reporter:'Ibrahima K.', minutes_ago:8,  name:'HLM → Terminus Leclerc' },
  { id:4, ligne:'232', position:'Grand Yoff',    lat:14.7312, lng:-17.4589, reporter:'Aissatou B.', minutes_ago:3,  name:'Guédiawaye → Plateau' },
  { id:5, ligne:'7',   position:'UCAD',          lat:14.6934, lng:-17.4659, reporter:'Omar N.',     minutes_ago:12, name:'Yoff → Gare Routière' },
  { id:6, ligne:'2',   position:'Petersen',      lat:14.6788, lng:-17.4401, reporter:'Rokhaya F.',  minutes_ago:1,  name:'Rufisque → Plateau' },
  { id:7, ligne:'327', position:"Patte d'Oie",   lat:14.7089, lng:-17.4734, reporter:'Cheikh M.',   minutes_ago:18, name:'Keur Massar → Plateau' },
  { id:8, ligne:'1',   position:"Jet d'eau",     lat:14.7023, lng:-17.4445, reporter:'Ndeye T.',    minutes_ago:6,  name:'Liberté 5 → Terminus Palais' },
];

const MOCK_LEADERBOARD = [
  { rank:1, name:'Mamadou Diallo', zone:'Liberté · Dieuppeul', count:142, badges:['Sentinelle L5','Expert Nord'], avatar:'👨🏿' },
  { rank:2, name:'Fatou Sow',      zone:'Médina · HLM',        count:118, badges:['Queen Médina'],                avatar:'👩🏿' },
  { rank:3, name:'Ibou Konaté',    zone:'Parcelles · Pikine',  count:97,  badges:['Banlieue King'],               avatar:'🧑🏿' },
  { rank:4, name:'Aissatou Ba',    zone:'Grand Yoff · Castor', count:84,  badges:['Régulier'],                    avatar:'👩🏾' },
  { rank:5, name:'Omar Ndiaye',    zone:'Plateau · Centre',    count:71,  badges:['Centrevillain'],               avatar:'👨🏾' },
  { rank:6, name:'Rokhaya Fall',   zone:'Rufisque · Thiaroye', count:63,  badges:['Banlieue'],                    avatar:'👩🏿' },
  { rank:7, name:'Cheikh Mbaye',   zone:'Keur Massar',         count:58,  badges:['Est solidaire'],               avatar:'🧑🏾' },
  { rank:8, name:'Ndeye Thiam',    zone:'Yoff · Almadies',     count:47,  badges:['Côtière'],                     avatar:'👩🏽' },
];

const MOCK_STATS = { signalements_today: 247, contributors: 89 };

// ── NOMS DES LIGNES ───────────────────────────────────────

const LIGNE_NAMES = {
  '1':   'Liberté 5 → Terminus Palais',
  '2':   'Rufisque → Plateau',
  '4':   'HLM → Terminus Leclerc',
  '7':   'Yoff → Gare Routière',
  '8':   'Pikine → Palais',
  '15':  'Parcelles → Plateau',
  '26':  'Pikine → Corniche',
  '232': 'Guédiawaye → Plateau',
  '327': 'Keur Massar → Plateau',
};

// ID stable par ligne pour Leaflet
let _busIdCounter = 1;
const _busIdMap = {};

// ── API MODULE ────────────────────────────────────────────

const Api = (() => {

  function _simulateLiveVariation(buses) {
    return buses.map(b => ({
      ...b,
      minutes_ago: Math.max(0, b.minutes_ago + Math.floor(Math.random() * 2 - 0.3)),
    }));
  }

  /**
   * Mappe le format Railway /api/buses → format dashboard
   * Railway retourne : { ligne, arret_estime, lat, lon,
   *   minutes_depuis_signalement, confiance, signale_par, au_terminus }
   */
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
          lng:         b.lon,           // Railway dit "lon", dashboard veut "lng"
          reporter:    b.signale_par ? `****${b.signale_par}` : 'Anonyme',
          minutes_ago: Math.round(b.minutes_depuis_signalement || 0),
          qualite:     b.au_terminus ? 'au terminus' : null,
        };
      });
  }

  /**
   * Mappe le format Railway /api/leaderboard → format dashboard
   * Railway retourne : { rang, pseudo, nb_signalements,
   *   fiabilite_score, badge: { emoji, label } }
   */
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

  async function fetchBuses() {
    if (Config.USE_MOCK) {
      return { buses: _simulateLiveVariation(MOCK_BUSES), stats: MOCK_STATS };
    }
    const res = await fetch(`${Config.API_BASE}/api/buses`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return {
      buses: _mapBuses(data.buses || []),
      stats: {
        signalements_today: data.stats?.signalements_today ?? '—',
        contributors:       data.stats?.contributors       ?? '—',
      },
    };
  }

  async function fetchLeaderboard() {
    if (Config.USE_MOCK) return MOCK_LEADERBOARD;
    const res = await fetch(`${Config.API_BASE}/api/leaderboard`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return _mapLeaderboard(data.leaderboard || []);
  }

  async function fetchAll() {
    try {
      const [busData, leaderboard] = await Promise.all([
        fetchBuses(),
        fetchLeaderboard(),
      ]);
      return { ...busData, leaderboard };
    } catch (err) {
      console.warn('[Api] Erreur Railway, fallback mock:', err.message);
      Config.USE_MOCK = true;
      return {
        buses:       _simulateLiveVariation(MOCK_BUSES),
        stats:       MOCK_STATS,
        leaderboard: MOCK_LEADERBOARD,
      };
    }
  }

  return { fetchAll, fetchBuses, fetchLeaderboard };

})();
