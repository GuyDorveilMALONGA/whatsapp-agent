/**
 * js/reader.js — Xëtu V1.2 FINAL
 * FIX : scroll basé sur deltaTime réel (px/sec) — indépendant du framerate
 * Le CSS du bandeau est injecté ici directement pour garantir son existence
 */

let _el       = null;
let _scrollEl = null;
let _rafId    = null;
let _scrollX  = 0;
let _paused   = false;
let _lastTs   = null;

const SCROLL_PX_PER_SEC = 25;   // px/seconde — lent, lisible
const PAUSE_MS          = 4000; // pause à la fin avant reset

// ── Init : injecte le CSS si absent + récupère les éléments ──

export function initReader() {
  _injectCSS();
  _el       = document.getElementById('bus-reader');
  _scrollEl = _el?.querySelector('.reader-scroll');
  if (!_el) { console.warn('[Reader] #bus-reader introuvable'); return; }
  hide();
}

// ── CSS injecté en JS — garantit que le style existe ─────────

function _injectCSS() {
  if (document.getElementById('reader-style')) return;
  const style = document.createElement('style');
  style.id    = 'reader-style';
  style.textContent = `
    #bus-reader {
      position: relative;
      width: 100%;
      overflow: hidden;
      background: var(--surface2, #1a2235);
      border-bottom: 1px solid var(--border, rgba(255,255,255,0.07));
      padding: 8px 14px;
      flex-shrink: 0;
      height: 36px;
      display: flex;
      align-items: center;
      white-space: nowrap;
    }
    #bus-reader[hidden] { display: none !important; }
    .reader-scroll {
      display: inline-flex;
      align-items: center;
      gap: 0;
      white-space: nowrap;
      will-change: transform;
      font-size: 12px;
      color: var(--text-dim, #c4cde0);
    }
    .reader-badge {
      border-radius: 4px;
      padding: 2px 8px;
      font-weight: 700;
      font-size: 11px;
      margin-right: 10px;
      flex-shrink: 0;
    }
    .reader-current {
      font-weight: 700;
      text-decoration: underline;
      font-size: 12px;
    }
    .reader-past    { opacity: 0.35; font-size: 12px; }
    .reader-future  { opacity: 0.75; font-size: 12px; }
    .reader-sep     { margin: 0 5px; opacity: 0.3; font-size: 11px; }
  `;
  document.head.appendChild(style);
}

// ── API publique ──────────────────────────────────────────────

export function updateReader(ligne, arrets, idx) {
  if (!_el || !_scrollEl || !arrets?.length) return;

  const color = _lineColor(ligne);

  const parts = arrets.map((a, i) => {
    const nom = a.nom || a.name || `Arrêt ${i + 1}`;
    if (i === idx)  return `<span class="reader-current" style="color:${color}">${nom}</span>`;
    if (i < idx)    return `<span class="reader-past">${nom}</span>`;
    return              `<span class="reader-future">${nom}</span>`;
  });

  _scrollEl.innerHTML =
    `<span class="reader-badge" style="background:${color};color:#fff">Bus ${ligne}</span>` +
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
  _lastTs  = null;
  if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';
}

// ── Scroll basé sur le temps réel ────────────────────────────

function _startScroll() {
  _stopScroll();
  _scrollX = 0;
  _paused  = false;
  _lastTs  = null;
  if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';

  // Attendre 1 frame que le DOM soit rendu avant de mesurer
  requestAnimationFrame(() => {
    requestAnimationFrame((ts) => {
      _lastTs = ts;
      _rafId  = requestAnimationFrame(_tick);
    });
  });
}

function _stopScroll() {
  if (_rafId) cancelAnimationFrame(_rafId);
  _rafId = null;
}

function _tick(ts) {
  if (!_scrollEl || !_el) return;
  if (_paused) { _lastTs = ts; _rafId = requestAnimationFrame(_tick); return; }

  const dt         = Math.min(ts - (_lastTs || ts), 100); // cap 100ms
  _lastTs          = ts;
  const containerW = _el.getBoundingClientRect().width;
  const contentW   = _scrollEl.scrollWidth;

  // Pas besoin de scroller si le contenu rentre
  if (contentW <= containerW + 10) { _stopScroll(); return; }

  _scrollX += (SCROLL_PX_PER_SEC * dt) / 1000;

  const maxScroll = contentW - containerW;
  if (_scrollX >= maxScroll) {
    _scrollX = maxScroll;
    _scrollEl.style.transform = `translateX(-${_scrollX}px)`;
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

// ── Couleur par hash ──────────────────────────────────────────

function _lineColor(ligne) {
  let hash = 0;
  for (let i = 0; i < String(ligne).length; i++)
    hash = String(ligne).charCodeAt(i) + ((hash << 5) - hash);
  return `hsl(${Math.abs(hash) % 360}, 70%, 55%)`;
}