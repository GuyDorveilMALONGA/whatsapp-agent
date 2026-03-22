/**
 * js/reader.js — Xëtu V2.0
 *
 * CORRECTIONS V2.0 (BUG-1) :
 *   - La mesure offsetWidth/scrollWidth se faisait AVANT que le DOM soit peint
 *     → containerW = 0 → scroll instantané (vitesse folle).
 *   - Fix : _startScroll() attend 2 frames RAF avant de mesurer, puis re-mesure
 *     à chaque tick (le contenu peut changer dynamiquement).
 *   - Fix CSS : le style est injecté avec `display:flex` et `width:100%` explicites,
 *     plus de dépendance à un fichier CSS externe qui peut arriver après le JS.
 *   - Vitesse : 28 px/seconde — lisible sur mobile 4 pouces.
 *   - Pause de 3s en fin de défilement avant reset.
 *   - hide() annule le RAF proprement pour éviter les fuites mémoire.
 */

let _el        = null;
let _scrollEl  = null;
let _rafId     = null;
let _scrollX   = 0;
let _paused    = false;
let _lastTs    = null;
let _pauseTimer = null;

const SCROLL_PX_PER_SEC = 28;
const PAUSE_MS          = 3000;

// ── Init ──────────────────────────────────────────────────

export function initReader() {
  _injectCSS();
  _el       = document.getElementById('bus-reader');
  _scrollEl = _el?.querySelector('.reader-scroll');
  if (!_el) { console.warn('[Reader] #bus-reader introuvable'); return; }
  _el.hidden = true;
}

// ── CSS injecté en JS — priorité maximale ─────────────────
// On utilise !important sur les propriétés critiques pour mesure.

function _injectCSS() {
  if (document.getElementById('reader-style')) return;
  const style = document.createElement('style');
  style.id = 'reader-style';
  style.textContent = `
    #bus-reader {
      position: relative !important;
      display: flex !important;
      align-items: center !important;
      width: 100% !important;
      height: 36px !important;
      overflow: hidden !important;
      flex-shrink: 0 !important;
      background: var(--surface2, #1a2235);
      border-bottom: 1px solid var(--border, rgba(255,255,255,0.07));
      padding: 0 14px;
      box-sizing: border-box;
    }
    #bus-reader[hidden] { display: none !important; }

    .reader-scroll {
      display: inline-flex !important;
      align-items: center;
      gap: 0;
      white-space: nowrap !important;
      will-change: transform;
      font-size: 12px;
      color: var(--text-dim, #c4cde0);
      /* NE PAS mettre width:100% ici — on veut scrollWidth > containerW */
    }

    .reader-badge {
      display: inline-flex;
      align-items: center;
      border-radius: 4px;
      padding: 2px 8px;
      font-weight: 700;
      font-size: 11px;
      color: #fff;
      margin-right: 10px;
      flex-shrink: 0;
    }
    .reader-sep     { margin: 0 5px; opacity: 0.3; font-size: 11px; flex-shrink: 0; }
    .reader-past    { opacity: 0.35; font-size: 12px; flex-shrink: 0; }
    .reader-current { font-weight: 700; text-decoration: underline; font-size: 12px; flex-shrink: 0; }
    .reader-future  { opacity: 0.75; font-size: 12px; flex-shrink: 0; }
  `;
  document.head.appendChild(style);
}

// ── API publique ──────────────────────────────────────────

export function updateReader(ligne, arrets, idx) {
  if (!_el || !_scrollEl || !arrets?.length) return;

  const color = _lineColor(ligne);

  const parts = arrets.map((a, i) => {
    const nom = a.nom || a.name || `Arrêt ${i + 1}`;
    const safe = _esc(nom);
    if (i === idx)  return `<span class="reader-current" style="color:${color}">${safe}</span>`;
    if (i < idx)    return `<span class="reader-past">${safe}</span>`;
    return              `<span class="reader-future">${safe}</span>`;
  });

  _scrollEl.innerHTML =
    `<span class="reader-badge" style="background:${color}">Bus ${_esc(String(ligne))}</span>` +
    parts.join('<span class="reader-sep">›</span>');

  show();
  _startScroll();
}

export function show() {
  if (_el) _el.hidden = false;
}

export function hide() {
  if (_el) _el.hidden = true;
  _stopScroll();
}

// ── Scroll ────────────────────────────────────────────────

function _startScroll() {
  _stopScroll();
  _scrollX = 0;
  _paused  = false;
  _lastTs  = null;
  if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';

  // CHG-1 : attendre 2 frames pour que le navigateur ait calculé les dimensions.
  // Sans ça, scrollWidth = 0 au moment de la mesure.
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      // Vérifier qu'il y a vraiment quelque chose à scroller
      const containerW = _el ? _el.getBoundingClientRect().width : 0;
      const contentW   = _scrollEl ? _scrollEl.scrollWidth : 0;
      if (contentW <= containerW + 10) {
        // Tout tient dans le bandeau — pas de scroll nécessaire
        return;
      }
      _rafId = requestAnimationFrame(_tick);
    });
  });
}

function _stopScroll() {
  if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null; }
  if (_pauseTimer) { clearTimeout(_pauseTimer); _pauseTimer = null; }
  _paused = false;
  _lastTs = null;
}

function _tick(ts) {
  if (!_scrollEl || !_el || _paused) {
    // Pendant la pause on re-planifie quand même pour reprendre
    if (_paused) _rafId = requestAnimationFrame(_tick);
    return;
  }

  // CHG-2 : cap à 100ms pour éviter les sauts après tab switch / mise en veille
  const dt = _lastTs ? Math.min(ts - _lastTs, 100) : 16;
  _lastTs  = ts;

  // CHG-3 : re-mesurer à chaque tick (résistant aux redimensionnements)
  const containerW = _el.getBoundingClientRect().width;
  const contentW   = _scrollEl.scrollWidth;

  if (contentW <= containerW + 10) {
    // Plus rien à scroller (ex: contenu changé entre deux ticks)
    _stopScroll();
    _scrollX = 0;
    _scrollEl.style.transform = 'translateX(0)';
    return;
  }

  _scrollX += (SCROLL_PX_PER_SEC * dt) / 1000;
  const maxScroll = contentW - containerW;

  if (_scrollX >= maxScroll) {
    _scrollX = maxScroll;
    _scrollEl.style.transform = `translateX(-${_scrollX}px)`;
    _paused = true;

    // Pause → reset → reprise
    _pauseTimer = setTimeout(() => {
      _scrollX = 0;
      _paused  = false;
      _lastTs  = null;
      if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';
      // Laisser un frame pour que le reset soit peint avant de reprendre
      requestAnimationFrame(() => {
        _rafId = requestAnimationFrame(_tick);
      });
    }, PAUSE_MS);

    return; // on ne re-planifie pas — le setTimeout s'en charge
  }

  _scrollEl.style.transform = `translateX(-${_scrollX}px)`;
  _rafId = requestAnimationFrame(_tick);
}

// ── Helpers ───────────────────────────────────────────────

function _lineColor(ligne) {
  let hash = 0;
  for (let i = 0; i < String(ligne).length; i++)
    hash = String(ligne).charCodeAt(i) + ((hash << 5) - hash);
  return `hsl(${Math.abs(hash) % 360}, 70%, 55%)`;
}

function _esc(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}