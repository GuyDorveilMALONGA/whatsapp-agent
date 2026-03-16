/**
 * js/app.js — V1.0
 * Point d'entrée PWA Xëtu App Passager.
 * Orchestre la navigation et initialise les 4 écrans.
 */

import * as store   from './store.js';
import * as Toast   from './toast.js';
import * as Ws      from './ws.js';
import { WA_NUMBER, REFRESH_SEC } from './constants.js';
import { fetchBuses, fetchLeaderboard } from './api.js';
import { subscribeToPush, isPushSubscribed } from './push.js';
import { initHome }    from './home.js';
import { initSignal }  from './signal.js';
import { initChat }    from './chat.js';
import { initMylines } from './mylines.js';

// ── Navigation ────────────────────────────────────────────

const _navBtns  = document.querySelectorAll('.nav-btn');
const _screens  = document.querySelectorAll('.screen');

export function goTo(screenId) {
  _screens.forEach(s => s.classList.remove('active'));
  _navBtns.forEach(b => b.classList.remove('active'));

  const screen = document.getElementById(`screen-${screenId}`);
  const btn    = document.querySelector(`[data-screen="${screenId}"]`);
  if (screen) screen.classList.add('active');
  if (btn)    btn.classList.add('active');

  // Sous-titre header
  const labels = {
    home:    'Bus Dem Dikk · Dakar',
    signal:  'Signaler un bus',
    chat:    'Chat avec Xëtu',
    mylines: 'Mes lignes',
  };
  const sub = document.getElementById('header-sub');
  if (sub) sub.textContent = labels[screenId] || 'Xëtu';
}

_navBtns.forEach(btn => {
  btn.addEventListener('click', () => goTo(btn.dataset.screen));
});

// ── Stats bar ─────────────────────────────────────────────

function _updateStats(buses, lbStats) {
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.textContent !== String(val)) {
      el.textContent = val;
      el.classList.remove('updated');
      void el.offsetWidth;
      el.classList.add('updated');
    }
  };
  set('stat-bus',    buses.length);
  set('stat-sig',    lbStats?.signalements_today ?? '—');
  set('stat-contrib',lbStats?.contributors       ?? '—');
}

// ── Statut WebSocket dans le header ──────────────────────

function _updateWsStatus(status) {
  const btn = document.getElementById('ws-status-btn');
  if (!btn) return;
  btn.className = 'ws-status-btn';
  const map = {
    open:       { cls: 'ws-status--open',       label: 'En ligne'    },
    connecting: { cls: 'ws-status--connecting', label: 'Connexion…'  },
    closed:     { cls: 'ws-status--closed',     label: 'Hors ligne'  },
    failed:     { cls: 'ws-status--closed',     label: 'Non connecté'},
  };
  const conf = map[status] ?? map.closed;
  btn.classList.add(conf.cls);
  const label = btn.querySelector('.ws-label');
  if (label) label.textContent = conf.label;
}

// ── Timer polling ─────────────────────────────────────────

let _timerCount = REFRESH_SEC;
let _timerInt   = null;

function _startTimer() {
  clearInterval(_timerInt);
  _timerCount = REFRESH_SEC;
  _timerInt   = setInterval(async () => {
    _timerCount--;
    const el = document.getElementById('timer');
    if (el) el.textContent = `${_timerCount}s`;
    if (_timerCount <= 0) {
      await _loadData();
      _timerCount = REFRESH_SEC;
    }
  }, 1000);
}

// ── Chargement données ───────────────────────────────────

async function _loadData() {
  try {
    const [busRes, lbRes] = await Promise.allSettled([
      fetchBuses(),
      fetchLeaderboard(),
    ]);

    const buses = busRes.status === 'fulfilled'
      ? busRes.value.buses || []
      : store.get('buses') || [];

    const lbData = lbRes.status === 'fulfilled'
      ? lbRes.value
      : { leaderboard: store.get('leaderboard') || [], stats: {} };

    store.set('buses',       buses);
    store.set('leaderboard', lbData.leaderboard || []);
    store.set('stats',       lbData.stats       || {});

    _updateStats(buses, lbData.stats);

  } catch (err) {
    console.warn('[App] Erreur chargement:', err);
  }
}

// ── PWA install ───────────────────────────────────────────

let _installPrompt = null;

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  _installPrompt = e;
});

// ── INIT ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {

  // 1. Initialiser les 4 écrans
  initHome({ onSeeBus: () => goTo('signal') });
  initSignal({ onSuccess: () => { goTo('home'); _loadData(); } });
  initChat();
  initMylines();

  // 2. WebSocket
  Ws.init({
    onOpen: async (sessionId) => {
      _updateWsStatus('open');
      store.set('wsStatus', 'open');
      // Push notifications
      const alreadySub = await isPushSubscribed();
      if (!alreadySub) await subscribeToPush();
    },
    onChatResponse: (text) => {
      store.set('lastBotMessage', text);
    },
    onTyping: (active) => {
      store.set('chatTyping', active);
    },
    onWelcome: (text, suggestions, firstVisit) => {
      store.set('chatWelcome', { text, suggestions, firstVisit });
    },
    onError: (msg) => {
      _updateWsStatus('closed');
      Toast.error(msg || 'Connexion perdue');
    },
    onClose: () => {
      _updateWsStatus('closed');
      store.set('wsStatus', 'closed');
    },
    onReconnecting: () => {
      _updateWsStatus('connecting');
      store.set('wsStatus', 'connecting');
    },
  });

  // 3. Chargement initial
  await _loadData();

  // 4. Timer
  _startTimer();

  // 5. Listeners réseau
  window.addEventListener('online',  () => Toast.info('Connexion rétablie ✅'));
  window.addEventListener('offline', () => Toast.error('Hors ligne'));

  // 6. Service Worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(err => {
      console.warn('[App] SW registration failed:', err);
    });
  }

  // 7. Deep link ?action=report
  const action = new URLSearchParams(window.location.search).get('action');
  if (action === 'report') goTo('signal');

});
