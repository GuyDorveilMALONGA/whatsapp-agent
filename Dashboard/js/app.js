/**
 * js/app.js — V2.4
 * V2.4 : Remplacement du compte à rebours par indicateur "En direct"
 *        _startTimer() pilote .live-indicator via états loading/online/offline
 */

import * as store   from './store.js';
import * as Toast   from './toast.js';
import * as Ws      from './ws.js';
import { REFRESH_SEC, API_BASE } from './constants.js';
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
const DEMO_MODE = false;

// ── Navigation ────────────────────────────────────────────

export function goTo(screenId) {
  _screens.forEach(s => s.classList.remove('active'));
  if (NAV_SCREENS.includes(screenId)) {
    _navBtns.forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-screen="${screenId}"]`)?.classList.add('active');
  }
  document.getElementById(`screen-${screenId}`)?.classList.add('active');
  if (screenId === 'signal') signalScreenEnter();
}

_navBtns.forEach(btn => btn.addEventListener('click', () => goTo(btn.dataset.screen)));
document.getElementById('btn-back-signal')?.addEventListener('click', () => goTo('home'));

// ── Live indicator ─────────────────────────────────────────

function _setLive(state) {
  const el = document.getElementById('live-indicator');
  if (!el) return;
  el.className = 'live-indicator' + (state !== 'online' ? ` live-indicator--${state}` : '');
  el.querySelector('.live-dot-inner')?.setAttribute('data-state', state);
  if (state === 'loading') {
    el.lastChild.textContent = 'sync…';
  } else if (state === 'offline') {
    const last = localStorage.getItem('xetu_last_update');
    el.lastChild.textContent = last ? `offline · ${last}` : 'offline';
  } else {
    el.lastChild.textContent = 'live';
  }
}

// ── Push conditionnel ────────────────────────────────────

async function _maybeSubscribePush() {
  try {
    // Vérifier d'abord si déjà abonné
    const alreadySub = await isPushSubscribed();
    if (alreadySub) return;

    // Vérifier si l'utilisateur a des lignes abonnées
    const SESSION_ID = sessionStorage.getItem('xetu_session_id') || '';
    if (!SESSION_ID) return;

    const res = await fetch(`${API_BASE}/api/subscriptions?session_id=${encodeURIComponent(SESSION_ID)}`);
    if (!res.ok) return;
    const { lignes } = await res.json();

    if (!lignes || lignes.length === 0) {
      console.log('[Push] Pas de lignes abonnées — push différé');
      return;
    }

    console.log('[Push] Lignes actives détectées — demande permission push');

    // Écouter l'événement iOS
    window.addEventListener('xetu:push-ios-required', () => {
      Toast.info("Ajoute Xetu a l'ecran d'accueil pour activer les alertes push");
    }, { once: true });

    await subscribeToPush();
  } catch (e) {
    console.warn('[Push] _maybeSubscribePush error:', e);
  }
}

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

// ── Timer → Live indicator ────────────────────────────────

let _timerCount = REFRESH_SEC;
let _timerInt   = null;

function _startTimer() {
  clearInterval(_timerInt);
  _timerCount = REFRESH_SEC;
  _setLive('online');

  _timerInt = setInterval(async () => {
    _timerCount--;
    if (_timerCount <= 0) {
      _setLive('loading');
      const ok = await _loadData();
      _timerCount = REFRESH_SEC;
      _setLive(ok ? 'online' : 'offline');
    }
  }, 1000);
}

// ── Données ───────────────────────────────────────────────

// Retourne true si succès, false si erreur
async function _loadData() {
  try {
    const [busRes, lbRes] = await Promise.allSettled([fetchBuses(), fetchLeaderboard()]);

    if (busRes.status === 'fulfilled') {
      // Succès réseau — mettre à jour store + timestamp
      store.set('buses', busRes.value.buses || []);
      try {
        localStorage.setItem(
          'xetu_last_update',
          new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
        );
      } catch {}
    } else {
      // Réseau KO — le SW a déjà tenté le cache dans fetchBuses().
      // On garde les données actuelles du store (dernière valeur connue)
      // et on notifie l'utilisateur avec le timestamp du dernier succès.
      console.warn('[App] fetchBuses échoué — mode offline');
      const lastUpdate = localStorage.getItem('xetu_last_update');
      const msg = lastUpdate
        ? `Hors ligne — dernière mise à jour à ${lastUpdate}`
        : 'Hors ligne — données non disponibles';
      Toast.error(msg);
      // Ne pas écraser le store — les données précédentes restent affichées
    }

    const lbData = lbRes.status === 'fulfilled' ? lbRes.value : { leaderboard: [], stats: {} };
    store.set('leaderboard', lbData.leaderboard || []);
    store.set('stats',       lbData.stats || {});

    return busRes.status === 'fulfilled';
  } catch (err) {
    console.warn('[App]', err);
    return false;
  }
}

// ── Init ──────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  _initMenu();
  _initPopups();

  initHome({ onSeeBus: () => goTo('signal'), onGeoError: (msg) => Toast.error(msg) });
  initSignal({ onSuccess: () => { goTo('home'); _loadData(); } });
  initChat();
  initMylines();

  Ws.init({
    onOpen: async () => {
      _updateWsStatus('open');
      store.set('wsStatus', 'open');
      if (!DEMO_MODE) {
        // Abonner aux push uniquement si l'utilisateur a des lignes actives
        // Évite la popup permission au premier lancement sans contexte
        _maybeSubscribePush();
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

  const ok = await _loadData();
  _setLive(ok ? 'online' : 'offline');
  _startTimer();

  window.addEventListener('online',  () => { Toast.info('Connexion rétablie ✅'); _setLive('online'); });
  window.addEventListener('offline', () => { Toast.error('Hors ligne'); _setLive('offline'); });

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