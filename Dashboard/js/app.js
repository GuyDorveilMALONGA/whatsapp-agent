/**
 * js/app.js
 * Point d'entrée unique. Initialise tout. Orchestre sans logique de rendu.
 *
 * Cycle de vie :
 *  1. constants + store
 *  2. map (Leaflet)
 *  3. ui (sidebar desktop)
 *  4. mobile (bottom sheet — uniquement sur mobile)
 *  5. modal (signalement)
 *  6. premier fetchAll
 *  7. polling 30s
 *  8. event listeners globaux
 */

import * as store      from './store.js';
import * as Api        from './api.js';
import * as MapManager from './map.js';
import * as UI         from './ui.js';
import * as Mobile     from './mobile.js';
import * as Modal      from './modal.js';
import Toast           from './toast.js';
import { WA_NUMBER, REFRESH_SEC } from './constants.js';
import { buildWhatsAppUrl } from './utils.js';

// ── DEEP LINK (appliqué avant DOMContentLoaded) ──────────

(function _applyDeepLink() {
  const params = new URLSearchParams(window.location.search);
  const line   = params.get('line');
  if (line) store.set('filteredLine', line);
})();

// ── INIT ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  // 1. Carte
  MapManager.init('map', _onBusSelect);

  // 2. UI sidebar desktop
  UI.initStats();
  UI.initTabs();
  UI.initFilters(_onFilterChange);
  UI.initBusList(_onBusSelect);
  UI.initLeaderboard();

  // 3. Bottom sheet mobile
  Mobile.init(_onBusSelect);

  // 4. Modal signalement
  window.__XETU_WA_NUMBER__ = WA_NUMBER;
  Modal.init({
    onConfirmSuccess: (busId) => {
      MapManager.pulseMarker(busId);
      _bumpReportsCount();
    },
  });

  // 5. Callbacks globaux pour les popups Leaflet (vanilla onclick dans map.js)
  window._onPopupDetails = (busId) => _onBusSelect(busId);
  window._onPopupConfirm = (busId, btnEl) => Modal.confirmBus(busId, btnEl);
  window._resetFilter    = () => _onFilterChange(null);

  // 6. Boutons "Signaler" — sidebar desktop + bottom sheet mobile
  ['btn-signaler', 'btn-signaler-mobile'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) {
      btn.addEventListener('click', (e) => {
        const bus = store.get('selectedBus');
        Modal.openModal(
          bus ? { ligne: bus.ligne, arret: bus.position } : {},
          e.currentTarget
        );
      });
    }
  });

  // 7. Chargement initial
  await _loadAndRender();

  // 8. Timer polling
  UI.startTimer(REFRESH_SEC, _onTimerComplete);

  // 9. Listeners globaux
  window.addEventListener('online',  () => Toast.info('Connexion rétablie ✅'));
  window.addEventListener('offline', () => Toast.error('Hors ligne — données en cache'));
});

// ── CHARGEMENT ────────────────────────────────────────────

async function _loadAndRender() {
  try {
    const data = await Api.fetchAll();

    store.set('buses', data.buses || []);
    store.set('stats', {
      activeBuses:  data.buses?.length ?? 0,
      reportsToday: data.stats?.signalements_today ?? '—',
      contributors: data.stats?.contributors ?? '—',
    });

    UI.renderLeaderboard(data.leaderboard || []);
    Mobile.injectLeaderboard(data.leaderboard || []);

  } catch (err) {
    Toast.error('Erreur de chargement. Données en cache affichées.');
  }
}

// ── CALLBACKS ─────────────────────────────────────────────

function _onBusSelect(busId) {
  const bus = store.get('buses').find(b => b.id === busId);
  if (!bus) return;
  store.set('selectedBus', bus);
  UI.selectBusCard(busId);
}

function _onFilterChange(line) {
  store.set('filteredLine', line);
  const url = new URL(window.location);
  if (line) url.searchParams.set('line', line);
  else      url.searchParams.delete('line');
  history.replaceState(null, '', url);
}

async function _onTimerComplete() {
  await _loadAndRender();
  UI.startTimer(REFRESH_SEC, _onTimerComplete);
}

// ── HELPERS ───────────────────────────────────────────────

function _bumpReportsCount() {
  const stats   = store.get('stats');
  const current = parseInt(stats.reportsToday, 10) || 0;
  store.set('stats', { ...stats, reportsToday: current + 1 });
}