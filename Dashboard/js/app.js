/**
 * js/app.js — V2.3
 * FIX DEMO_MODE : _loadData() ne touche pas les bus démo
 * FIX V2.3 : intégration signal.js V3.1
 *   - import onScreenEnter depuis signal.js
 *   - goTo('signal') appelle signalScreenEnter()
 *   - btn-see-bus sans { capture: true } (était la cause du crash carte noire)
 */

import * as store   from './store.js';
import * as Toast   from './toast.js';
import * as Ws      from './ws.js';
import { REFRESH_SEC } from './constants.js';
import { fetchBuses, fetchLeaderboard } from './api.js';
import { subscribeToPush, isPushSubscribed } from './push.js';
import { initHome }    from './home.js';
import { initSignal, onScreenEnter as signalScreenEnter } from './signal.js';
import { initChat }    from './chat.js';
import { initMylines } from './mylines.js';

const NAV_SCREENS = ['home', 'itin', 'mylines'];
const _navBtns    = document.querySelectorAll('.nav-btn');
const _screens    = document.querySelectorAll('.screen');

// ── Mode démo ─────────────────────────────────────────────
// false → données réelles depuis Railway/Supabase
const DEMO_MODE = false;

// ── Navigation ────────────────────────────────────────────

export function goTo(screenId) {
  _screens.forEach(s => s.classList.remove('active'));
  if (NAV_SCREENS.includes(screenId)) {
    _navBtns.forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-screen="${screenId}"]`)?.classList.add('active');
  }
  document.getElementById(`screen-${screenId}`)?.classList.add('active');

  // FIX V2.3 : déclencher GPS auto quand on arrive sur l'écran signal
  if (screenId === 'signal') signalScreenEnter();
}

_navBtns.forEach(btn => btn.addEventListener('click', () => goTo(btn.dataset.screen)));
document.getElementById('btn-back-signal')?.addEventListener('click', () => goTo('home'));

// ── Popups ────────────────────────────────────────────────

function _openPopup(id) {
  setTimeout(() => {
    const el = document.getElementById(id);
    if (el) el.hidden = false;
  }, 50);
}

function _closePopup(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = true;
}

function _initPopups() {
  let _starVal = 0;
  const starsRow = document.getElementById('stars-row');

  starsRow?.querySelectorAll('.star-btn').forEach(btn => {
    const val = parseInt(btn.dataset.val);
    btn.addEventListener('click', () => { _starVal = val; _updateStars(starsRow, _starVal); });
    btn.addEventListener('mouseenter', () => _updateStars(starsRow, val));
    btn.addEventListener('mouseleave', () => _updateStars(starsRow, _starVal));
    btn.addEventListener('touchstart', (e) => {
      e.stopPropagation();
      _starVal = val;
      _updateStars(starsRow, _starVal);
    }, { passive: true });
  });

  document.getElementById('avis-cancel')?.addEventListener('click', () => _closePopup('popup-avis'));
  document.getElementById('avis-confirm')?.addEventListener('click', () => {
    _closePopup('popup-avis');
    if (_starVal >= 4) window.open('https://play.google.com/store/apps/', '_blank');
    else if (_starVal > 0) Toast.info('Merci pour votre avis ! 🙏');
  });
  document.getElementById('popup-avis')?.addEventListener('click', (e) => {
    if (e.target.id === 'popup-avis') _closePopup('popup-avis');
  });

  document.getElementById('contact-close')?.addEventListener('click', () => _closePopup('popup-contact'));
  document.getElementById('popup-contact')?.addEventListener('click', (e) => {
    if (e.target.id === 'popup-contact') _closePopup('popup-contact');
  });
}

function _updateStars(row, val) {
  row.querySelectorAll('.star-btn').forEach((b, i) => {
    b.classList.toggle('active', i < val);
  });
}

// ── Menu hamburger ────────────────────────────────────────

function _initMenu() {
  const overlay  = document.getElementById('menu-overlay');
  const btnOpen  = document.getElementById('btn-menu');
  const btnClose = document.getElementById('menu-close');
  if (!overlay || !btnOpen) return;

  const openMenu  = () => { overlay.hidden = false; };
  const closeMenu = () => { overlay.hidden = true; };

  btnOpen.addEventListener('click', openMenu);
  btnClose?.addEventListener('click', closeMenu);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeMenu(); });

  document.getElementById('menu-partager')?.addEventListener('click', async () => {
    closeMenu();
    try {
      if (navigator.share) await navigator.share({ title: 'Xëtu', url: location.href });
      else { await navigator.clipboard?.writeText(location.href); Toast.info('Lien copié !'); }
    } catch {}
  });

  document.getElementById('menu-cgu')?.addEventListener('click', () => {
    closeMenu();
    Toast.info('Conditions d\'utilisation à venir');
  });

  document.getElementById('menu-avis')?.addEventListener('click', () => {
    closeMenu();
    _openPopup('popup-avis');
  });

  document.getElementById('menu-contact')?.addEventListener('click', () => {
    closeMenu();
    _openPopup('popup-contact');
  });
}

// ── Statut WS ─────────────────────────────────────────────

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
  } catch (err) { console.warn('[App]', err); }
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
      if (!DEMO_MODE) {
        const sub = await isPushSubscribed();
        if (!sub) await subscribeToPush();
      }
    },
    onChatResponse: (text) => store.set('lastBotMessage', text),
    onTyping:       (active) => store.set('chatTyping', active),
    onWelcome:      (_text, suggestions) => {
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

  // SW désactivé en dev local — activé uniquement en prod
  const _isProd = location.hostname !== 'localhost'
               && location.hostname !== '127.0.0.1'
               && location.protocol !== 'file:';

  if ('serviceWorker' in navigator && _isProd) {
    navigator.serviceWorker.register('/sw.js').catch(e => console.warn('[SW]', e));
  } else if ('serviceWorker' in navigator && !_isProd) {
    navigator.serviceWorker.getRegistrations()
      .then(regs => regs.forEach(r => r.unregister()))
      .catch(() => {});
  }

  if (new URLSearchParams(location.search).get('action') === 'report') goTo('signal');
});