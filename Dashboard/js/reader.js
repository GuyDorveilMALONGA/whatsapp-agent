/**
 * js/reader.js — Xëtu V1.2
 * FIX V1.2 : scroll basé sur deltaTime (ms) — 22px/sec indépendant du framerate
 */

let _el       = null;
let _scrollEl = null;
let _rafId    = null;
let _scrollX  = 0;
let _paused   = false;
let _lastTs   = null;

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
  _lastTs  = null;
  if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';
}

// ── Scroll basé sur le temps (indépendant du framerate) ──

const SCROLL_PX_PER_SEC = 22;  // 22px/seconde — lent et lisible
const PAUSE_MS          = 3500;

function _startScroll() {
  _stopScroll();
  _scrollX = 0;
  _paused  = false;
  _lastTs  = null;
  if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';
  _rafId = requestAnimationFrame(_tick);
}

function _stopScroll() {
  if (_rafId) cancelAnimationFrame(_rafId);
  _rafId = null;
}

function _tick(ts) {
  if (!_scrollEl) return;

  if (_paused) { _lastTs = ts; _rafId = requestAnimationFrame(_tick); return; }

  if (!_lastTs) _lastTs = ts;
  const dt = Math.min(ts - _lastTs, 100);
  _lastTs  = ts;

  const containerW = _el.offsetWidth;
  const contentW   = _scrollEl.scrollWidth;

  if (contentW <= containerW) { _stopScroll(); return; }

  _scrollX += (SCROLL_PX_PER_SEC * dt) / 1000;

  if (_scrollX > contentW - containerW + 40) {
    _paused  = true;
    _scrollX = contentW - containerW + 40;
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