/**
 * js/reader.js — Xëtu V1.0
 * Bandeau "arrêt courant" affiché au-dessus du bouton "Je vois un bus ici"
 * quand un bus est sélectionné et animé sur la carte.
 *
 * Reçoit des updates via updateReader(busId, ligne, arrets, currentIdx).
 * Masqué automatiquement quand aucun bus n'est sélectionné.
 */

let _el       = null;
let _scrollEl = null;
let _rafId    = null;
let _scrollX  = 0;
let _paused   = false;

// ── Init ──────────────────────────────────────────────────

export function initReader() {
  _el = document.getElementById('bus-reader');
  _scrollEl = _el?.querySelector('.reader-scroll');
  if (!_el) return;
  hide();
}

// ── API publique ──────────────────────────────────────────

/**
 * Met à jour le bandeau avec la progression actuelle du bus.
 * @param {string} ligne
 * @param {Array}  arrets   — liste des arrêts [{nom}]
 * @param {number} idx      — index de l'arrêt courant
 */
export function updateReader(ligne, arrets, idx) {
  if (!_el || !_scrollEl || !arrets?.length) return;

  const color = _lineColor(ligne);

  // Construire la chaîne : arrêts avec l'arrêt courant mis en avant
  const parts = arrets.map((a, i) => {
    const nom = a.nom || a.name || `Arrêt ${i + 1}`;
    if (i === idx) {
      return `<span class="reader-current" style="color:${color}">${nom}</span>`;
    }
    if (i < idx) {
      return `<span class="reader-past">${nom}</span>`;
    }
    return `<span class="reader-future">${nom}</span>`;
  });

  _scrollEl.innerHTML =
    `<span class="reader-badge" style="background:${color}">Bus ${ligne}</span>` +
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
  _scrollX = 0;
  if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';
}

// ── Scroll automatique ────────────────────────────────────

const SCROLL_SPEED = 0.4; // px/frame
const PAUSE_MS     = 2000;

function _startScroll() {
  _stopScroll();
  _scrollX = 0;
  _paused  = false;
  if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';
  _rafId = requestAnimationFrame(_tick);
}

function _stopScroll() {
  if (_rafId) cancelAnimationFrame(_rafId);
  _rafId = null;
}

function _tick() {
  if (!_scrollEl) return;
  if (_paused) { _rafId = requestAnimationFrame(_tick); return; }

  const containerW = _el.offsetWidth;
  const contentW   = _scrollEl.scrollWidth;

  if (contentW <= containerW) {
    // Pas besoin de scroller
    _stopScroll();
    return;
  }

  _scrollX += SCROLL_SPEED;

  // Arrivé à la fin → pause puis reset
  if (_scrollX > contentW - containerW + 40) {
    _paused = true;
    setTimeout(() => {
      _scrollX = 0;
      if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';
      _paused = false;
    }, PAUSE_MS);
  } else {
    _scrollEl.style.transform = `translateX(-${_scrollX}px)`;
  }

  _rafId = requestAnimationFrame(_tick);
}

// ── Couleur par hash ligne (FIX-8) ───────────────────────

function _lineColor(ligne) {
  let hash = 0;
  for (let i = 0; i < ligne.length; i++) {
    hash = ligne.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 70%, 55%)`;
}
