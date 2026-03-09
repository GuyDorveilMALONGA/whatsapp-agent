/**
 * js/utils.js
 * Fonctions utilitaires pures — aucune dépendance externe.
 * Pas de DOM, pas d'API, pas de Leaflet ici.
 */

const Utils = (() => {

  /**
   * Retourne la classe CSS selon l'âge du signalement.
   * @param {number} minutesAgo
   * @returns {'age-fresh'|'age-ok'|'age-old'}
   */
  function getAgeClass(minutesAgo) {
    if (minutesAgo <= 5)  return 'age-fresh';
    if (minutesAgo <= 15) return 'age-ok';
    return 'age-old';
  }

  /**
   * Retourne la couleur hex selon l'âge.
   * @param {number} minutesAgo
   * @returns {string} couleur hex
   */
  function getAgeColor(minutesAgo) {
    if (minutesAgo <= 5)  return '#00D67F';
    if (minutesAgo <= 15) return '#FFD166';
    return '#FF4757';
  }

  /**
   * Formate l'âge en texte lisible.
   * @param {number} minutesAgo
   * @returns {string}
   */
  function formatAge(minutesAgo) {
    if (minutesAgo < 1) return "à l'instant";
    if (minutesAgo === 1) return '1 min';
    return `${minutesAgo} min`;
  }

  /**
   * Classe CSS du rang leaderboard.
   * @param {number} rank
   * @returns {string}
   */
  function getRankClass(rank) {
    if (rank === 1) return 'gold';
    if (rank === 2) return 'silver';
    if (rank === 3) return 'bronze';
    return 'other';
  }

  /**
   * Symbole emoji du rang.
   * @param {number} rank
   * @returns {string}
   */
  function getRankSymbol(rank) {
    if (rank === 1) return '🥇';
    if (rank === 2) return '🥈';
    if (rank === 3) return '🥉';
    return String(rank);
  }

  /**
   * Génère une classe badge cyclique.
   * @param {number} index
   * @returns {string}
   */
  function getBadgeClass(index) {
    return ['badge-orange', 'badge-green', 'badge-yellow'][index % 3];
  }

  /**
   * Encode un message pour une URL WhatsApp.
   * @param {string} message
   * @returns {string} URL wa.me
   */
  function buildWhatsAppUrl(phoneNumber, message) {
    return `https://wa.me/${phoneNumber}?text=${encodeURIComponent(message)}`;
  }

  return {
    getAgeClass,
    getAgeColor,
    formatAge,
    getRankClass,
    getRankSymbol,
    getBadgeClass,
    buildWhatsAppUrl,
  };

})();
