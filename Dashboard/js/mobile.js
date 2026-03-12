/**
 * js/mobile.js
 * Bottom sheet mobile — 3 états, drag, scroll interne, clavier virtuel.
 *
 * États :
 *   peek  → 100px visible (handle + résumé + bouton signaler)
 *   half  → 45vh
 *   full  → 90vh
 *
 * Dépend de : store.js, utils.js
 */

import * as store from './store.js';
import { getAgeClass, formatAge } from './utils.js';

// ── Constantes ────────────────────────────────────────────

const PEEK_HEIGHT         = 100;
const HALF_HEIGHT         = 0.45;
const FULL_HEIGHT         = 0.90;
const VELOCITY_THRESHOLD  = 0.5;
const POSITION_THRESHOLD  = 0.30;

// ── État interne ──────────────────────────────────────────

let _sheet          = null;
let _handle         = null;
let _content        = null;
let _summary        = null;
let _tabs           = null;
let _currentState   = 'peek';
let _isDragging     = false;
let _startY         = 0;
let _startTranslate = 0;
let _lastY          = 0;
let _lastTime       = 0;
let _velocity       = 0;
let _rafId          = null;
let _onBusSelect    = null;

// ── INIT ─────────────────────────────────────────────────

export function init(onBusSelect) {
  if (window.innerWidth > 768) return;

  _onBusSelect = onBusSelect;
  _sheet   = document.getElementById('bottom-sheet');
  _handle  = document.getElementById('sheet-handle');
  _content = document.getElementById('sheet-content');
  _summary = document.getElementById('sheet-summary');
  _tabs    = _sheet?.querySelector('.sheet-tabs');

  if (!_sheet || !_handle) return;

  _sheet.style.willChange = 'transform';
  _snapTo('peek', false);
  _attachDragEvents();
  _attachTabEvents();
  _attachKeyboardEvents();
  _subscribeStore();

  // FIX : protège le bouton signaler mobile contre l'interception du drag
  const btnMobile = document.getElementById('btn-signaler-mobile');
  if (btnMobile) {
    btnMobile.addEventListener('touchstart', (e) => {
      e.stopPropagation();
    }, { passive: true });
  }
}

// ── STORE SUBSCRIPTIONS ───────────────────────────────────

function _subscribeStore() {
  store.subscribe('buses', (buses) => {
    const line     = store.get('filteredLine');
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
    if (bus && _currentState === 'peek') _snapTo('half');
    _highlightSelectedCard(bus?.id);
  });

  store.subscribe('mobileSheetState', (state) => {
    if (state && state !== _currentState) _snapTo(state);
  });
}

// ── DRAG — TOUCH EVENTS ───────────────────────────────────

function _attachDragEvents() {
  _handle.addEventListener('touchstart', _onTouchStart, { passive: true });

  _sheet.addEventListener('touchstart', _onSheetTouchStart, { passive: true });
  _sheet.addEventListener('touchmove',  _onSheetTouchMove,  { passive: false });
  _sheet.addEventListener('touchend',   _onSheetTouchEnd,   { passive: true });

  _handle.addEventListener('click', _onHandleClick);
}

function _onHandleClick() {
  if (_currentState === 'peek')      _snapTo('half');
  else if (_currentState === 'half') _snapTo('peek');
}

function _onTouchStart(e) {
  // Si on touche un élément interactif dans le handle, ne pas démarrer le drag
  const interactive = e.target.closest('button, input, textarea, a, [role="button"]');
  if (interactive) return;
  _startDrag(e.touches[0].clientY);
}

function _onSheetTouchStart(e) {
  // FIX : utiliser closest() au lieu de tagName pour gérer les enfants (span, emoji…)
  const interactive = e.target.closest('button, input, textarea, a, [role="button"]');
  if (interactive) return;

  const chatWindow = document.getElementById('chat-window');
  if (chatWindow && chatWindow.contains(e.target)) return;

  _startDrag(e.touches[0].clientY);
}

function _startDrag(clientY) {
  _isDragging     = true;
  _startY         = clientY;
  _lastY          = clientY;
  _lastTime       = Date.now();
  _velocity       = 0;
  _startTranslate = _getCurrentTranslate();
  _sheet.style.transition = 'none';
}

function _onSheetTouchMove(e) {
  if (!_isDragging) return;

  const touch   = e.touches[0];
  const clientY = touch.clientY;
  const deltaY  = clientY - _startY;
  const now     = Date.now();

  const dt = now - _lastTime;
  if (dt > 0) _velocity = (clientY - _lastY) / dt;
  _lastY    = clientY;
  _lastTime = now;

  const scrollTop = _content?.scrollTop ?? 0;

  if (_currentState === 'full' || _currentState === 'half') {
    const isInsideContent = _content && _content.contains(e.target);
    if (isInsideContent) {
      if (deltaY < 0) { _isDragging = false; return; }
      if (deltaY > 0 && scrollTop > 0) { _isDragging = false; return; }
    }
  }

  e.preventDefault();

  const maxTranslate = _sheet.offsetHeight - PEEK_HEIGHT;
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
  const sheetH           = _sheet.offsetHeight;
  const windowH          = window.innerHeight;

  const snapPeek = sheetH - PEEK_HEIGHT;
  const snapHalf = sheetH - windowH * HALF_HEIGHT;
  const snapFull = sheetH - windowH * FULL_HEIGHT;

  let target;

  if (_velocity > VELOCITY_THRESHOLD) {
    target = _currentState === 'full' ? 'half' : 'peek';
  } else if (_velocity < -VELOCITY_THRESHOLD) {
    target = _currentState === 'peek' ? 'half'
           : _currentState === 'half' ? 'full'
           : 'full';
  } else {
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

  const sheetH = _sheet.offsetHeight;
  let translateY;

  if (state === 'peek') {
    translateY = sheetH - PEEK_HEIGHT;
  } else if (state === 'half') {
    translateY = sheetH - window.innerHeight * HALF_HEIGHT;
  } else {
    translateY = sheetH - window.innerHeight * FULL_HEIGHT;
  }

  translateY = Math.max(0, translateY);

  if (animate) {
    _sheet.style.transition = 'transform 0.3s cubic-bezier(0.34, 1.2, 0.64, 1)';
  } else {
    _sheet.style.transition = 'none';
  }

  requestAnimationFrame(() => {
    _sheet.style.transform = `translateY(${translateY}px)`;
  });

  if (state === 'peek' && _content) _content.scrollTop = 0;
  _handle.style.touchAction = 'none';
}

// ── CLAVIER VIRTUEL ───────────────────────────────────────

function _attachKeyboardEvents() {
  if (!window.visualViewport) return;

  window.visualViewport.addEventListener('resize', () => {
    const chatWin = document.getElementById('chat-window');
    if (chatWin && chatWin.classList.contains('chat-window--open')) return;

    const vvHeight = window.visualViewport.height;
    const windowH  = window.innerHeight;

    if (vvHeight < windowH * 0.85) {
      _snapTo('full');
    } else {
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
      if (_currentState === 'peek') _snapTo('half');
    });
  });
}

function _renderTab(tab) {
  const buses    = store.get('buses');
  const line     = store.get('filteredLine');
  const filtered = line ? buses.filter(b => b.ligne === line) : buses;

  if (tab === 'buses')       _renderBusList(filtered);
  else if (tab === 'leaderboard') _renderLeaderboard();
}

// ── RENDU BUS LIST ────────────────────────────────────────

function _updateSummary(count) {
  if (!_summary) return;
  _summary.textContent = count > 0
    ? `${count} bus actif${count > 1 ? 's' : ''}`
    : 'Aucun bus actif';
}

function _renderBusList(buses) {
  const activeTab = _tabs?.querySelector('.sheet-tab-btn.active')?.dataset.sheetTab;
  if (activeTab && activeTab !== 'buses') return;
  if (!_content) return;

  _content.innerHTML = '';

  if (!buses || buses.length === 0) {
    _content.innerHTML = `
      <div class="empty-state">
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
    <div class="bus-position">${bus.position}</div>
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
  _content.innerHTML = `
    <div class="empty-state">
      <div class="empty-text">Chargement du classement...</div>
    </div>`;
}

export function injectLeaderboard(users) {
  const activeTab = _tabs?.querySelector('.sheet-tab-btn.active')?.dataset.sheetTab;
  if (activeTab !== 'leaderboard' || !_content) return;

  _content.innerHTML = '';

  if (!users || users.length === 0) {
    _content.innerHTML = `
      <div class="empty-state">
        <div class="empty-text">Aucun contributeur pour l'instant.</div>
      </div>`;
    return;
  }

  users.forEach((user, i) => {
    const div = document.createElement('div');
    div.className = 'lb-item';
    const rank       = i + 1;
    const rankClass  = rank === 1 ? 'gold' : rank === 2 ? 'silver' : rank === 3 ? 'bronze' : 'other';
    const rankSymbol = rank === 1 ? '1' : rank === 2 ? '2' : rank === 3 ? '3' : String(rank);

    div.innerHTML = `
      <div class="lb-rank ${rankClass}">${rankSymbol}</div>
      <div class="lb-avatar">${user.avatar}</div>
      <div class="lb-info">
        <div class="lb-name">${user.name}</div>
        <div class="lb-zone">${user.zone}</div>
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

export function snapTo(state) { _snapTo(state); }
export function getState()    { return _currentState; }