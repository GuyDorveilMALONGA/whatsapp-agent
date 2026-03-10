/**
 * js/store.js
 * État centralisé observable — pattern pub/sub minimal.
 * 
 * RÈGLE D'OR : map.js, ui.js, mobile.js, chat.js ne se parlent
 * JAMAIS directement. Tout passe par store.js. Aucune exception.
 */

const _state = {
  buses:            [],
  filteredLine:     null,       // null = toutes les lignes
  selectedBus:      null,       // objet bus ou null
  chatMessages:     [],
  mobileSheetState: 'peek',     // 'peek' | 'half' | 'full'
  wsStatus:         'disconnected', // 'disconnected' | 'connecting' | 'connected'
  stats: {
    activeBuses:    0,
    reportsToday:   '—',
    contributors:   '—',
  },
};

const _listeners = new Map();

/**
 * S'abonner à un changement d'état.
 * @param {string} key
 * @param {Function} fn - appelée avec la nouvelle valeur
 * @returns {Function} unsubscribe
 */
export function subscribe(key, fn) {
  if (!_listeners.has(key)) _listeners.set(key, new Set());
  _listeners.get(key).add(fn);
  return () => _listeners.get(key).delete(fn);
}

/**
 * Lire une valeur de l'état.
 * @param {string} key
 * @returns {*}
 */
export function get(key) {
  return _state[key];
}

/**
 * Mettre à jour une valeur et notifier les abonnés.
 * @param {string} key
 * @param {*} value
 */
export function set(key, value) {
  _state[key] = value;
  const fns = _listeners.get(key);
  if (fns) fns.forEach(fn => fn(value));
}
