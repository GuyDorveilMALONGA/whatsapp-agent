/**
 * js/app.js — Phase 3
 * Point d'entrée unique. Orchestre sans logique de rendu.
 *
 * Cycle de vie :
 *  1. store + deep link
 *  2. map
 *  3. ui sidebar
 *  4. mobile bottom sheet
 *  5. modal signalement natif
 *  6. chat UI + WebSocket
 *  7. fetchAll initial
 *  8. polling 30s
 */

import * as store      from './store.js';
import * as Api        from './api.js';
import * as MapManager from './map.js';
import * as UI         from './ui.js';
import * as Mobile     from './mobile.js';
import * as Modal      from './modal.js';
import * as Ws         from './ws.js';
import * as Chat       from './chat.js';
import Toast           from './toast.js';
import { WA_NUMBER, REFRESH_SEC } from './constants.js';

// ── DEEP LINK ─────────────────────────────────────────────
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

  // 3. Bottom sheet mobile
  Mobile.init(_onBusSelect);

  // 4. Modal signalement natif
  window.__XETU_WA_NUMBER__ = WA_NUMBER;
  Modal.init({
    onConfirmSuccess: (busId) => {
      MapManager.pulseMarker(busId);
      _bumpReportsCount();
    },
  });

  // 5. Callbacks globaux pour popups Leaflet
  window._onPopupDetails = (busId) => _onBusSelect(busId);
  window._onPopupConfirm = (busId, btnEl) => Modal.confirmBus(busId, btnEl);
  window._resetFilter    = () => _onFilterChange(null);

  // 6. Boutons "Signaler"
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

  // 7. Chat + WebSocket
  _initChat();

  // 8. Chargement initial
  await _loadAndRender();

  // 9. Timer polling
  UI.startTimer(REFRESH_SEC, _onTimerComplete);

  // 10. Listeners globaux
  window.addEventListener('online',  () => Toast.info('Connexion rétablie ✅'));
  window.addEventListener('offline', () => Toast.error('Hors ligne — données en cache'));
});

// ── CHAT + WEBSOCKET ──────────────────────────────────────

function _initChat() {
  // Initialise l'UI chat avec le callback d'envoi
  Chat.init({
    onSend: (text) => {
      const sent = Ws.sendChat(text);
      if (!sent) {
        Chat.hideTyping();
        Chat.appendMessage('bot', '⚠️ Non connecté. Réessaie dans un instant.');
      }
    },
  });

  // Initialise le WebSocket
  Ws.init({
    onOpen: () => {
      Chat.setStatus('open');
    },

    onWelcome: (text, suggestions) => {
      Chat.appendMessage('bot', text);
      Chat.setSuggestions(suggestions);
    },

    onChatResponse: (text) => {
      Chat.hideTyping();
      Chat.appendMessage('bot', text);
    },

    onReportAck: (payload) => {
      Chat.hideTyping();
      if (payload.success) {
        Chat.appendMessage('bot', '✅ Signalement enregistré ! Merci 🙏');
        _bumpReportsCount();
      } else {
        Chat.appendMessage('bot', `❌ ${payload.error || 'Erreur lors du signalement.'}`);
      }
    },

    onError: (message) => {
      Chat.hideTyping();
      Chat.appendMessage('bot', `⚠️ ${message}`);
    },

    onClose: (wasClean) => {
      Chat.setStatus('closed');
      if (!wasClean) {
        store.set('wsStatus', 'closed');
      }
    },

    onReconnecting: (attempt) => {
      Chat.setStatus('connecting');
    },
  });

  // Synchronise le statut WS dans le chat
  store.subscribe('wsStatus', (status) => {
    Chat.setStatus(status);
  });
}

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

function _bumpReportsCount() {
  const stats   = store.get('stats');
  const current = parseInt(stats?.reportsToday, 10) || 0;
  store.set('stats', { ...stats, reportsToday: current + 1 });
}