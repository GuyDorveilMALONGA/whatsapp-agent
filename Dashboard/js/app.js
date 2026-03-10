/**
 * js/app.js
 * Point d'entrée unique. Initialise tout. Orchestre sans logique de rendu.
 * 
 * Cycle de vie :
 *  1. constants + store
 *  2. map (Leaflet)
 *  3. ui (sidebar, stats, filtres)
 *  4. premier fetchAll
 *  5. polling 30s
 *  6. event listeners globaux
 */

import * as store from './store.js';
import * as Api   from './api.js';
import * as MapManager from './map.js';
import * as UI    from './ui.js';
import Toast      from './toast.js';
import { WA_NUMBER, REFRESH_SEC } from './constants.js';
import { buildWhatsAppUrl } from './utils.js';

// ── INIT ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  // 1. Carte
  MapManager.init('map', _onBusSelect);

  // 2. UI — stats, tabs, filtres, bus list
  UI.initStats();
  UI.initTabs();
  UI.initFilters(_onFilterChange);
  UI.initBusList(_onBusSelect);
  UI.initLeaderboard();

  // 3. Callbacks globaux pour les popups Leaflet (vanilla onclick)
  window._onPopupDetails  = _onBusSelect;
  window._onPopupConfirm  = _onPopupConfirm;
  window._resetFilter     = () => _onFilterChange(null);

  // 4. Boutons WhatsApp
  _bindWhatsAppButtons();

  // 5. Chargement initial
  await _loadAndRender();

  // 6. Timer + polling
  UI.startTimer(REFRESH_SEC, _onTimerComplete);

  // 7. Listeners globaux
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
  // Deep link
  const url = new URL(window.location);
  if (line) url.searchParams.set('line', line);
  else url.searchParams.delete('line');
  history.replaceState(null, '', url);
}

async function _onTimerComplete() {
  await _loadAndRender();
  UI.startTimer(REFRESH_SEC, _onTimerComplete);
}

async function _onPopupConfirm(busId, btnEl) {
  const bus = store.get('buses').find(b => b.id === busId);
  if (!bus || btnEl.disabled) return;

  btnEl.disabled = true;
  btnEl.classList.add('loading');
  btnEl.textContent = '…';

  try {
    // Phase 1 : endpoint /api/report à créer côté Railway
    // Pour l'instant : simulation d'un POST (fallback WA si 404)
    const res = await fetch(`${(await import('./constants.js')).API_BASE}/api/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ligne:     bus.ligne,
        arret:     bus.position,
        source:    'web_dashboard',
        client_ts: new Date().toISOString(),
      }),
    });

    if (res.ok) {
      Toast.success(`Bus ${bus.ligne} confirmé à ${bus.position} ✅`);
      MapManager.pulseMarker(busId);
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch {
    Toast.error('Envoi échoué', {
      retry: () => _onPopupConfirm(busId, btnEl),
    });
    btnEl.disabled = false;
    btnEl.classList.remove('loading');
    btnEl.textContent = '✅ Confirmer';
    return;
  }

  btnEl.textContent = '✅ Confirmé';
  setTimeout(() => {
    if (btnEl.isConnected) {
      btnEl.disabled = false;
      btnEl.classList.remove('loading');
      btnEl.textContent = '✅ Confirmer';
    }
  }, 3000);
}

// ── WHATSAPP ──────────────────────────────────────────────

function _bindWhatsAppButtons() {
  const msg = 'Bonjour Xëtu ! Je veux signaler un bus 🚌';
  ['btn-signal-main', 'btn-signal-mobile'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener('click', () =>
      window.open(buildWhatsAppUrl(WA_NUMBER, msg), '_blank')
    );
  });
}

// ── DEEP LINK (line=XX dans l'URL) ───────────────────────

(function _applyDeepLink() {
  const params = new URLSearchParams(window.location.search);
  const line = params.get('line');
  if (line) store.set('filteredLine', line);
})();
