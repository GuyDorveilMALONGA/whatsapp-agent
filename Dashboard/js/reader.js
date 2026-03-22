/**
 * js/reader.js — Xëtu V1.1
 * Bandeau "arrêt courant" affiché au-dessus du bouton "Je vois un bus ici"
 *
 * FIX V1.1 : SCROLL_SPEED 0.4 → 0.02, PAUSE_MS 2000 → 3500
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

export function updateReader(ligne, arrets, idx) {
  if (!_el || !_scrollEl || !arrets?.length) return;

  const color = _lineColor(ligne);

  const parts = arrets.map((a, i) => {
    const nom = a.nom || a.name || `Arrêt ${i + 1}`;
    if (i === idx) {
      return `<span class="reader-current" style="color:${color};font-weight:700;text-decoration:underline">${nom}</span>`;
    }
    if (i < idx) {
      return `<span class="reader-past" style="opacity:0.4">${nom}</span>`;
    }
    return `<span class="reader-future">${nom}</span>`;
  });

  _scrollEl.innerHTML =
    `<span class="reader-badge" style="background:${color};color:#fff;padding:2px 8px;border-radius:4px;font-weight:700;margin-right:8px">Bus ${ligne}</span>` +
    parts.join('<span class="reader-sep" style="margin:0 4px;opacity:0.4">›</span>');

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

const SCROLL_SPEED = 0.02;  // px/frame — lent et lisible
const PAUSE_MS     = 3500;  // pause à la fin avant reset

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
    _stopScroll();
    return;
  }

  _scrollX += SCROLL_SPEED;

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
  return `hsl(${Math.abs(hash) % 360}, 70%, 55%)`;
}