/**
 * XËTU — js/api.js
 * Couche réseau. Ne touche jamais au DOM.
 * Retry + Exponential Backoff + AbortController timeout.
 * Conçu pour les connexions instables (Orange/Free Dakar).
 */
const ApiService = (() => {

  const CONFIG = {
    BASE_URL:    'https://web-production-ccab8.up.railway.app/api',
    TIMEOUT_MS:  8000, // Railway cold start peut être lent
    MAX_RETRIES: 2,
  };

  /**
   * Fetch avec timeout et retry automatique.
   * Si le réseau coupe une seconde, l'utilisateur ne voit rien.
   */
  const _fetchWithRetry = async (endpoint, retries = CONFIG.MAX_RETRIES) => {
    const url = `${CONFIG.BASE_URL}${endpoint}`;

    for (let attempt = 0; attempt <= retries; attempt++) {
      const controller = new AbortController();
      const timeoutId  = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

      try {
        const response = await fetch(url, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();

      } catch (error) {
        clearTimeout(timeoutId);

        const isLastAttempt = attempt === retries;
        if (isLastAttempt) {
          console.error(`[ApiService] Échec définitif sur ${endpoint} :`, error.message);
          throw error;
        }

        // Exponential backoff : 1s puis 2s avant de réessayer
        const waitMs = Math.pow(2, attempt) * 1000;
        console.warn(`[ApiService] Tentative ${attempt + 1} échouée. Retry dans ${waitMs / 1000}s…`);
        await new Promise(resolve => setTimeout(resolve, waitMs));
      }
    }
  };

  const getActiveBuses = async () => {
    const data = await _fetchWithRetry('/buses');
    return data.buses || [];
  };

  const getLeaderboard = async () => {
    return await _fetchWithRetry('/leaderboard');
  };

  return { getActiveBuses, getLeaderboard };

})();
