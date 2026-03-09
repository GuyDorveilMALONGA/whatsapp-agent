/**
 * XËTU — js/app.js
 * Orchestrateur. Coordonne ApiService, XetuMap et UI.
 * Contient l'état centralisé et la boucle de refresh.
 * Ne manipule jamais le DOM directement — délègue tout à UI.
 */
const App = (() => {

  // État centralisé — une seule source de vérité
  const state = {
    buses:         [],
    currentFilter: 'all',
    countdown:     30,
    isFirstLoad:   true,
  };

  // ── Interactions utilisateur ───────────────────────────

  const onFilterChange = (filterValue) => {
    state.currentFilter = filterValue;
    UI.renderFilters(state.buses, state.currentFilter, onFilterChange);
    UI.renderBusList(state.buses, state.currentFilter, onBusCardClick);
  };

  const onBusCardClick = (bus) => {
    XetuMap.focusOn(bus.lat, bus.lon);
    const busId = bus.id_unique || bus.ligne;
    XetuMap.openMarkerPopup(busId);
  };

  // ── Fetch et mise à jour ───────────────────────────────

  const refreshData = async () => {
    try {
      // Requêtes en parallèle — on ne attend pas l'une pour lancer l'autre
      const [busesData, leaderboardData] = await Promise.all([
        ApiService.getActiveBuses(),
        ApiService.getLeaderboard(),
      ]);

      const previousCount = state.buses.length;
      state.buses = busesData;

      // Mise à jour UI
      UI.animateValue(UI.DOM.statBuses, state.buses.length);
      UI.renderFilters(state.buses, state.currentFilter, onFilterChange);
      UI.renderBusList(state.buses, state.currentFilter, onBusCardClick);
      UI.renderLeaderboard(leaderboardData);

      // Mise à jour carte
      XetuMap.updateFleet(state.buses);

      // Notification — seulement après le premier chargement
      if (!state.isFirstLoad && state.buses.length > previousCount) {
        UI.showToast('🚌 Nouveau bus signalé !', 'success');
      }

      if (state.isFirstLoad) {
        UI.hideLoader();
        state.isFirstLoad = false;
      }

    } catch (error) {
      console.error('[App] Erreur de refresh :', error);
      UI.showToast('Connexion perdue. Réessai en cours…', 'error');
    }
  };

  // ── Boucle de rafraîchissement ─────────────────────────

  const startRefreshLoop = () => {
    state.countdown = 30;

    const tick = setInterval(() => {
      state.countdown--;
      UI.updateTimer(state.countdown);

      if (state.countdown <= 0) {
        clearInterval(tick);
        UI.updateTimer(0);
        refreshData().then(startRefreshLoop);
      }
    }, 1000);
  };

  // ── Initialisation ─────────────────────────────────────

  const init = () => {
    UI.init();          // Cache DOM d'abord
    XetuMap.init('map');
    refreshData();
    startRefreshLoop();
  };

  return { init };

})();

// Point d'entrée unique — après que le DOM est prêt
document.addEventListener('DOMContentLoaded', App.init);
