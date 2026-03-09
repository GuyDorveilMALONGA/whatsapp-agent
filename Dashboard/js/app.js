/**
 * js/app.js
 * Point d'entrée — orchestre Api, MapManager, UI.
 * Aucune logique de rendu ici, seulement la coordination.
 *
 * Dépend de (dans l'ordre de chargement) :
 *   utils.js → api.js → map.js → ui.js → app.js
 */

// ── STATE ─────────────────────────────────────────────────
const State = {
  buses:      [],
  leaderboard: [],
  selectedId: null,
};

// ── INIT ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Carte
  MapManager.init('map', onBusSelect);

  // Tabs sidebar
  UI.initTabs();

  // Boutons WhatsApp
  _bindWhatsAppButtons();

  // Premier chargement
  loadAndRender().then(() => {
    UI.startTimer(Config.REFRESH_SEC, onTimerComplete);
  });
});

// ── CHARGEMENT ────────────────────────────────────────────

/**
 * Charge les données et met à jour toute l'interface.
 */
async function loadAndRender() {
  const data = await Api.fetchAll();

  State.buses       = data.buses       || [];
  State.leaderboard = data.leaderboard || [];

  // Carte
  MapManager.updateMarkers(State.buses, State.selectedId);

  // Sidebar
  UI.renderBusList(State.buses, State.selectedId, onBusSelect);
  UI.renderLeaderboard(State.leaderboard);

  // Stats bar
  UI.updateStats(State.buses.length, data.stats || {});
}

// ── CALLBACKS ─────────────────────────────────────────────

/**
 * Appelé quand l'usager clique sur un bus (carte ou sidebar).
 * @param {number} busId
 */
function onBusSelect(busId) {
  State.selectedId = busId;

  const bus = State.buses.find(b => b.id === busId);
  if (!bus) return;

  // Highlight sidebar
  UI.selectBusCard(busId);

  // Fly to + popup
  MapManager.flyToBus(bus);

  // Redessiner les markers pour refléter la sélection
  MapManager.updateMarkers(State.buses, State.selectedId);
}

/**
 * Appelé quand le timer atteint 0 — rafraîchit les données.
 */
async function onTimerComplete() {
  await loadAndRender();
  UI.startTimer(Config.REFRESH_SEC, onTimerComplete);
}

// ── WHATSAPP ──────────────────────────────────────────────

function _bindWhatsAppButtons() {
  const defaultMsg = 'Bonjour Xëtu ! Je veux signaler un bus 🚌';

  ['btn-signal-main', 'btn-signal-mobile'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) {
      btn.addEventListener('click', () => {
        window.open(
          Utils.buildWhatsAppUrl(Config.WA_NUMBER, defaultMsg),
          '_blank'
        );
      });
    }
  });
}
