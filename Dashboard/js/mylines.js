/**
 * js/mylines.js — V2.0 Sprint Final
 * 2 sections : abonnements lignes + score signalements.
 */

import * as store from './store.js';
import { LIGNES_CONNUES, LIGNE_NAMES, API_BASE, SESSION_PREFIX } from './constants.js';
import { generateUUID } from './utils.js';

const SESSION_ID = (() => {
  try {
    let id = sessionStorage.getItem('xetu_session_id');
    if (!id) { id = `${SESSION_PREFIX}${generateUUID()}`; sessionStorage.setItem('xetu_session_id', id); }
    return id;
  } catch { return `${SESSION_PREFIX}${generateUUID()}`; }
})();

// ── Init ──────────────────────────────────────────────────

export function initMylines() {
  _renderSubscriptions();
  _renderScore();
  _initSubscribeModal();

  store.subscribe('favLines',     () => _renderSubscriptions());
  store.subscribe('userScore',    (s) => _renderScore(s));
  store.subscribe('buses',        () => _refreshScore());
}

// ── Section 1 : Abonnements ───────────────────────────────

function _getSubscriptions() {
  try { return JSON.parse(localStorage.getItem('xetu_subscriptions') || '[]'); }
  catch { return []; }
}

function _saveSubscriptions(list) {
  try { localStorage.setItem('xetu_subscriptions', JSON.stringify(list)); }
  catch {}
}

function _renderSubscriptions() {
  const subs = _getSubscriptions();
  const el   = document.getElementById('subscriptions-list');
  if (!el) return;

  if (!subs.length) {
    el.innerHTML = `<div class="mylines-empty">Aucun abonnement.<br>Abonne-toi à une ligne pour recevoir des alertes.</div>`;
    return;
  }

  el.innerHTML = subs.map((ligne, i) => {
    const name = LIGNE_NAMES[ligne] || `Ligne ${ligne}`;
    return `<div class="myline-card anim-up" style="animation-delay:${i*0.05}s">
      <span class="myline-badge">Bus ${ligne}</span>
      <div class="myline-info"><div class="myline-name">${name}</div></div>
      <button class="myline-remove" data-ligne="${ligne}" aria-label="Se désabonner">×</button>
    </div>`;
  }).join('');

  el.querySelectorAll('.myline-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      const updated = _getSubscriptions().filter(l => l !== btn.dataset.ligne);
      _saveSubscriptions(updated);
      _renderSubscriptions();
    });
  });
}

// ── Modal abonnement ──────────────────────────────────────

function _initSubscribeModal() {
  const modal      = document.getElementById('subscribe-modal');
  const btnOpen    = document.getElementById('btn-subscribe');
  const btnCancel  = document.getElementById('subscribe-cancel');
  const searchInput= document.getElementById('subscribe-search');
  if (!modal || !btnOpen) return;

  btnOpen.addEventListener('click', () => {
    modal.hidden = false;
    _renderSubscribeLines('');
  });

  btnCancel?.addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });

  searchInput?.addEventListener('input', () => {
    _renderSubscribeLines(searchInput.value.trim().toLowerCase());
  });
}

function _renderSubscribeLines(filter) {
  const container = document.getElementById('subscribe-lines');
  if (!container) return;

  const subs = _getSubscriptions();
  const all  = [...LIGNES_CONNUES].sort((a, b) => {
    const na = parseFloat(a), nb = parseFloat(b);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return a.localeCompare(b);
  });

  const filtered = filter ? all.filter(l => l.toLowerCase().includes(filter)) : all;

  container.innerHTML = filtered.map(l => {
    const isSub = subs.includes(l);
    return `<button class="subscribe-chip${isSub ? ' subscribed' : ''}" data-ligne="${l}">${l}</button>`;
  }).join('');

  container.querySelectorAll('.subscribe-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const ligne   = btn.dataset.ligne;
      let   current = _getSubscriptions();
      if (current.includes(ligne)) {
        current = current.filter(l => l !== ligne);
        btn.classList.remove('subscribed');
      } else {
        current = [...current, ligne];
        btn.classList.add('subscribed');
      }
      _saveSubscriptions(current);
      _renderSubscriptions();
    });
  });
}

// ── Section 2 : Score ─────────────────────────────────────

function _getScore() {
  try { return parseInt(localStorage.getItem('xetu_score') || '0', 10); }
  catch { return 0; }
}

function _getBadge(score) {
  if (score >= 100) return 'Légende 🏆';
  if (score >= 50)  return 'Expert ⭐';
  if (score >= 20)  return 'Régulier 🔥';
  if (score >= 5)   return 'Actif 👍';
  return 'Nouveau';
}

function _renderScore(score) {
  const s = score ?? _getScore();
  const numEl   = document.getElementById('score-number');
  const badgeEl = document.getElementById('score-badge');
  if (numEl)   numEl.textContent   = s;
  if (badgeEl) badgeEl.textContent = _getBadge(s);
}

function _refreshScore() {
  _renderScore(_getScore());
}

// Incrémenter le score quand un signalement est envoyé
export function incrementScore() {
  try {
    const s = _getScore() + 1;
    localStorage.setItem('xetu_score', String(s));
    store.set('userScore', s);
  } catch {}
}
