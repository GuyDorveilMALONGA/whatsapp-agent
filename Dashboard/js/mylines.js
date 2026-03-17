/**
 * js/mylines.js — V2.1
 * Page Mes lignes redesignée : couleurs, abonnements avec noms, score visuel.
 */

import * as store from './store.js';
import { LIGNES_CONNUES, LIGNE_NAMES, SESSION_PREFIX } from './constants.js';
import { generateUUID } from './utils.js';

const SESSION_ID = (() => {
  try {
    let id = sessionStorage.getItem('xetu_session_id');
    if (!id) { id = `${SESSION_PREFIX}${generateUUID()}`; sessionStorage.setItem('xetu_session_id', id); }
    return id;
  } catch { return `${SESSION_PREFIX}${generateUUID()}`; }
})();

export function initMylines() {
  _renderSubscriptions();
  _renderScore();
  _initSubscribeModal();
  store.subscribe('userScore', (s) => _renderScore(s));
}

// ── Abonnements ───────────────────────────────────────────

function _getSubs() {
  try { return JSON.parse(localStorage.getItem('xetu_subscriptions') || '[]'); }
  catch { return []; }
}

function _saveSubs(list) {
  try { localStorage.setItem('xetu_subscriptions', JSON.stringify(list)); }
  catch {}
}

function _renderSubscriptions() {
  const subs = _getSubs();
  const el   = document.getElementById('subscriptions-list');
  if (!el) return;

  if (!subs.length) {
    el.innerHTML = `<div class="mylines-empty-state">
      <div class="mylines-empty-icon">🔔</div>
      <div class="mylines-empty-text">Aucun abonnement</div>
      <div class="mylines-empty-hint">Abonne-toi pour recevoir des alertes quand un bus est signalé</div>
    </div>`;
    return;
  }

  el.innerHTML = subs.map((ligne, i) => {
    const name = LIGNE_NAMES[ligne] || `Ligne ${ligne}`;
    return `<div class="myline-card anim-up" style="animation-delay:${i*0.05}s">
      <div class="myline-badge-wrap">
        <span class="myline-badge">Bus ${ligne}</span>
      </div>
      <div class="myline-info">
        <div class="myline-name">${name}</div>
        <div class="myline-sub-label">🔔 Alertes actives</div>
      </div>
      <button class="myline-remove" data-ligne="${ligne}" aria-label="Se désabonner de ${ligne}">×</button>
    </div>`;
  }).join('');

  el.querySelectorAll('.myline-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      const updated = _getSubs().filter(l => l !== btn.dataset.ligne);
      _saveSubs(updated);
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
    if (searchInput) searchInput.value = '';
    _renderSubscribeLines('');
  });
  btnCancel?.addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });
  searchInput?.addEventListener('input', () => _renderSubscribeLines(searchInput.value.trim().toLowerCase()));
}

function _renderSubscribeLines(filter) {
  const container = document.getElementById('subscribe-lines');
  if (!container) return;
  const subs = _getSubs();
  const all  = [...LIGNES_CONNUES].sort((a, b) => {
    const na = parseFloat(a), nb = parseFloat(b);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return a.localeCompare(b);
  });
  const filtered = filter ? all.filter(l => l.toLowerCase().includes(filter) || (LIGNE_NAMES[l] || '').toLowerCase().includes(filter)) : all;

  container.innerHTML = filtered.map(l => {
    const isSub = subs.includes(l);
    return `<button class="subscribe-chip${isSub ? ' subscribed' : ''}" data-ligne="${l}">${l}</button>`;
  }).join('');

  container.querySelectorAll('.subscribe-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const ligne   = btn.dataset.ligne;
      let   current = _getSubs();
      if (current.includes(ligne)) {
        current = current.filter(l => l !== ligne);
        btn.classList.remove('subscribed');
      } else {
        current = [...current, ligne];
        btn.classList.add('subscribed');
      }
      _saveSubs(current);
      _renderSubscriptions();
    });
  });
}

// ── Score ─────────────────────────────────────────────────

function _getScore() {
  try { return parseInt(localStorage.getItem('xetu_score') || '0', 10); }
  catch { return 0; }
}

function _getBadge(s) {
  if (s >= 100) return { label: 'Légende', emoji: '🏆', color: '#FFD700' };
  if (s >= 50)  return { label: 'Expert',  emoji: '⭐', color: '#FF6B35' };
  if (s >= 20)  return { label: 'Régulier',emoji: '🔥', color: '#FF6B35' };
  if (s >= 5)   return { label: 'Actif',   emoji: '👍', color: '#00D67F' };
  return            { label: 'Nouveau',    emoji: '🌱', color: '#6B7A99' };
}

function _renderScore(score) {
  const s     = score ?? _getScore();
  const badge = _getBadge(s);
  const card  = document.getElementById('score-card');
  if (!card) return;

  card.innerHTML = `
    <div class="score-top">
      <div class="score-circle" style="border-color:${badge.color}">
        <div class="score-number" style="color:${badge.color}">${s}</div>
        <div class="score-unit">signalements</div>
      </div>
    </div>
    <div class="score-badge-row">
      <span class="score-badge" style="background:${badge.color}22;color:${badge.color};border-color:${badge.color}44">
        ${badge.emoji} ${badge.label}
      </span>
    </div>
    <div class="score-progress-wrap">
      ${_renderProgress(s)}
    </div>
    <div class="score-message">${_getMessage(s)}</div>
  `;
}

function _renderProgress(s) {
  const levels = [
    { label: 'Actif',    min: 5,   color: '#00D67F' },
    { label: 'Régulier', min: 20,  color: '#FF6B35' },
    { label: 'Expert',   min: 50,  color: '#FF6B35' },
    { label: 'Légende',  min: 100, color: '#FFD700' },
  ];
  const next = levels.find(l => s < l.min);
  if (!next) return `<div class="score-progress-text" style="color:#FFD700">🏆 Niveau maximum atteint !</div>`;

  const prev = levels[levels.indexOf(next) - 1];
  const from = prev ? prev.min : 0;
  const pct  = Math.min(100, Math.round(((s - from) / (next.min - from)) * 100));

  return `
    <div class="score-progress-text">Encore ${next.min - s} signalement${next.min - s > 1 ? 's' : ''} pour devenir <b>${next.label}</b></div>
    <div class="score-progress-bar">
      <div class="score-progress-fill" style="width:${pct}%;background:${next.color}"></div>
    </div>`;
}

function _getMessage(s) {
  if (s === 0) return 'Commence à signaler pour aider la communauté !';
  if (s < 5)  return 'Bien démarré ! Continue comme ça 💪';
  if (s < 20) return 'Tu aides déjà beaucoup de Dakarois !';
  if (s < 50) return 'Tu es un pilier de la communauté Xëtu !';
  if (s < 100)return 'Incroyable ! Tu es une référence à Dakar 🚌';
  return 'Légende vivante du transport dakarois ! 🏆';
}

export function incrementScore() {
  try {
    const s = _getScore() + 1;
    localStorage.setItem('xetu_score', String(s));
    store.set('userScore', s);
  } catch {}
}
