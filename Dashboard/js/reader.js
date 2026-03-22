/**
 * js/reader.js — Xëtu V2.1
 * V2.1 : #bus-reader ancré en bas de #map-home (position absolute)
 *        Ne déborde plus sur le bouton "Signaler un bus"
 */

let _el         = null;
let _scrollEl   = null;
let _rafId      = null;
let _scrollX    = 0;
let _paused     = false;
let _pauseTimer = null;
let _lastTs     = null;

const SCROLL_PX_PER_SEC = 28;
const PAUSE_MS          = 3000;

// ── Init ──────────────────────────────────────────────────────

export function initReader() {
  _injectCSS();
  _el       = document.getElementById('bus-reader');
  _scrollEl = _el?.querySelector('.reader-scroll');
  if (!_el) { console.warn('[Reader] #bus-reader introuvable'); return; }
  hide();
}

// ── CSS ───────────────────────────────────────────────────────

function _injectCSS() {
  if (document.getElementById('reader-style')) return;
  const style = document.createElement('style');
  style.id    = 'reader-style';
  style.textContent = `
    #bus-reader {
      position: absolute !important;
      bottom: 0 !important;
      left: 0 !important;
      right: 0 !important;
      z-index: 400 !important;
      display: flex !important;
      align-items: center !important;
      width: 100% !important;
      height: 36px !important;
      overflow: hidden !important;
      flex-shrink: 0 !important;
      background: rgba(10,15,30,0.82);
      backdrop-filter: blur(4px);
      -webkit-backdrop-filter: blur(4px);
      border-top: 1px solid var(--border, rgba(255,255,255,0.07));
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
    .reader-current { font-weight: 700; text-decoration: underline; font-size: 12px; flex-shrink: 0; }
    .reader-past    { opacity: 0.35; font-size: 12px; flex-shrink: 0; }
    .reader-future  { opacity: 0.75; font-size: 12px; flex-shrink: 0; }
    .reader-sep     { margin: 0 5px; opacity: 0.3; font-size: 11px; flex-shrink: 0; }
  `;
  document.head.appendChild(style);
}

// ── API publique ──────────────────────────────────────────────

export function updateReader(ligne, arrets, idx) {
  if (!_el || !_scrollEl || !arrets?.length) return;

  const color = _lineColor(ligne);

  const parts = arrets.map((a, i) => {
    const nom  = a.nom || a.name || `Arrêt ${i + 1}`;
    const safe = nom.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    if (i === idx)  return `<span class="reader-current" style="color:${color}">${safe}</span>`;
    if (i < idx)    return `<span class="reader-past">${safe}</span>`;
    return              `<span class="reader-future">${safe}</span>`;
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
}

// ── Scroll ────────────────────────────────────────────────────

function _startScroll() {
  _stopScroll();

  _scrollX = 0;
  _paused  = false;
  _lastTs  = null;
  if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';

  requestAnimationFrame(() => {
    requestAnimationFrame((ts) => {
      const containerW = _el ? _el.getBoundingClientRect().width : 0;
      const contentW   = _scrollEl ? _scrollEl.scrollWidth : 0;
      if (contentW <= containerW + 10) return;
      _lastTs = ts;
      _rafId  = requestAnimationFrame(_tick);
    });
  });
}

function _stopScroll() {
  if (_rafId)      { cancelAnimationFrame(_rafId); _rafId = null; }
  if (_pauseTimer) { clearTimeout(_pauseTimer);    _pauseTimer = null; }
  _paused = false;
  _lastTs = null;
}

function _tick(ts) {
  if (!_scrollEl || !_el) return;

  const dt     = Math.min(ts - (_lastTs || ts), 100);
  _lastTs      = ts;

  const containerW = _el.getBoundingClientRect().width;
  const contentW   = _scrollEl.scrollWidth;

  if (contentW <= containerW + 10) {
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
    _rafId = null;
    _pauseTimer = setTimeout(() => {
      _scrollX = 0;
      if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';
      _pauseTimer = null;
      requestAnimationFrame((ts2) => {
        _lastTs = ts2;
        _rafId  = requestAnimationFrame(_tick);
      });
    }, PAUSE_MS);
    return;
  }

  _scrollEl.style.transform = `translateX(-${_scrollX}px)`;
  _rafId = requestAnimationFrame(_tick);
}

// ── Couleur par hash ──────────────────────────────────────────

function _lineColor(ligne) {
  let hash = 0;
  for (let i = 0; i < String(ligne).length; i++)
    hash = String(ligne).charCodeAt(i) + ((hash << 5) - hash);
  return `hsl(${Math.abs(hash) % 360}, 70%, 55%)`;
}