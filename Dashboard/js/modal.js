/**
 * js/modal.js
 * Modal de signalement — deux modes : confirmation rapide + signalement complet.
 *
 * MODE CONFIRMATION (depuis popup "Confirmer") :
 *   → POST direct, pas de modal, toast + pulseMarker
 *
 * MODE SIGNALEMENT (depuis sidebar "Signaler") :
 *   → Modal complet : ligne (dropdown) + arrêt (autocomplete) + observation
 *
 * FIX : closeModal() reset le formulaire + réactive le bouton submit
 *
 * Dépend de : store.js, constants.js, utils.js, toast.js
 * RÈGLE : ne touche jamais map.js ou ui.js directement — passe par store ou callbacks.
 */

import * as store from './store.js';
import { ARRETS_CONNUS, LIGNES_CONNUES, LIGNE_NAMES, API_BASE } from './constants.js';
import { normalizeText, safeFetch, generateUUID } from './utils.js';
import * as Toast from './toast.js';

// ── Callbacks injectés depuis app.js ──────────────────────
let _onConfirmSuccess = null;
let _onReportSuccess  = null;

// ── Session ID (mémoire uniquement, jamais localStorage) ──
const SESSION_ID = `web_${generateUUID()}`;

// ── État interne du modal ─────────────────────────────────
let _isSubmitting = false;
let _focusTrigger = null;
let _autocompleteTimeout = null;

// ── Éléments DOM ─────────────────────────────────────────
let _elModal, _elOverlay, _elForm;
let _elLigne, _elArret, _elObservation;
let _elSuggestions, _elSubmitBtn, _elSubmitLabel;
let _elWaLink, _elTgLink;

// ═══════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════

export function init(callbacks = {}) {
  _onConfirmSuccess = callbacks.onConfirmSuccess || null;
  _onReportSuccess  = callbacks.onReportSuccess  || null;
  _buildDOM();
  _attachEvents();
}

// ═══════════════════════════════════════════════════════════
// API PUBLIQUE
// ═══════════════════════════════════════════════════════════

export async function confirmBus(busId, triggerEl = null) {
  const bus = store.get('buses').find(b => String(b.id) === String(busId));
  if (!bus) {
    Toast.error('Bus introuvable. Actualise la carte.');
    return;
  }

  if (triggerEl) {
    triggerEl.disabled    = true;
    triggerEl.textContent = '⏳';
  }

  try {
    await _postReport({
      ligne:       bus.ligne,
      arret:       bus.position,
      observation: 'confirmation',
      source:      'web_popup_confirm',
    });

    Toast.success(`✅ Bus ${bus.ligne} confirmé à ${bus.position} !`);
    if (_onConfirmSuccess) _onConfirmSuccess(busId);
    _bumpReportsCount();

  } catch (err) {
    _handlePostError(err, null, bus.ligne, bus.position);
  } finally {
    if (triggerEl) {
      triggerEl.disabled    = false;
      triggerEl.textContent = '✅ Confirmer';
    }
  }
}

export function openModal(prefill = {}, triggerEl = null) {
  _focusTrigger = triggerEl;
  _resetForm();

  if (prefill.ligne && LIGNES_CONNUES.has(prefill.ligne)) {
    _elLigne.value = prefill.ligne;
    _updateWaLink(prefill.ligne, prefill.arret || '');
  }
  if (prefill.arret) {
    _elArret.value = prefill.arret;
  }

  _elModal.hidden   = false;
  _elOverlay.hidden = false;
  _elModal.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';

  requestAnimationFrame(() => {
    if (!_elLigne.value)       _elLigne.focus();
    else if (!_elArret.value)  _elArret.focus();
    else                       _elSubmitBtn.focus();
  });
}

export function closeModal() {
  // FIX : reset immédiat à la fermeture — formulaire propre pour la prochaine ouverture
  // et bouton "Envoyer" réactivé si on ferme pendant un envoi
  _resetForm();

  _elModal.hidden   = true;
  _elOverlay.hidden = true;
  _elModal.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
  _hideSuggestions();

  if (_focusTrigger) {
    _focusTrigger.focus();
    _focusTrigger = null;
  }
}

// ═══════════════════════════════════════════════════════════
// CONSTRUCTION DU DOM
// ═══════════════════════════════════════════════════════════

function _buildDOM() {
  _elOverlay = document.createElement('div');
  _elOverlay.className = 'modal-overlay';
  _elOverlay.setAttribute('aria-hidden', 'true');
  _elOverlay.hidden = true;

  _elModal = document.createElement('div');
  _elModal.id        = 'report-modal';
  _elModal.className = 'modal';
  _elModal.setAttribute('role', 'dialog');
  _elModal.setAttribute('aria-modal', 'true');
  _elModal.setAttribute('aria-labelledby', 'modal-title');
  _elModal.hidden = true;

  _elModal.innerHTML = `
    <div class="modal-header">
      <h2 id="modal-title" class="modal-title">🚌 Signaler un bus</h2>
      <button class="modal-close" aria-label="Fermer le modal" id="modal-close-btn">✕</button>
    </div>

    <form class="modal-form" id="report-form" novalidate>

      <div class="form-group">
        <label for="modal-ligne" class="form-label">
          Ligne <span class="required" aria-hidden="true">*</span>
        </label>
        <select id="modal-ligne" class="form-select" required aria-required="true"
                aria-describedby="ligne-error">
          <option value="">— Choisir une ligne —</option>
          ${_buildLigneOptions()}
        </select>
        <span id="ligne-error" class="form-error" role="alert" aria-live="polite"></span>
      </div>

      <div class="form-group">
        <label for="modal-arret" class="form-label">
          Arrêt <span class="required" aria-hidden="true">*</span>
        </label>
        <div class="autocomplete-wrapper">
          <input
            id="modal-arret"
            type="text"
            class="form-input"
            placeholder="Ex : Liberté 5, Sandaga, Pikine…"
            autocomplete="off"
            required
            aria-required="true"
            aria-autocomplete="list"
            aria-controls="arret-suggestions"
            aria-describedby="arret-error"
            maxlength="80"
          />
          <ul id="arret-suggestions" class="autocomplete-list" role="listbox"
              aria-label="Suggestions d'arrêts" hidden></ul>
        </div>
        <span id="arret-error" class="form-error" role="alert" aria-live="polite"></span>
      </div>

      <div class="form-group">
        <label for="modal-observation" class="form-label">
          Observation <span class="form-optional">(optionnel)</span>
        </label>
        <select id="modal-observation" class="form-select">
          <option value="">— Aucune —</option>
          <option value="bondé">🔴 Bondé</option>
          <option value="vide">🟢 Vide / peu de monde</option>
          <option value="en retard">⏱️ En retard</option>
          <option value="en panne">🔧 En panne</option>
          <option value="déjà parti">💨 Déjà parti</option>
        </select>
      </div>

      <!-- Honeypot anti-bot -->
      <input type="text" name="website" tabindex="-1"
             aria-hidden="true" style="display:none" autocomplete="off" />

      <button type="submit" id="modal-submit" class="modal-submit-btn" aria-live="polite">
        <span id="modal-submit-label">📡 Envoyer le signalement</span>
      </button>

    </form>

    <div class="modal-footer-links">
      <span class="modal-footer-text">Préférez WhatsApp ou Telegram ?</span>
      <a id="modal-wa-link" href="#" target="_blank" rel="noopener" class="modal-channel-link">
        WhatsApp
      </a>
      <span class="modal-footer-sep">·</span>
      <a id="modal-tg-link" href="https://t.me/XetuBot" target="_blank"
         rel="noopener" class="modal-channel-link">
        Telegram
      </a>
    </div>
  `;

  document.body.appendChild(_elOverlay);
  document.body.appendChild(_elModal);

  _elForm        = _elModal.querySelector('#report-form');
  _elLigne       = _elModal.querySelector('#modal-ligne');
  _elArret       = _elModal.querySelector('#modal-arret');
  _elObservation = _elModal.querySelector('#modal-observation');
  _elSuggestions = _elModal.querySelector('#arret-suggestions');
  _elSubmitBtn   = _elModal.querySelector('#modal-submit');
  _elSubmitLabel = _elModal.querySelector('#modal-submit-label');
  _elWaLink      = _elModal.querySelector('#modal-wa-link');
  _elTgLink      = _elModal.querySelector('#modal-tg-link');
}

function _buildLigneOptions() {
  return [...LIGNES_CONNUES]
    .sort((a, b) => {
      const na = parseFloat(a), nb = parseFloat(b);
      if (!isNaN(na) && !isNaN(nb)) return na - nb;
      return a.localeCompare(b);
    })
    .map(code => {
      const name = LIGNE_NAMES[code] || '';
      return `<option value="${code}">Bus ${code}${name ? ' — ' + name : ''}</option>`;
    })
    .join('');
}

// ═══════════════════════════════════════════════════════════
// EVENTS
// ═══════════════════════════════════════════════════════════

function _attachEvents() {
  _elModal.querySelector('#modal-close-btn').addEventListener('click', closeModal);
  _elOverlay.addEventListener('click', closeModal);
  _elModal.addEventListener('keydown', _handleKeydown);
  _elForm.addEventListener('submit', _handleSubmit);

  _elArret.addEventListener('input',   _handleArretInput);
  _elArret.addEventListener('keydown', _handleArretKeydown);
  _elArret.addEventListener('blur', () => setTimeout(_hideSuggestions, 150));

  _elLigne.addEventListener('change', () => _updateWaLink(_elLigne.value, _elArret.value));
  _elArret.addEventListener('input',  () => _updateWaLink(_elLigne.value, _elArret.value));

  _elLigne.addEventListener('change', () => _clearError('ligne-error'));
  _elArret.addEventListener('input',  () => _clearError('arret-error'));
}

function _handleKeydown(e) {
  if (e.key === 'Escape') { closeModal(); return; }
  if (e.key !== 'Tab') return;

  const focusables = Array.from(
    _elModal.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), [tabindex="0"]'
    )
  ).filter(el => !el.closest('[aria-hidden="true"]'));

  if (!focusables.length) return;
  const first = focusables[0];
  const last  = focusables[focusables.length - 1];

  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault(); last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault(); first.focus();
  }
}

// ═══════════════════════════════════════════════════════════
// AUTOCOMPLETE ARRÊTS
// ═══════════════════════════════════════════════════════════

let _activeSuggestionIndex = -1;

function _handleArretInput() {
  clearTimeout(_autocompleteTimeout);
  const query = _elArret.value;
  if (query.length < 2) { _hideSuggestions(); return; }
  _autocompleteTimeout = setTimeout(() => {
    const results = _searchArrets(query, _elLigne.value);
    _renderSuggestions(results);
  }, 120);
}

function _handleArretKeydown(e) {
  if (_elSuggestions.hidden) return;
  const items = _elSuggestions.querySelectorAll('[role="option"]');
  if (!items.length) return;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _activeSuggestionIndex = Math.min(_activeSuggestionIndex + 1, items.length - 1);
    _highlightSuggestion(items);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    _activeSuggestionIndex = Math.max(_activeSuggestionIndex - 1, 0);
    _highlightSuggestion(items);
  } else if (e.key === 'Enter' && _activeSuggestionIndex >= 0) {
    e.preventDefault();
    items[_activeSuggestionIndex].click();
  } else if (e.key === 'Escape') {
    _hideSuggestions();
  }
}

function _highlightSuggestion(items) {
  items.forEach((item, i) => {
    item.setAttribute('aria-selected', i === _activeSuggestionIndex ? 'true' : 'false');
    item.classList.toggle('is-highlighted', i === _activeSuggestionIndex);
  });
  if (_activeSuggestionIndex >= 0) {
    _elArret.setAttribute('aria-activedescendant', items[_activeSuggestionIndex].id);
  }
}

function _searchArrets(query, selectedLigne) {
  const q = normalizeText(query);

  const score = (arret) => {
    const normalName     = normalizeText(arret.name);
    const allTexts       = [normalName, ...arret.aliases.map(normalizeText)];
    const onSelectedLine = selectedLigne && arret.lines.includes(selectedLigne);

    let s = 0;
    if (normalName.startsWith(q))               s += 30;
    else if (normalName.includes(q))            s += 20;
    else if (allTexts.some(t => t.includes(q))) s += 10;
    else return -1;

    if (onSelectedLine) s += 5;
    return s;
  };

  return ARRETS_CONNUS
    .map(arret => ({ arret, score: score(arret) }))
    .filter(({ score }) => score >= 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5)
    .map(({ arret }) => arret);
}

function _renderSuggestions(results) {
  _activeSuggestionIndex = -1;
  _elArret.removeAttribute('aria-activedescendant');

  if (!results.length) { _hideSuggestions(); return; }

  const query = normalizeText(_elArret.value);

  _elSuggestions.innerHTML = results.map((arret, i) => {
    const highlighted = _highlightMatch(arret.name, query);
    const linesBadges = arret.lines.slice(0, 3)
      .map(l => `<span class="suggestion-line-badge">${l}</span>`)
      .join('');
    return `
      <li id="suggestion-${i}"
          role="option"
          aria-selected="false"
          class="autocomplete-item"
          data-name="${arret.name}">
        <span class="suggestion-name">${highlighted}</span>
        <span class="suggestion-lines">${linesBadges}</span>
      </li>
    `;
  }).join('');

  _elSuggestions.querySelectorAll('[role="option"]').forEach(item => {
    item.addEventListener('mousedown', (e) => {
      e.preventDefault();
      _elArret.value = item.dataset.name;
      _hideSuggestions();
      _updateWaLink(_elLigne.value, _elArret.value);
      _clearError('arret-error');
    });
  });

  _elSuggestions.hidden = false;
}

function _highlightMatch(name, query) {
  const normalName = normalizeText(name);
  const idx = normalName.indexOf(query);
  if (idx === -1) return _escapeHtml(name);
  return (
    _escapeHtml(name.slice(0, idx)) +
    `<mark>${_escapeHtml(name.slice(idx, idx + query.length))}</mark>` +
    _escapeHtml(name.slice(idx + query.length))
  );
}

function _hideSuggestions() {
  _elSuggestions.hidden = true;
  _elSuggestions.innerHTML = '';
  _activeSuggestionIndex = -1;
}

// ═══════════════════════════════════════════════════════════
// SOUMISSION
// ═══════════════════════════════════════════════════════════

async function _handleSubmit(e) {
  e.preventDefault();

  const honeypot = _elForm.querySelector('input[name="website"]');
  if (honeypot && honeypot.value) return;
  if (_isSubmitting) return;

  const ligne       = _elLigne.value.trim();
  const arret       = _elArret.value.trim();
  const observation = _elObservation.value;

  let valid = true;
  if (!ligne || !LIGNES_CONNUES.has(ligne)) {
    _showError('ligne-error', 'Veuillez choisir une ligne valide.');
    _elLigne.focus();
    valid = false;
  }
  if (!arret || arret.length < 2) {
    _showError('arret-error', 'Veuillez indiquer un arrêt (2 caractères minimum).');
    if (valid) _elArret.focus();
    valid = false;
  }
  if (!valid) return;

  _setSubmitting(true);

  try {
    await _postReport({
      ligne,
      arret,
      observation: observation || undefined,
      source: 'web_dashboard',
    });

    Toast.success(`✅ Signalement enregistré — Bus ${ligne} à ${arret} !`);
    _bumpReportsCount();

    // FIX : callback vers app.js pour recharger stats + carte
    if (_onReportSuccess) _onReportSuccess();

    // Ferme après 1.2s — closeModal() reset le formulaire
    setTimeout(closeModal, 1200);

  } catch (err) {
    _handlePostError(err, _elSubmitBtn, ligne, arret);
    // FIX : réactiver le bouton en cas d'erreur (setSubmitting(false) dans finally)
  } finally {
    _setSubmitting(false);
  }
}

// ═══════════════════════════════════════════════════════════
// POST /api/report
// ═══════════════════════════════════════════════════════════

async function _postReport({ ligne, arret, observation, source }) {
  const payload = {
    ligne,
    arret,
    source:     source || 'web_dashboard',
    client_ts:  new Date().toISOString(),
    session_id: SESSION_ID,
  };
  if (observation) payload.observation = observation;

  return safeFetch(`${API_BASE}/api/report`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(payload),
  });
}

// ═══════════════════════════════════════════════════════════
// GESTION ERREURS
// ═══════════════════════════════════════════════════════════

function _handlePostError(err, retryBtn, ligne, arret) {
  if (err.code === 'rate_limited') {
    const mins = Math.ceil((err.retryAfter || 120) / 60);
    Toast.error(`⏱️ Trop de signalements. Réessaie dans ${mins} min.`);
    return;
  }
  if (err.code === 'timeout') {
    Toast.error('⚡ Connexion lente. Réessaie dans un instant.', {
      retry: retryBtn ? () => retryBtn.click() : null,
    });
    return;
  }
  const waUrl = `https://wa.me/${_getWaNumber()}?text=${encodeURIComponent(`Bus ${ligne} à ${arret}`)}`;
  Toast.error('❌ Envoi échoué.', {
    retry:         retryBtn ? () => retryBtn.click() : null,
    fallbackUrl:   waUrl,
    fallbackLabel: 'Signaler par WhatsApp',
  });
}

// ═══════════════════════════════════════════════════════════
// HELPERS UI
// ═══════════════════════════════════════════════════════════

function _setSubmitting(state) {
  _isSubmitting         = state;
  _elSubmitBtn.disabled = state;
  _elSubmitLabel.textContent = state
    ? '⏳ Envoi en cours…'
    : '📡 Envoyer le signalement';
}

function _showError(id, msg) {
  const el = document.getElementById(id);
  if (el) { el.textContent = msg; el.hidden = false; }
}

function _clearError(id) {
  const el = document.getElementById(id);
  if (el) { el.textContent = ''; el.hidden = true; }
}

function _resetForm() {
  if (_elForm) _elForm.reset();
  _hideSuggestions();
  _isSubmitting         = false;
  _elSubmitBtn.disabled = false;
  _elSubmitLabel.textContent = '📡 Envoyer le signalement';
  document.querySelectorAll('.form-error').forEach(el => {
    el.textContent = '';
    el.hidden = true;
  });
  _updateWaLink('', '');
}

function _updateWaLink(ligne, arret) {
  const msg = ligne && arret ? `Bus ${ligne} à ${arret}`
            : ligne          ? `Bus ${ligne}`
            :                  'Signalement bus';
  _elWaLink.href = `https://wa.me/${_getWaNumber()}?text=${encodeURIComponent(msg)}`;
}

function _getWaNumber() {
  try { return window.__XETU_WA_NUMBER__ || '221XXXXXXXXX'; }
  catch { return '221XXXXXXXXX'; }
}

function _bumpReportsCount() {
  const stats   = store.get('stats');
  const current = parseInt(stats?.reportsToday, 10) || 0;
  store.set('stats', { ...stats, reportsToday: current + 1 });
}

function _escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}