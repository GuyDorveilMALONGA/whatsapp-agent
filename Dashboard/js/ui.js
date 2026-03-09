/**
 * js/ui.js
 * Rendu DOM — sidebar buses, leaderboard, stats, tabs.
 * Dépend de : utils.js
 * Ne touche pas à la carte (map.js) ni aux données (api.js).
 */

const UI = (() => {

  // ── STATS ────────────────────────────────────────────────

  /**
   * Met à jour les 3 compteurs du stats bar.
   * @param {number} busCount
   * @param {object} stats - {signalements_today, contributors}
   */
  function updateStats(busCount, stats) {
    _setText('stat-bus',     busCount);
    _setText('stat-sig',     stats.signalements_today || '—');
    _setText('stat-contrib', stats.contributors || '—');
  }

  // ── TIMER ────────────────────────────────────────────────

  let _timerInterval = null;

  /**
   * Démarre le countdown visible dans le header.
   * Appelle onComplete quand il atteint 0.
   * @param {number} seconds
   * @param {Function} onComplete
   */
  function startTimer(seconds, onComplete) {
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

  // ── TABS ────────────────────────────────────────────────

  /**
   * Initialise les onglets sidebar.
   */
  function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        const content = document.getElementById(`tab-${tab}`);
        if (content) content.classList.add('active');
      });
    });
  }

  // ── BUS LIST ─────────────────────────────────────────────

  /**
   * Rendu de la liste des bus dans la sidebar.
   * @param {Array} buses
   * @param {number|null} selectedId
   * @param {Function} onSelect - callback(busId)
   */
  function renderBusList(buses, selectedId, onSelect) {
    const container = document.getElementById('tab-buses');
    if (!container) return;
    container.innerHTML = '';

    if (!buses || buses.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔍</div>
          <div class="empty-text">Aucun bus signalé pour l'instant.<br>Sois le premier !</div>
        </div>`;
      return;
    }

    buses.forEach(bus => {
      const card = _buildBusCard(bus, selectedId === bus.id);
      card.addEventListener('click', () => onSelect(bus.id));
      container.appendChild(card);
    });
  }

  /**
   * Met en surbrillance une carte bus et scroll dessus.
   * @param {number} busId
   */
  function selectBusCard(busId) {
    document.querySelectorAll('.bus-card').forEach(c => c.classList.remove('selected'));
    const card = document.getElementById(`bus-card-${busId}`);
    if (card) {
      card.classList.add('selected');
      card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  /**
   * Construit l'élément DOM d'une carte bus.
   * @param {object} bus
   * @param {boolean} isSelected
   * @returns {HTMLElement}
   */
  function _buildBusCard(bus, isSelected) {
    const div = document.createElement('div');
    div.className = `bus-card${isSelected ? ' selected' : ''}`;
    div.id = `bus-card-${bus.id}`;

    const ageClass = Utils.getAgeClass(bus.minutes_ago);
    const ageLabel = Utils.formatAge(bus.minutes_ago);

    div.innerHTML = `
      <div class="bus-card-header">
        <div class="bus-badge">${bus.ligne}</div>
        <div class="bus-name">${bus.name}</div>
        <div class="bus-age ${ageClass}">${ageLabel}</div>
      </div>
      <div class="bus-position">📍 ${bus.position}</div>
      <div class="bus-reporter">Signalé par ${bus.reporter}</div>
    `;

    return div;
  }

  // ── LEADERBOARD ──────────────────────────────────────────

  /**
   * Rendu du leaderboard dans la sidebar.
   * @param {Array} users
   */
  function renderLeaderboard(users) {
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

    users.forEach((user, i) => {
      container.appendChild(_buildLeaderboardItem(user, i));
    });
  }

  /**
   * Construit un élément leaderboard.
   * @param {object} user
   * @param {number} index - 0-based
   * @returns {HTMLElement}
   */
  function _buildLeaderboardItem(user, index) {
    const div = document.createElement('div');
    div.className = 'lb-item';

    const rankClass  = Utils.getRankClass(index + 1);
    const rankSymbol = Utils.getRankSymbol(index + 1);

    const badgesHtml = (user.badges || []).slice(0, 2).map((badge, j) =>
      `<span class="badge ${Utils.getBadgeClass(j)}">${badge}</span>`
    ).join('');

    div.innerHTML = `
      <div class="lb-rank ${rankClass}">${rankSymbol}</div>
      <div class="lb-avatar">${user.avatar}</div>
      <div class="lb-info">
        <div class="lb-name">${user.name}</div>
        <div class="lb-zone">📍 ${user.zone}</div>
        <div class="badge-row">${badgesHtml}</div>
      </div>
      <div class="lb-score">
        <div class="lb-count">${user.count}</div>
        <div class="lb-unit">signalements</div>
      </div>
    `;

    return div;
  }

  // ── HELPERS ──────────────────────────────────────────────

  function _setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  // ── PUBLIC API ───────────────────────────────────────────

  return {
    updateStats,
    startTimer,
    initTabs,
    renderBusList,
    renderLeaderboard,
    selectBusCard,
  };

})();
