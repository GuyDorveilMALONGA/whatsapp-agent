/**
 * XËTU — js/ui.js
 * Seul fichier autorisé à toucher le DOM.
 * Ne fait aucun appel réseau.
 * Cache DOM initialisé dans init() — jamais au chargement du fichier.
 */
const UI = (() => {

  // Cache DOM — initialisé dans init() après DOMContentLoaded
  // Si initialisé au niveau module, getElementById retourne null (DOM pas prêt)
  let DOM = {};

  const init = () => {
    DOM = {
      statBuses:        document.getElementById('stat-buses'),
      statToday:        document.getElementById('stat-today'),
      statContributors: document.getElementById('stat-contributors'),
      busCount:         document.getElementById('bus-count'),
      busList:          document.getElementById('bus-list'),
      lineFilters:      document.getElementById('line-filters'),
      leaderboardCount: document.getElementById('leaderboard-count'),
      leaderboardList:  document.getElementById('leaderboard-list'),
      mapLoader:        document.getElementById('map-loader'),
      timer:            document.getElementById('timer'),
      toastContainer:   document.getElementById('toast-container'),
    };
  };

  /**
   * Animation fluide des compteurs (stats bar).
   */
  const animateValue = (element, newValue) => {
    if (!element || element.textContent === String(newValue)) return;
    element.style.opacity = '0';
    element.style.transform = 'translateY(-3px)';
    setTimeout(() => {
      element.textContent = newValue;
      element.style.transition = 'all .25s';
      element.style.opacity = '1';
      element.style.transform = 'translateY(0)';
    }, 150);
  };

  /**
   * Toast avec type : 'info' | 'success' | 'error'
   * textContent = zéro XSS possible
   */
  const showToast = (message, type = 'info') => {
    if (!DOM.toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast${type !== 'info' ? ` toast--${type}` : ''}`;
    toast.textContent = message;

    DOM.toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 3200);
  };

  const hideLoader = () => {
    DOM.mapLoader?.classList.add('map-loader--hidden');
  };

  const updateTimer = (secondsRemaining) => {
    if (!DOM.timer) return;
    DOM.timer.textContent = `${secondsRemaining}s`;
    DOM.timer.classList.toggle('badge-timer--urgent', secondsRemaining <= 5);
  };

  /**
   * Filtres lignes — DocumentFragment + textContent sur les labels
   */
  const renderFilters = (buses, currentFilter, onFilterChange) => {
    if (!DOM.lineFilters) return;

    const lignes = [...new Set(buses.map(b => b.ligne))].sort();
    const fragment = document.createDocumentFragment();

    const makeButton = (label, filterValue) => {
      const btn = document.createElement('button');
      btn.className = `filter-btn${currentFilter === filterValue ? ' filter-btn--active' : ''}`;
      btn.textContent = label; // textContent
      btn.addEventListener('click', () => onFilterChange(filterValue));
      return btn;
    };

    fragment.appendChild(makeButton('Tous', 'all'));
    lignes.forEach(ligne => fragment.appendChild(makeButton(ligne, ligne)));

    DOM.lineFilters.innerHTML = '';
    DOM.lineFilters.appendChild(fragment);
  };

  /**
   * Liste des bus — DocumentFragment, textContent partout sauf stripe/status
   * qui sont des classes CSS internes sans données API.
   */
  const renderBusList = (buses, currentFilter, onBusClick) => {
    if (!DOM.busList) return;

    const filtered = currentFilter === 'all'
      ? buses
      : buses.filter(b => b.ligne === currentFilter);

    if (DOM.busCount) DOM.busCount.textContent = filtered.length;

    if (filtered.length === 0) {
      DOM.busList.innerHTML = '';
      const empty = _buildEmptyState(
        '🚌',
        'Aucun bus actif',
        'Sois le premier à signaler !\nEnvoie Bus 15 à Liberté 5 sur WhatsApp'
      );
      DOM.busList.appendChild(empty);
      return;
    }

    const fragment = document.createDocumentFragment();

    filtered.forEach((bus, index) => {
      const card = _buildBusCard(bus, index, onBusClick);
      fragment.appendChild(card);
    });

    DOM.busList.innerHTML = '';
    DOM.busList.appendChild(fragment);
  };

  /**
   * Construction d'une carte bus — 100% createElement + textContent
   */
  const _buildBusCard = (bus, index, onBusClick) => {
    const cls   = Utils.getConfidenceClass(bus.confiance, bus.minutes_depuis_signalement);
    const label = Utils.CONFIDENCE_LABELS[cls];

    const card = document.createElement('div');
    card.className = 'bus-card';
    card.style.animationDelay = `${index * 0.05}s`;

    // Barre colorée latérale
    const stripe = document.createElement('div');
    stripe.className = `bus-card__stripe bus-card__stripe--${cls}`;
    card.appendChild(stripe);

    // Ligne du haut : numéro + statut
    const top = document.createElement('div');
    top.className = 'bus-card__top';

    const numEl = document.createElement('div');
    numEl.className = 'bus-card__number';
    numEl.textContent = bus.ligne;

    const statusEl = document.createElement('div');
    statusEl.className = `bus-card__status bus-card__status--${cls}`;
    const dot = document.createElement('div');
    dot.className = 'bus-card__status-dot';
    statusEl.appendChild(dot);
    statusEl.appendChild(document.createTextNode(label));

    top.appendChild(numEl);
    top.appendChild(statusEl);
    card.appendChild(top);

    // Position
    const posEl = document.createElement('div');
    posEl.className = 'bus-card__position';
    posEl.textContent = bus.position_actuelle || 'Position inconnue';
    card.appendChild(posEl);

    // Métadonnées
    const metaEl = document.createElement('div');
    metaEl.className = 'bus-card__meta';

    const timeEl = document.createElement('div');
    timeEl.className = 'bus-card__time';
    timeEl.textContent = Utils.timeAgo(bus.minutes_depuis_signalement);
    metaEl.appendChild(timeEl);

    if (bus.au_terminus) {
      const termEl = document.createElement('div');
      termEl.className = 'bus-card__terminus';
      termEl.textContent = '⚑ Terminus';
      metaEl.appendChild(termEl);
    }

    card.appendChild(metaEl);
    card.addEventListener('click', () => onBusClick(bus));

    return card;
  };

  /**
   * Leaderboard — DocumentFragment + textContent
   */
  const renderLeaderboard = (leaderboardData) => {
    if (!DOM.leaderboardList) return;

    const leaders = leaderboardData?.leaderboard || [];
    const stats   = leaderboardData?.stats || {};

    if (DOM.leaderboardCount) DOM.leaderboardCount.textContent = leaders.length;

    animateValue(DOM.statToday,        stats.total_signalements_aujourd_hui ?? 0);
    animateValue(DOM.statContributors, stats.nb_contributeurs ?? 0);

    if (leaders.length === 0) {
      DOM.leaderboardList.innerHTML = '';
      const empty = _buildEmptyState(null, null, 'Aucun contributeur encore.\nSois le premier !');
      empty.style.padding = '16px';
      DOM.leaderboardList.appendChild(empty);
      return;
    }

    const RANK_SYMBOLS = ['🥇', '🥈', '🥉'];
    const RANK_CLASSES = [
      'leader-row__rank--1',
      'leader-row__rank--2',
      'leader-row__rank--3',
    ];

    const fragment = document.createDocumentFragment();

    leaders.forEach((leader, index) => {
      const row = document.createElement('div');
      row.className = 'leader-row';
      row.style.animationDelay = `${index * 0.05}s`;

      const rankEl = document.createElement('div');
      rankEl.className = `leader-row__rank ${RANK_CLASSES[index] || 'leader-row__rank--n'}`;
      rankEl.textContent = index < 3 ? RANK_SYMBOLS[index] : String(index + 1);

      const emojiEl = document.createElement('div');
      emojiEl.className = 'leader-row__emoji';
      emojiEl.textContent = leader.badge?.emoji || '🏅';

      const infoEl = document.createElement('div');
      infoEl.className = 'leader-row__info';
      const nameEl = document.createElement('div');
      nameEl.className = 'leader-row__name';
      nameEl.textContent = leader.pseudo || '—';
      const badgeEl = document.createElement('div');
      badgeEl.className = 'leader-row__badge';
      badgeEl.textContent = leader.badge?.label || 'Contributeur';
      infoEl.appendChild(nameEl);
      infoEl.appendChild(badgeEl);

      const scoreEl = document.createElement('div');
      scoreEl.className = 'leader-row__score';
      const countEl = document.createElement('div');
      countEl.className = 'leader-row__count';
      countEl.textContent = leader.nb_signalements;
      const unitEl = document.createElement('div');
      unitEl.className = 'leader-row__unit';
      unitEl.textContent = 'signalements';
      scoreEl.appendChild(countEl);
      scoreEl.appendChild(unitEl);

      row.appendChild(rankEl);
      row.appendChild(emojiEl);
      row.appendChild(infoEl);
      row.appendChild(scoreEl);

      fragment.appendChild(row);
    });

    DOM.leaderboardList.innerHTML = '';
    DOM.leaderboardList.appendChild(fragment);
  };

  /**
   * État vide réutilisable
   */
  const _buildEmptyState = (icon, title, text) => {
    const empty = document.createElement('div');
    empty.className = 'empty-state';

    if (icon) {
      const iconEl = document.createElement('div');
      iconEl.className = 'empty-state__icon';
      iconEl.textContent = icon;
      empty.appendChild(iconEl);
    }

    if (title) {
      const titleEl = document.createElement('div');
      titleEl.className = 'empty-state__title';
      titleEl.textContent = title;
      empty.appendChild(titleEl);
    }

    if (text) {
      const textEl = document.createElement('div');
      textEl.className = 'empty-state__text';
      textEl.textContent = text;
      empty.appendChild(textEl);
    }

    return empty;
  };

  return {
    init,
    animateValue,
    showToast,
    hideLoader,
    updateTimer,
    renderFilters,
    renderBusList,
    renderLeaderboard,
    get DOM() { return DOM; },
  };

})();
