/**
 * js/ui.js
 * Rendu DOM sidebar desktop : bus list, leaderboard, stats, tabs, filtres.
 * Dépend de : store.js, utils.js, constants.js
 * Ne touche PAS à la carte ni au chat.
 */

import * as store from './store.js';
import { getAgeClass, formatAge, getRankClass, getRankSymbol, getBadgeClass } from './utils.js';

// ── STATS BAR ─────────────────────────────────────────────

export function initStats() {
  store.subscribe('stats', (stats) => {
    _setStatAnimated('stat-bus',     stats.activeBuses);
    _setStatAnimated('stat-sig',     stats.reportsToday);
    _setStatAnimated('stat-contrib', stats.contributors);
  });
}

function _setStatAnimated(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  const prev = el.textContent;
  if (String(prev) === String(value)) return;
  el.textContent = value;
  el.classList.remove('updated');
  void el.offsetWidth;
  el.classList.add('updated');
}

// ── TIMER ─────────────────────────────────────────────────

let _timerInterval = null;

export function startTimer(seconds, onComplete) {
  if (_timerInterval) clearInterval(_timerInterval);
  let count = seconds;
  const el = document.getElementById('timer');
  if (el) el.textContent = `${count}s`;

  _timerInterval = setInterval(() => {
    count--;
    if (el) el.textContent = `${count}s`;
    if (count <= 0) {
      clearInterval(_timerInterval);
      _timerInterval = null;
      onComplete();
    }
  }, 1000);
}

// ── TABS ─────────────────────────────────────────────────

export function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      const content = document.getElementById(`tab-${tab}`);
      if (content) content.classList.add('active');
    });
  });
}

// ── FILTRES PAR LIGNE ─────────────────────────────────────

export function initFilters(onFilterChange) {
  store.subscribe('buses', (buses) => _renderFilters(buses, onFilterChange));
  store.subscribe('filteredLine', (line) => _updateFilterChips(line));
}

function _renderFilters(buses, onFilterChange) {
  const bar = document.getElementById('filter-bar');
  if (!bar) return;

  // Lignes actives extraites dynamiquement
  const activeLines = [...new Set(buses.map(b => b.ligne))].sort((a, b) =>
    isNaN(a) || isNaN(b) ? a.localeCompare(b) : Number(a) - Number(b)
  );

  bar.innerHTML = '';

  // Chip "Toutes"
  const allChip = _createChip('Toutes', null, store.get('filteredLine') === null, onFilterChange);
  bar.appendChild(allChip);

  activeLines.forEach(ligne => {
    const chip = _createChip(ligne, ligne, store.get('filteredLine') === ligne, onFilterChange);
    bar.appendChild(chip);
  });

  // Navigation clavier flèches
  _initChipsKeyboard(bar);
}

function _createChip(label, value, isActive, onClick) {
  const btn = document.createElement('button');
  btn.className = `filter-chip${isActive ? ' active' : ''}`;
  btn.textContent = label;
  btn.dataset.line = value ?? 'all';
  btn.setAttribute('role', 'tab');
  btn.setAttribute('aria-selected', String(isActive));
  btn.addEventListener('click', () => onClick(value));
  return btn;
}

function _updateFilterChips(activeLine) {
  document.querySelectorAll('.filter-chip').forEach(chip => {
    const val = chip.dataset.line === 'all' ? null : chip.dataset.line;
    const isActive = val === activeLine;
    chip.classList.toggle('active', isActive);
    chip.setAttribute('aria-selected', String(isActive));
  });
}

function _initChipsKeyboard(bar) {
  bar.setAttribute('role', 'tablist');
  bar.addEventListener('keydown', (e) => {
    const chips = [...bar.querySelectorAll('.filter-chip:not(:disabled)')];
    const idx = chips.indexOf(document.activeElement);
    if (e.key === 'ArrowRight' && idx < chips.length - 1) chips[idx + 1].focus();
    if (e.key === 'ArrowLeft'  && idx > 0)                chips[idx - 1].focus();
  });
}

// ── BUS LIST ─────────────────────────────────────────────

export function initBusList(onSelect) {
  store.subscribe('buses', (buses) => {
    const filtered = _applyLineFilter(buses, store.get('filteredLine'));
    _renderBusList(filtered, store.get('selectedBus')?.id, onSelect);
  });

  store.subscribe('filteredLine', (line) => {
    const filtered = _applyLineFilter(store.get('buses'), line);
    _renderBusList(filtered, store.get('selectedBus')?.id, onSelect);
  });

  store.subscribe('selectedBus', (bus) => {
    if (bus) selectBusCard(bus.id);
  });
}

function _applyLineFilter(buses, line) {
  return line ? buses.filter(b => b.ligne === line) : buses;
}

function _renderBusList(buses, selectedId, onSelect) {
  const container = document.getElementById('tab-buses');
  if (!container) return;
  container.innerHTML = '';

  if (!buses || buses.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-text">Aucun bus actif sur cette ligne.<br>Essayez une autre ligne.</div>
        <button class="empty-action" onclick="window._resetFilter()">Voir toutes les lignes</button>
      </div>`;
    return;
  }

  buses.forEach(bus => {
    const card = _buildBusCard(bus, selectedId === bus.id);
    card.addEventListener('click', () => onSelect(bus.id));
    container.appendChild(card);
  });
}

export function selectBusCard(busId) {
  document.querySelectorAll('.bus-card').forEach(c => c.classList.remove('selected'));
  const card = document.getElementById(`bus-card-${busId}`);
  if (card) {
    card.classList.add('selected');
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function _buildBusCard(bus, isSelected) {
  const div = document.createElement('div');
  div.className = `bus-card${isSelected ? ' selected' : ''}`;
  div.id = `bus-card-${bus.id}`;
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

  // Navigation clavier
  div.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); div.click(); }
  });

  return div;
}

// ── LEADERBOARD ───────────────────────────────────────────

export function initLeaderboard() {
  // Le leaderboard est chargé une fois via app.js
}

export function renderLeaderboard(users) {
  const container = document.getElementById('tab-leaderboard');
  if (!container) return;
  container.innerHTML = '';

  if (!users || users.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🏆</div>
        <div class="empty-text">Aucun contributeur pour l'instant.</div>
      </div>`;
    return;
  }

  users.forEach((user, i) => container.appendChild(_buildLeaderboardItem(user, i)));
}

function _buildLeaderboardItem(user, index) {
  const div = document.createElement('div');
  div.className = 'lb-item';

  const rankClass  = getRankClass(index + 1);
  const rankSymbol = getRankSymbol(index + 1);
  const badgesHtml = (user.badges || []).slice(0, 2).map((badge, j) =>
    `<span class="badge ${getBadgeClass(j)}">${badge}</span>`
  ).join('');

  div.innerHTML = `
    <div class="lb-rank ${rankClass}" aria-label="Rang ${index + 1}">${rankSymbol}</div>
    <div class="lb-avatar" aria-hidden="true">${user.avatar}</div>
    <div class="lb-info">
      <div class="lb-name">${user.name}</div>
      <div class="lb-zone">📍 ${user.zone}</div>
      <div class="badge-row">${badgesHtml}</div>
    </div>
    <div class="lb-score" aria-label="${user.count} signalements">
      <div class="lb-count">${user.count}</div>
      <div class="lb-unit">signalements</div>
    </div>
  `;

  return div;
}
