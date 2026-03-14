/**
 * js/app.js — Phase 5.1.2
 * Point d'entrée unique. Orchestre sans logique de rendu.
 *
 * MIGRATIONS Phase 5.1.2 :
 *   - Push notifications déplacées dans onOpen WebSocket
 *     pour garantir que getSessionId() est disponible
 *
 * V6.0 :
 *   - MapManager.init() est maintenant async → await ajouté
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
import { subscribeToPush, isPushSubscribed } from './push.js';

// ── DEEP LINK ─────────────────────────────────────────────
(function _applyDeepLink() {
  const params = new URLSearchParams(window.location.search);
  const line   = params.get('line');
  if (line) store.set('filteredLine', line);
})();

// ── INIT ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {

  // 1. Carte (async — charge les tracés au démarrage)
  await MapManager.init('map', _onBusSelect);

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
    onReportSuccess: () => _loadAndRender(),
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

  // Deep link ligne → overlay immédiat
  const deepLine = store.get('filteredLine');
  if (deepLine) await _applyLineOverlay(deepLine);

  // 9. Timer polling
  UI.startTimer(REFRESH_SEC, _onTimerComplete);

  // 10. Listeners globaux
  window.addEventListener('online',  () => Toast.info('Connexion rétablie ✅'));
  window.addEventListener('offline', () => Toast.error('Hors ligne — données en cache'));

  // 11. PWA
  _initPWA();

  // 12. Shortcut manifest (?action=report)
  const action = new URLSearchParams(window.location.search).get('action');
  if (action === 'report') {
    setTimeout(() => Modal.openModal({}, document.getElementById('btn-signaler')), 300);
  }
});

// ── OVERLAY LIGNE ─────────────────────────────────────────

async function _applyLineOverlay(line) {
  if (!line) {
    MapManager.clearLineOverlay();
    return;
  }
  try {
    const lineData = await Api.getLineData(line);
    if (lineData) {
      MapManager.showLineOverlay(lineData);
    } else {
      console.warn(`[App] Ligne ${line} introuvable dans routes_geometry_v13`);
      MapManager.clearLineOverlay();
    }
  } catch (err) {
    console.warn('[App] Erreur chargement overlay ligne :', err.message);
    MapManager.clearLineOverlay();
  }
}

// ── PWA ───────────────────────────────────────────────────

let _deferredInstallPrompt = null;

function _initPWA() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .then(reg => {
        console.log('[PWA] Service Worker enregistré :', reg.scope);
        reg.addEventListener('updatefound', () => {
          const newWorker = reg.installing;
          if (!newWorker) return;
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              _showUpdateBanner(newWorker);
            }
          });
        });
      })
      .catch(err => console.warn('[PWA] Enregistrement SW échoué :', err));

    navigator.serviceWorker.addEventListener('controllerchange', () => {
      window.location.reload();
    });
  }

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    _deferredInstallPrompt = e;
    const btn = document.getElementById('btn-install');
    if (btn) btn.hidden = false;
  });

  const installBtn = document.getElementById('btn-install');
  if (installBtn) {
    installBtn.addEventListener('click', async () => {
      if (!_deferredInstallPrompt) return;
      _deferredInstallPrompt.prompt();
      const { outcome } = await _deferredInstallPrompt.userChoice;
      console.log('[PWA] Install prompt outcome :', outcome);
      _deferredInstallPrompt = null;
      installBtn.hidden = true;
    });
  }

  window.addEventListener('appinstalled', () => {
    const btn = document.getElementById('btn-install');
    if (btn) btn.hidden = true;
    _deferredInstallPrompt = null;
    Toast.success('Xëtu installé ! 🎉');
  });
}

// ── MISE À JOUR PWA ───────────────────────────────────────

function _showUpdateBanner(newWorker) {
  if (document.getElementById('update-banner')) return;

  const banner = document.createElement('div');
  banner.id = 'update-banner';
  banner.style.cssText = `
    position: fixed;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    background: #1e293b;
    border: 1px solid #ff6b35;
    color: #fff;
    padding: 12px 20px;
    border-radius: 12px;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 12px;
    z-index: 9999;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    max-width: calc(100vw - 32px);
    white-space: nowrap;
  `;
  banner.innerHTML = `
    <span>🔄 Nouvelle version disponible</span>
    <button style="
      background: #ff6b35;
      color: white;
      border: none;
      border-radius: 8px;
      padding: 6px 14px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    ">Mettre à jour</button>
  `;

  banner.querySelector('button').addEventListener('click', () => {
    newWorker.postMessage({ type: 'SKIP_WAITING' });
    banner.remove();
  });

  document.body.appendChild(banner);
  setTimeout(() => banner.remove(), 30_000);
}

// ── CHAT + WEBSOCKET ──────────────────────────────────────

function _initChat() {
  Chat.init({
    onSend: (text) => {
      const sent = Ws.sendChat(text);
      if (!sent) {
        Chat.appendMessage('bot', '⚠️ Non connecté. Réessaie dans un instant.');
      }
    },
  });

  Ws.init({
    onOpen: async () => {
      Chat.setStatus('open');

      try {
        const alreadySubscribed = await isPushSubscribed();
        if (!alreadySubscribed) {
          await subscribeToPush();
        }
      } catch (err) {
        console.warn('[Push] Erreur init push:', err);
      }
    },

    onWelcome: (text, suggestions, firstVisit) => {
      Chat.showWelcome(text, suggestions, firstVisit);
    },

    onTyping: (active) => {
      Chat.setTyping(active);
    },

    onChatResponse: (text) => {
      Chat.setTyping(false);
      Chat.appendMessage('bot', text);
    },

    onError: (message) => {
      Chat.setTyping(false);
      Chat.appendMessage('bot', `⚠️ ${message}`);
    },

    onClose: (wasClean) => {
      Chat.setStatus('closed');
      if (!wasClean) store.set('wsStatus', 'closed');
    },

    onReconnecting: () => {
      Chat.setStatus('connecting');
    },
  });

  store.subscribe('wsStatus', (status) => Chat.setStatus(status));

  if (window.innerWidth > 768) {
    setTimeout(() => Chat.open(), 1000);
  }
}

// ── CHARGEMENT ────────────────────────────────────────────

async function _loadAndRender() {
  try {
    const data = await Api.fetchAll();

    store.set('buses', data.buses || []);
    store.set('stats', {
      activeBuses:  data.buses?.length ?? 0,
      reportsToday: data.stats?.signalements_today ?? '—',
      contributors: data.stats?.contributors       ?? '—',
    });

    UI.renderLeaderboard(data.leaderboard || []);
    Mobile.injectLeaderboard(data.leaderboard || []);

  } catch (err) {
    Toast.error('Erreur de chargement. Données en cache affichées.');
  }
}

// ── CALLBACKS ─────────────────────────────────────────────

function _onBusSelect(busId) {
  const bus = store.get('buses').find(b => String(b.id) === String(busId));
  if (!bus) return;
  store.set('selectedBus', bus);
  UI.selectBusCard(busId);
}

async function _onFilterChange(line) {
  store.set('filteredLine', line);

  const url = new URL(window.location);
  if (line) url.searchParams.set('line', line);
  else      url.searchParams.delete('line');
  history.replaceState(null, '', url);

  await _applyLineOverlay(line);
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