/**
 * js/mylines.js — V1.0
 * Écran "Mes lignes" : 2-3 lignes favorites + espace pub.
 * Les favoris sont sauvegardés en localStorage par signal.js.
 */

import * as store from './store.js';
import { LIGNE_NAMES } from './constants.js';

const MAX_FAVS = 3;

// ── Init ─────────────────────────────────────────────────

export function initMylines() {
  _loadAndRender();
  store.subscribe('favLines', () => _loadAndRender());
}

// ── Chargement depuis localStorage ───────────────────────

function _getFavLines() {
  try {
    const raw = localStorage.getItem('xetu_fav_lines') || '[]';
    return JSON.parse(raw).slice(0, MAX_FAVS);
  } catch {
    return [];
  }
}

function _removeFavLine(ligne) {
  try {
    const raw  = localStorage.getItem('xetu_fav_lines') || '[]';
    const favs = JSON.parse(raw).filter(l => l !== ligne);
    localStorage.setItem('xetu_fav_lines', JSON.stringify(favs));
    store.set('favLines', favs.slice(0, MAX_FAVS));
  } catch { /* localStorage bloqué */ }
}

// ── Rendu ─────────────────────────────────────────────────

function _loadAndRender() {
  const favs = _getFavLines();
  const el   = document.getElementById('mylines-list');
  if (!el) return;

  if (!favs.length) {
    el.innerHTML = `<div class="mylines-empty">
      Tes lignes favorites apparaîtront ici.<br>
      Signale un bus pour commencer !
    </div>`;
    return;
  }

  el.innerHTML = favs.map((ligne, i) => {
    const name = LIGNE_NAMES[ligne] || `Ligne ${ligne}`;
    return `<div class="myline-card anim-up" style="animation-delay:${i * 0.06}s">
      <span class="myline-badge">Bus ${ligne}</span>
      <div class="myline-info">
        <div class="myline-name">${name}</div>
      </div>
      <button class="myline-remove" data-ligne="${ligne}" aria-label="Supprimer ${ligne} des favoris">×</button>
    </div>`;
  }).join('');

  el.querySelectorAll('.myline-remove').forEach(btn => {
    btn.addEventListener('click', () => _removeFavLine(btn.dataset.ligne));
  });
}
