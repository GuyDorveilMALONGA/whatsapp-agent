/**
 * js/api.js
 * Couche données — mock + fetch API Railway.
 * Un seul endroit à modifier quand Railway revient.
 *
 * Pour basculer sur l'API réelle :
 *   Config.USE_MOCK = false;
 */

const Config = {
  API_BASE:    'https://web-production-ccab8.up.railway.app',
  WA_NUMBER:   '221XXXXXXXXX', // ← remplacer par le vrai numéro
  USE_MOCK:    true,            // ← passer à false quand Railway OK
  REFRESH_SEC: 30,
};

// ── DONNÉES MOCK ─────────────────────────────────────────
// Bus sur les vraies coordonnées GPS de Dakar.
// Remplacé par /api/buses quand USE_MOCK = false.

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
  { rank:1, name:'Mamadou Diallo', zone:'Liberté · Dieuppeul', count:142, badges:['Sentinelle L5','Expert Nord'],   avatar:'👨🏿' },
  { rank:2, name:'Fatou Sow',      zone:'Médina · HLM',        count:118, badges:['Queen Médina'],                  avatar:'👩🏿' },
  { rank:3, name:'Ibou Konaté',    zone:'Parcelles · Pikine',  count:97,  badges:['Banlieue King','Régulier'],      avatar:'🧑🏿' },
  { rank:4, name:'Aissatou Ba',    zone:'Grand Yoff · Castor', count:84,  badges:['Régulier'],                      avatar:'👩🏾' },
  { rank:5, name:'Omar Ndiaye',    zone:'Plateau · Centre',    count:71,  badges:['Centrevillain'],                 avatar:'👨🏾' },
  { rank:6, name:'Rokhaya Fall',   zone:'Rufisque · Thiaroye', count:63,  badges:['Banlieue'],                      avatar:'👩🏿' },
  { rank:7, name:'Cheikh Mbaye',   zone:'Keur Massar',         count:58,  badges:['Est solidaire'],                 avatar:'🧑🏾' },
  { rank:8, name:'Ndeye Thiam',    zone:'Yoff · Almadies',     count:47,  badges:['Côtière'],                       avatar:'👩🏽' },
];

const MOCK_STATS = {
  signalements_today: 247,
  contributors: 89,
};

// ── API MODULE ────────────────────────────────────────────

const Api = (() => {

  /**
   * Simule une légère variation des données mock
   * pour donner l'impression de temps réel.
   */
  function _simulateLiveVariation(buses) {
    return buses.map(b => ({
      ...b,
      minutes_ago: Math.max(0, b.minutes_ago + Math.floor(Math.random() * 2 - 0.3)),
    }));
  }

  /**
   * Récupère les bus actifs.
   * @returns {Promise<{buses: Array, stats: object}>}
   */
  async function fetchBuses() {
    if (Config.USE_MOCK) {
      return {
        buses: _simulateLiveVariation(MOCK_BUSES),
        stats: MOCK_STATS,
      };
    }

    const res = await fetch(`${Config.API_BASE}/api/buses`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    return {
      buses: data.buses || data,
      stats: data.stats || {},
    };
  }

  /**
   * Récupère le leaderboard.
   * @returns {Promise<Array>}
   */
  async function fetchLeaderboard() {
    if (Config.USE_MOCK) {
      return MOCK_LEADERBOARD;
    }

    const res = await fetch(`${Config.API_BASE}/api/leaderboard`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.leaderboard || data;
  }

  /**
   * Charge toutes les données en parallèle.
   * Fallback mock si l'API échoue.
   * @returns {Promise<{buses, stats, leaderboard}>}
   */
  async function fetchAll() {
    try {
      const [busData, leaderboard] = await Promise.all([
        fetchBuses(),
        fetchLeaderboard(),
      ]);
      return { ...busData, leaderboard };
    } catch (err) {
      console.warn('[Api] Erreur, fallback mock:', err.message);
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
