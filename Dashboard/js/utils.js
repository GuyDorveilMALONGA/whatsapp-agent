/**
 * XËTU — js/utils.js
 * Utilitaires purs. Zéro DOM, zéro effet de bord.
 * Peut être testé unitairement sans navigateur.
 */
const Utils = (() => {

  /**
   * Neutralise les injections XSS via le DOM lui-même.
   * Plus fiable qu'une regex car le navigateur gère tous les cas edge.
   */
  const escapeHTML = (str) => {
    if (str == null) return '';
    const node = document.createTextNode(String(str));
    const wrapper = document.createElement('span');
    wrapper.appendChild(node);
    return wrapper.innerHTML;
  };

  /**
   * Classe de confiance selon fraîcheur du signalement.
   * Retourne 'good' | 'warning' | 'danger' — lisible par un humain.
   */
  const getConfidenceClass = (confiance, minutesAgo) => {
    if (confiance === 'high' || confiance === 'vert' || minutesAgo < 10)   return 'good';
    if (confiance === 'medium' || confiance === 'jaune' || minutesAgo < 30) return 'warning';
    return 'danger';
  };

  const CONFIDENCE_LABELS = {
    good:    'FIABLE',
    warning: 'ESTIMÉ',
    danger:  'PEU SÛR',
  };

  const CONFIDENCE_COLORS = {
    good:    '#00935A',
    warning: '#C47D00',
    danger:  '#C42020',
  };

  /**
   * Temps relatif lisible.
   */
  const timeAgo = (minutes) => {
    if (minutes == null) return '?';
    if (minutes < 1)    return "à l'instant";
    if (minutes === 1)  return 'il y a 1 min';
    return `il y a ${minutes} min`;
  };

  return {
    escapeHTML,
    getConfidenceClass,
    CONFIDENCE_LABELS,
    CONFIDENCE_COLORS,
    timeAgo,
  };

})();
