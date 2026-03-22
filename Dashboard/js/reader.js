/**
 * js/reader.js — Xëtu V2.0
 * BUG-1 fix : scroll qui s'arrête après la première pause
 *   - Pendant la pause : on ne re-planifie PAS le tick (économie CPU)
 *   - Après la pause : le setTimeout relance _startScroll() proprement
 *   - !important sur display:flex garantit que getBoundingClientRect donne une vraie valeur
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

// ── CSS — !important sur display et width pour forcer la mesure ──

function _injectCSS() {
  if (document.getElementById('reader-style')) return;
  const style = document.createElement('style');
  style.id    = 'reader-style';
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
  _stopScroll();  // annule tout cycle précédent proprement

  _scrollX = 0;
  _paused  = false;
  _lastTs  = null;
  if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';

  // 2 frames d'attente : garantit que le DOM est peint et que
  // getBoundingClientRect() / scrollWidth retournent des valeurs réelles.
  requestAnimationFrame(() => {
    requestAnimationFrame((ts) => {
      const containerW = _el ? _el.getBoundingClientRect().width : 0;
      const contentW   = _scrollEl ? _scrollEl.scrollWidth : 0;
      if (contentW <= containerW + 10) return; // tout tient — pas de scroll
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

  // cap 100ms pour éviter les sauts après tab switch ou mise en veille
  const dt     = Math.min(ts - (_lastTs || ts), 100);
  _lastTs      = ts;

  // re-mesurer à chaque tick — résistant aux redimensionnements
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
    // Fin du défilement — afficher la fin, puis pause, puis relancer
    _scrollX = maxScroll;
    _scrollEl.style.transform = `translateX(-${_scrollX}px)`;
    _rafId = null;  // stop le RAF — le setTimeout reprend le contrôle
    _pauseTimer = setTimeout(() => {
      _scrollX = 0;
      if (_scrollEl) _scrollEl.style.transform = 'translateX(0)';
      _pauseTimer = null;
      // Relancer un cycle complet proprement (avec les 2 frames d'attente)
      requestAnimationFrame((ts2) => {
        _lastTs = ts2;
        _rafId  = requestAnimationFrame(_tick);
      });
    }, PAUSE_MS);
    return;  // NE PAS re-planifier _tick ici — le setTimeout s'en charge
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