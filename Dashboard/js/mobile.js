/**
 * js/mobile.js
 * Bottom sheet mobile — 3 états, drag, scroll interne, clavier virtuel.
 *
 * États :
 *   peek  → 64px visible (handle + résumé)
 *   half  → 45vh
 *   full  → 90vh
 *
 * Dépend de : store.js, utils.js
 * RÈGLE : ne parle jamais à map.js, ui.js, chat.js directement.
 *         Tout passe par store.js.
 */

import * as store from './store.js';
import { getAgeClass, formatAge } from './utils.js';

// ── Constantes ────────────────────────────────────────────

const PEEK_HEIGHT  = 88;    // px — handle + résumé + bouton signaler
const HALF_HEIGHT  = 0.45;  // % de la fenêtre
const FULL_HEIGHT  = 0.90;  // % de la fenêtre

const VELOCITY_THRESHOLD  = 0.5;  // px/ms — snap au prochain état
const POSITION_THRESHOLD  = 0.30; // 30% entre deux snaps → snap

// ── État interne ──────────────────────────────────────────

let _sheet        = null;
let _handle       = null;
let _content      = null;
let _summary      = null;
let _tabs         = null;
let _currentState = 'peek'; // 'peek' | 'half' | 'full'
let _isDragging   = false;
let _startY       = 0;
let _startTranslate = 0;
let _lastY        = 0;
let _lastTime     = 0;
let _velocity     = 0;
let _rafId        = null;
let _onBusSelect  = null;

// ── INIT ─────────────────────────────────────────────────

export function init(onBusSelect) {
  // Uniquement sur mobile
  if (window.innerWidth > 768) return;

  _onBusSelect = onBusSelect;
  _sheet   = document.getElementById('bottom-sheet');
  _handle  = document.getElementById('sheet-handle');
  _content = document.getElementById('sheet-content');
  _summary = document.getElementById('sheet-summary');
  _tabs    = _sheet?.querySelector('.sheet-tabs');

  if (!_sheet || !_handle) return;

  // Performance : will-change uniquement pendant le drag
  _sheet.style.willChange = 'transform';

  _snapTo('peek', false);
  _attachDragEvents();
  _attachTabEvents();
  _attachKeyboardEvents();
  _subscribeStore();
}

// ── STORE SUBSCRIPTIONS ───────────────────────────────────

function _subscribeStore() {
  store.subscribe('buses', (buses) => {
    const line   = store.get('filteredLine');
    const filtered = line ? buses.filter(b => b.ligne === line) : buses;
    _updateSummary(filtered.length);
    _renderBusList(filtered);
  });

  store.subscribe('filteredLine', (line) => {
    const buses    = store.get('buses');
    const filtered = line ? buses.filter(b => b.ligne === line) : buses;
    _updateSummary(filtered.length);
    _renderBusList(filtered);
  });

  store.subscribe('selectedBus', (bus) => {
    if (bus && _currentState === 'peek') {
      _snapTo('half');
    }
    _highlightSelectedCard(bus?.id);
  });

  store.subscribe('mobileSheetState', (state) => {
    if (state && state !== _currentState) _snapTo(state);
  });
}

// ── DRAG — TOUCH EVENTS ───────────────────────────────────

function _attachDragEvents() {
  // Touch sur le handle uniquement pour ouvrir depuis peek
  _handle.addEventListener('touchstart', _onTouchStart, { passive: true });

  // Touch sur le sheet entier (géré via scroll vs drag)
  _sheet.addEventListener('touchstart', _onSheetTouchStart, { passive: true });
  _sheet.addEventListener('touchmove',  _onSheetTouchMove,  { passive: false });
  _sheet.addEventListener('touchend',   _onSheetTouchEnd,   { passive: true });

  // Clic sur le handle = toggle peek/half
  _handle.addEventListener('click', _onHandleClick);
}

function _onHandleClick() {
  if (_currentState === 'peek') _snapTo('half');
  else if (_currentState === 'half') _snapTo('peek');
  // full → on ne colle pas au clic (laisse le drag)
}

function _onTouchStart(e) {
  _startDrag(e.touches[0].clientY);
}

function _onSheetTouchStart(e) {
  // Ignorer les touches venant du chat ou des boutons interactifs
  const tag = e.target.tagName;
  if (tag === 'BUTTON' || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'A') return;
  const chatWindow = document.getElementById('chat-window');
  if (chatWindow && chatWindow.contains(e.target)) return;

  _startDrag(e.touches[0].clientY);
}

function _startDrag(clientY) {
  _isDragging   = true;
  _startY       = clientY;
  _lastY        = clientY;
  _lastTime     = Date.now();
  _velocity     = 0;
  _startTranslate = _getCurrentTranslate();

  // Désactiver la transition pendant le drag
  _sheet.style.transition = 'none';
}

function _onSheetTouchMove(e) {
  if (!_isDragging) return;

  const touch    = e.touches[0];
  const clientY  = touch.clientY;
  const deltaY   = clientY - _startY;
  const now      = Date.now();

  // Calcul vélocité
  const dt = now - _lastTime;
  if (dt > 0) {
    _velocity = (clientY - _lastY) / dt; // px/ms, positif = vers le bas
  }
  _lastY    = clientY;
  _lastTime = now;

  // Déterminer si on doit drag ou scroller
  const scrollTop = _content?.scrollTop ?? 0;

  if (_currentState === 'full' || _currentState === 'half') {
    const isInsideContent = _content && _content.contains(e.target);

    if (isInsideContent) {
      if (deltaY < 0) {
        // Scroll vers le bas du contenu → jamais un drag
        _isDragging = false;
        return;
      }
      if (deltaY > 0 && scrollTop > 0) {
        // Glisse vers le bas mais contenu pas encore en haut → scroll natif
        _isDragging = false;
        return;
      }
      // deltaY > 0 et scrollTop === 0 → drag vers le bas autorisé (fermer le sheet)
    }
  }

  e.preventDefault();

  const maxTranslate = window.innerHeight - PEEK_HEIGHT; // ne jamais descendre sous le peek
  const newTranslate = Math.min(maxTranslate, Math.max(0, _startTranslate + deltaY));

  if (_rafId) cancelAnimationFrame(_rafId);
  _rafId = requestAnimationFrame(() => {
    _sheet.style.transform = `translateY(${newTranslate}px)`;
  });
}

function _onSheetTouchEnd() {
  if (!_isDragging) return;
  _isDragging = false;
  if (_rafId) cancelAnimationFrame(_rafId);

  const currentTranslate = _getCurrentTranslate();
  const windowH          = window.innerHeight;

  // Positions absolues des snaps (translateY depuis le bas)
  const snapPeek = windowH - PEEK_HEIGHT;
  const snapHalf = windowH - windowH * HALF_HEIGHT;
  const snapFull = windowH - windowH * FULL_HEIGHT;

  let target;

  // Snap par vélocité
  if (_velocity > VELOCITY_THRESHOLD) {
    // Glisse vers le bas → minimum peek (jamais complètement caché)
    target = _currentState === 'full' ? 'half' : 'peek';
  } else if (_velocity < -VELOCITY_THRESHOLD) {
    // Glisse vers le haut → état supérieur
    target = _currentState === 'peek' ? 'half'
           : _currentState === 'half' ? 'full'
           : 'full';
  } else {
    // Snap par position — trouver le snap le plus proche
    const distances = [
      { state: 'peek', dist: Math.abs(currentTranslate - snapPeek) },
      { state: 'half', dist: Math.abs(currentTranslate - snapHalf) },
      { state: 'full', dist: Math.abs(currentTranslate - snapFull) },
    ];
    distances.sort((a, b) => a.dist - b.dist);
    target = distances[0].state;
  }

  _snapTo(target);
}

// ── SNAP ─────────────────────────────────────────────────

function _snapTo(state, animate = true) {
  _currentState = state;
  store.set('mobileSheetState', state);

  const windowH   = window.innerHeight;
  let translateY;

  if (state === 'peek') {
    translateY = windowH - PEEK_HEIGHT;
  } else if (state === 'half') {
    translateY = windowH - windowH * HALF_HEIGHT;
  } else {
    translateY = windowH - windowH * FULL_HEIGHT;
  }

  if (animate) {
    _sheet.style.transition = 'transform 0.3s cubic-bezier(0.34, 1.2, 0.64, 1)';
  } else {
    _sheet.style.transition = 'none';
  }

  requestAnimationFrame(() => {
    _sheet.style.transform = `translateY(${translateY}px)`;
  });

  // Scroll interne : remettre à 0 si on ferme
  if (state === 'peek' && _content) {
    _content.scrollTop = 0;
  }

  // touch-action sur le handle
  _handle.style.touchAction = 'none';
}

// ── CLAVIER VIRTUEL ───────────────────────────────────────

function _attachKeyboardEvents() {
  if (!window.visualViewport) return;

  window.visualViewport.addEventListener('resize', () => {
    // Si le chat est ouvert, il gère le clavier lui-même → ne pas toucher le sheet
    const chatWin = document.getElementById('chat-window');
    if (chatWin && chatWin.classList.contains('chat-window--open')) return;

    const vvHeight = window.visualViewport.height;
    const windowH  = window.innerHeight;

    if (vvHeight < windowH * 0.85) {
      // Clavier ouvert → passer en full pour que l'input reste visible
      _snapTo('full');
    } else {
      // Clavier fermé → revenir à half si on était en full à cause du clavier
      if (_currentState === 'full') _snapTo('half');
    }
  });
}

// ── TABS ─────────────────────────────────────────────────

function _attachTabEvents() {
  if (!_tabs) return;

  _tabs.querySelectorAll('.sheet-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      _tabs.querySelectorAll('.sheet-tab-btn').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');

      const tab = btn.dataset.sheetTab;
      _renderTab(tab);

      // Ouvrir le sheet si en peek
      if (_currentState === 'peek') _snapTo('half');
    });
  });
}

function _renderTab(tab) {
  const buses    = store.get('buses');
  const line     = store.get('filteredLine');
  const filtered = line ? buses.filter(b => b.ligne === line) : buses;

  if (tab === 'buses') {
    _renderBusList(filtered);
  } else if (tab === 'leaderboard') {
    _renderLeaderboard();
  }
}

// ── RENDU BUS LIST ────────────────────────────────────────

function _updateSummary(count) {
  if (!_summary) return;
  _summary.textContent = count > 0
    ? `${count} bus actif${count > 1 ? 's' : ''}`
    : 'Aucun bus actif';
}

function _renderBusList(buses) {
  // Vérifier que l'onglet actif est "buses"
  const activeTab = _tabs?.querySelector('.sheet-tab-btn.active')?.dataset.sheetTab;
  if (activeTab && activeTab !== 'buses') return;
  if (!_content) return;

  _content.innerHTML = '';

  if (!buses || buses.length === 0) {
    _content.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-text">Aucun bus actif sur cette ligne.</div>
        <button class="empty-action" onclick="window._resetFilter()">
          Voir toutes les lignes
        </button>
      </div>`;
    return;
  }

  const selectedId = store.get('selectedBus')?.id;

  buses.forEach(bus => {
    const card = _buildBusCard(bus, selectedId === bus.id);
    _content.appendChild(card);
  });
}

function _buildBusCard(bus, isSelected) {
  const div = document.createElement('div');
  div.className = `bus-card${isSelected ? ' selected' : ''}`;
  div.id = `sheet-card-${bus.id}`;
  div.setAttribute('role', 'button');
  div.setAttribute('tabindex', '0');
  div.setAttribute('aria-label', `Bus ${bus.ligne} à ${bus.position}, ${formatAge(bus.minutes_ago)}`);

  const ageClass = getAgeClass(bus.minutes_ago);
  const ageLabel = formatAge(bus.minutes_ago);

  div.innerHTML = `
    <div class="bus-card-header">
      <div class="bus-badge">${bus.ligne}</div>
      <div class="bus-name">${bus.name}</div>
      <div class="bus-age ${ageClass}">${ageLabel}</div>
    </div>
    <div class="bus-position">📍 ${bus.position}</div>
    <div class="bus-reporter">Signalé par ${bus.reporter}</div>
  `;

  div.addEventListener('click', () => {
    if (_onBusSelect) _onBusSelect(bus.id);
    _snapTo('peek');
  });

  div.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); div.click(); }
  });

  return div;
}

function _highlightSelectedCard(busId) {
  if (!_content) return;
  _content.querySelectorAll('.bus-card').forEach(c => c.classList.remove('selected'));
  const card = document.getElementById(`sheet-card-${busId}`);
  if (card) {
    card.classList.add('selected');
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

// ── RENDU LEADERBOARD ─────────────────────────────────────

function _renderLeaderboard() {
  if (!_content) return;
  _content.innerHTML = '';

  // Récupère les données via store si disponibles,
  // sinon affiche un état vide propre
  const empty = `
    <div class="empty-state">
      <div class="empty-icon">🏆</div>
      <div class="empty-text">Chargement du classement...</div>
    </div>`;
  _content.innerHTML = empty;

  // Les données leaderboard ne sont pas dans le store actuellement.
  // Elles seront injectées par app.js via injectLeaderboard().
}

export function injectLeaderboard(users) {
  const activeTab = _tabs?.querySelector('.sheet-tab-btn.active')?.dataset.sheetTab;
  if (activeTab !== 'leaderboard' || !_content) return;

  _content.innerHTML = '';

  if (!users || users.length === 0) {
    _content.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🏆</div>
        <div class="empty-text">Aucun contributeur pour l'instant.</div>
      </div>`;
    return;
  }

  users.forEach((user, i) => {
    const div = document.createElement('div');
    div.className = 'lb-item';
    const rank = i + 1;
    const rankClass  = rank === 1 ? 'gold' : rank === 2 ? 'silver' : rank === 3 ? 'bronze' : 'other';
    const rankSymbol = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : String(rank);

    div.innerHTML = `
      <div class="lb-rank ${rankClass}">${rankSymbol}</div>
      <div class="lb-avatar">${user.avatar}</div>
      <div class="lb-info">
        <div class="lb-name">${user.name}</div>
        <div class="lb-zone">📍 ${user.zone}</div>
      </div>
      <div class="lb-score">
        <div class="lb-count">${user.count}</div>
        <div class="lb-unit">signalements</div>
      </div>
    `;
    _content.appendChild(div);
  });
}

// ── HELPERS ───────────────────────────────────────────────

function _getCurrentTranslate() {
  const transform = _sheet.style.transform;
  const match = transform.match(/translateY\((.+)px\)/);
  return match ? parseFloat(match[1]) : window.innerHeight - PEEK_HEIGHT;
}

// ── API PUBLIQUE ──────────────────────────────────────────

export function snapTo(state) {
  _snapTo(state);
}

export function getState() {
  return _currentState;
}