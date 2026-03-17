/**
 * js/app.js — V2.0 Sprint Final
 */

import * as store   from './store.js';
import * as Toast   from './toast.js';
import * as Ws      from './ws.js';
import { REFRESH_SEC } from './constants.js';
import { fetchBuses, fetchLeaderboard } from './api.js';
import { subscribeToPush, isPushSubscribed } from './push.js';
import { initHome }    from './home.js';
import { initSignal }  from './signal.js';
import { initChat }    from './chat.js';
import { initMylines } from './mylines.js';

const NAV_SCREENS = ['home', 'itin', 'mylines'];
const _navBtns    = document.querySelectorAll('.nav-btn');
const _screens    = document.querySelectorAll('.screen');

// ── Navigation ────────────────────────────────────────────

export function goTo(screenId) {
  _screens.forEach(s => s.classList.remove('active'));
  if (NAV_SCREENS.includes(screenId)) {
    _navBtns.forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-screen="${screenId}"]`)?.classList.add('active');
  }
  document.getElementById(`screen-${screenId}`)?.classList.add('active');
}

_navBtns.forEach(btn => btn.addEventListener('click', () => goTo(btn.dataset.screen)));
document.getElementById('btn-back-signal')?.addEventListener('click', () => goTo('home'));

// ── Menu hamburger — corrigé ──────────────────────────────

function _initMenu() {
  const overlay  = document.getElementById('menu-overlay');
  const btnOpen  = document.getElementById('btn-menu');
  const btnClose = document.getElementById('menu-close');
  if (!overlay || !btnOpen) return;

  const open  = () => { overlay.hidden = false; };
  const close = () => { overlay.hidden = true;  };

  btnOpen.addEventListener('click', open);
  btnClose?.addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

  // Partager
  document.getElementById('menu-partager')?.addEventListener('click', async () => {
    close();
    try {
      if (navigator.share) {
        await navigator.share({ title: 'Xëtu', text: 'Suis les bus Dem Dikk en temps réel', url: location.href });
      } else {
        await navigator.clipboard?.writeText(location.href);
        Toast.info('Lien copié !');
      }
    } catch {}
  });

  // CGU
  document.getElementById('menu-cgu')?.addEventListener('click', () => {
    close();
    Toast.info('Conditions d\'utilisation à venir');
  });

  // Avis → popup étoiles
  document.getElementById('menu-avis')?.addEventListener('click', () => {
    close();
    _openPopup('popup-avis');
  });

  // Contact → popup
  document.getElementById('menu-contact')?.addEventListener('click', () => {
    close();
    _openPopup('popup-contact');
  });
}

// ── Popups ────────────────────────────────────────────────

function _openPopup(id) {
  document.getElementById(id).hidden = false;
}
function _closePopup(id) {
  document.getElementById(id).hidden = true;
}

function _initPopups() {
  // Popup Avis — étoiles
  let _starVal = 0;
  const starsRow = document.getElementById('stars-row');
  starsRow?.querySelectorAll('.star-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      _starVal = parseInt(btn.dataset.val);
      starsRow.querySelectorAll('.star-btn').forEach((b, i) => {
        b.classList.toggle('active', i < _starVal);
      });
    });
    btn.addEventListener('mouseenter', () => {
      const hov = parseInt(btn.dataset.val);
      starsRow.querySelectorAll('.star-btn').forEach((b, i) => {
        b.classList.toggle('active', i < hov);
      });
    });
    btn.addEventListener('mouseleave', () => {
      starsRow.querySelectorAll('.star-btn').forEach((b, i) => {
        b.classList.toggle('active', i < _starVal);
      });
    });
  });

  document.getElementById('avis-cancel')?.addEventListener('click', () => _closePopup('popup-avis'));
  document.getElementById('avis-confirm')?.addEventListener('click', () => {
    _closePopup('popup-avis');
    if (_starVal >= 4) {
      window.open('https://play.google.com/store/apps/', '_blank');
    } else if (_starVal > 0) {
      Toast.info('Merci pour votre avis ! 🙏');
    }
  });
  // Fermer en cliquant fond
  document.getElementById('popup-avis')?.addEventListener('click', (e) => {
    if (e.target.id === 'popup-avis') _closePopup('popup-avis');
  });

  // Popup Contact
  document.getElementById('contact-close')?.addEventListener('click', () => _closePopup('popup-contact'));
  document.getElementById('popup-contact')?.addEventListener('click', (e) => {
    if (e.target.id === 'popup-contact') _closePopup('popup-contact');
  });
}

// ── Statut WebSocket — point coloré seulement ─────────────

function _updateWsStatus(status) {
  const el = document.getElementById('ws-status-btn');
  if (!el) return;
  el.className = `ws-status-dot-only ws-status--${
    status === 'open' ? 'open' : status === 'connecting' ? 'connecting' : 'closed'
  }`;
}

// ── Timer ─────────────────────────────────────────────────

let _timerCount = REFRESH_SEC;
let _timerInt   = null;

function _startTimer() {
  clearInterval(_timerInt);
  _timerCount = REFRESH_SEC;
  _timerInt = setInterval(async () => {
    _timerCount--;
    const el = document.getElementById('timer');
    if (el) el.textContent = `${_timerCount}s`;
    if (_timerCount <= 0) { await _loadData(); _timerCount = REFRESH_SEC; }
  }, 1000);
}

// ── Données ───────────────────────────────────────────────

async function _loadData() {
  try {
    const [busRes, lbRes] = await Promise.allSettled([fetchBuses(), fetchLeaderboard()]);
    const buses  = busRes.status === 'fulfilled' ? busRes.value.buses || [] : store.get('buses') || [];
    const lbData = lbRes.status  === 'fulfilled' ? lbRes.value : { leaderboard: [], stats: {} };
    store.set('buses',       buses);
    store.set('leaderboard', lbData.leaderboard || []);
    store.set('stats',       lbData.stats || {});
  } catch (err) {
    console.warn('[App]', err);
  }
}

// ── Init ──────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {

  _initMenu();
  _initPopups();

  initHome({ onSeeBus: () => goTo('signal') });
  initSignal({ onSuccess: () => { goTo('home'); _loadData(); } });
  initChat();
  initMylines();

  Ws.init({
    onOpen: async () => {
      _updateWsStatus('open');
      store.set('wsStatus', 'open');
      const sub = await isPushSubscribed();
      if (!sub) await subscribeToPush();
    },
    onChatResponse: (text) => store.set('lastBotMessage', text),
    onTyping:       (active) => store.set('chatTyping', active),
    onWelcome:      (text, suggestions) => {
      // NE PAS afficher le texte welcome — il est déjà dans le HTML
      // On envoie seulement les suggestions si présentes
      if (suggestions?.length) store.set('chatSuggestions', suggestions);
    },
    onError:        (msg) => { _updateWsStatus('closed'); Toast.error(msg || 'Connexion perdue'); },
    onClose:        ()    => { _updateWsStatus('closed');     store.set('wsStatus', 'closed'); },
    onReconnecting: ()    => { _updateWsStatus('connecting'); store.set('wsStatus', 'connecting'); },
  });

  await _loadData();
  _startTimer();

  window.addEventListener('online',  () => Toast.info('Connexion rétablie ✅'));
  window.addEventListener('offline', () => Toast.error('Hors ligne'));

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(e => console.warn('[SW]', e));
  }

  if (new URLSearchParams(location.search).get('action') === 'report') goTo('signal');
});
