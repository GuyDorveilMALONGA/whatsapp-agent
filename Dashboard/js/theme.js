/**
 * js/theme.js — Xëtu V2.0
 * Popup thème depuis le menu hamburger.
 * Pas de bouton flottant — tout passe par menu → "Thème".
 *
 * Intégration dans app.js :
 *   import { initTheme } from './theme.js';
 *   // dans DOMContentLoaded :
 *   initTheme();
 */

const STORAGE_KEY = 'xetu_theme';
const DEFAULT     = 'dark';

// ── Appliquer ─────────────────────────────────────────────

function _apply(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  // Mettre à jour le label dans le menu
  const label = document.getElementById('menu-theme-label');
  if (label) label.textContent = theme === 'light' ? 'Thème · Clair' : 'Thème · Sombre';
  // Mettre à jour les cards dans le popup
  _updatePopupCards(theme);
}

function _updatePopupCards(theme) {
  document.querySelectorAll('.theme-card').forEach(card => {
    card.classList.toggle('theme-card--active', card.dataset.theme === theme);
  });
}

// ── Préférence ────────────────────────────────────────────

function _getPreference() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {}
  if (window.matchMedia?.('(prefers-color-scheme: light)').matches) return 'light';
  return DEFAULT;
}

// ── Popup ─────────────────────────────────────────────────

function _buildPopup() {
  // Ne pas créer deux fois
  if (document.getElementById('popup-theme')) return;

  const overlay = document.createElement('div');
  overlay.className = 'popup-overlay';
  overlay.id        = 'popup-theme';
  overlay.hidden    = true;

  overlay.innerHTML = `
    <div class="popup-card theme-popup-card">
      <div class="popup-title">Apparence</div>
      <div class="popup-sub">Choisis le thème de l'application</div>

      <div class="theme-cards-row">

        <button class="theme-card" data-theme="dark" aria-label="Mode sombre">
          <div class="theme-card-preview theme-preview--dark">
            <div class="theme-preview-header"></div>
            <div class="theme-preview-body">
              <div class="theme-preview-bar"></div>
              <div class="theme-preview-bar theme-preview-bar--short"></div>
            </div>
            <div class="theme-preview-dot"></div>
          </div>
          <div class="theme-card-label">
            <span class="theme-card-icon">🌙</span>
            Sombre
          </div>
          <div class="theme-card-check">✓</div>
        </button>

        <button class="theme-card" data-theme="light" aria-label="Mode clair — Dakar">
          <div class="theme-card-preview theme-preview--light">
            <div class="theme-preview-header"></div>
            <div class="theme-preview-body">
              <div class="theme-preview-bar"></div>
              <div class="theme-preview-bar theme-preview-bar--short"></div>
            </div>
            <div class="theme-preview-dot"></div>
          </div>
          <div class="theme-card-label">
            <span class="theme-card-icon">☀️</span>
            Clair
          </div>
          <div class="theme-card-check">✓</div>
        </button>

      </div>

      <button class="popup-btn popup-btn--cancel" id="theme-popup-close">Fermer</button>
    </div>
  `;

  document.body.appendChild(overlay);

  // Fermer en cliquant hors de la card
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) _closePopup();
  });
  document.getElementById('theme-popup-close').addEventListener('click', _closePopup);

  // Sélection d'un thème
  overlay.querySelectorAll('.theme-card').forEach(card => {
    card.addEventListener('click', () => {
      const theme = card.dataset.theme;
      _apply(theme);
      try { localStorage.setItem(STORAGE_KEY, theme); } catch {}
    });
  });
}

function _openPopup() {
  const overlay = document.getElementById('popup-theme');
  if (overlay) {
    overlay.hidden = false;
    _updatePopupCards(
      document.documentElement.getAttribute('data-theme') || DEFAULT
    );
  }
}

function _closePopup() {
  const overlay = document.getElementById('popup-theme');
  if (overlay) overlay.hidden = true;
}

// ── Init publique ─────────────────────────────────────────

export function initTheme() {
  // 1. Construire le popup
  _buildPopup();

  // 2. Appliquer la préférence
  const pref = _getPreference();
  _apply(pref);

  // 3. Brancher le bouton menu
  const menuBtn = document.getElementById('menu-theme-btn');
  if (menuBtn) {
    menuBtn.addEventListener('click', () => {
      // Fermer le menu avant d'ouvrir le popup
      const menuOverlay = document.getElementById('menu-overlay');
      if (menuOverlay) menuOverlay.hidden = true;
      setTimeout(_openPopup, 120); // micro-délai pour l'animation menu
    });
  }

  // 4. Réagir aux changements OS
  try {
    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
      try {
        if (!localStorage.getItem(STORAGE_KEY)) _apply(e.matches ? 'light' : 'dark');
      } catch {
        _apply(e.matches ? 'light' : 'dark');
      }
    });
  } catch {}
}

export function getTheme() {
  return document.documentElement.getAttribute('data-theme') || DEFAULT;
}
