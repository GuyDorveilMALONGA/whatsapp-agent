/**
 * js/reader.js — Xëtu V3.8
 * V3.8 : Fade réel via ::before/::after sur #header-reader
 *        Gradient fond → transparent sur les bords gauche et droit
 */

let _containerEl = null;

export function initReader() {
  _injectCSS();
  _buildContainer();
}

function _injectCSS() {
  if (document.getElementById('reader-style')) return;
  const style = document.createElement('style');
  style.id    = 'reader-style';
  style.textContent = `
    #header-reader {
      position: absolute;
      left: 0;
      right: 0;
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      pointer-events: none;
      overflow: hidden;
    }

    /* Fade gauche — recouvre le début de prev */
    #header-reader::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 60px;
      background: linear-gradient(to right, #0A0F1E 0%, transparent 100%);
      z-index: 1;
      pointer-events: none;
    }

    /* Fade droit — recouvre la fin de next */
    #header-reader::after {
      content: '';
      position: absolute;
      right: 0;
      top: 0;
      bottom: 0;
      width: 60px;
      background: linear-gradient(to left, #0A0F1E 0%, transparent 100%);
      z-index: 1;
      pointer-events: none;
    }

    #header-reader[hidden] { display: none !important; }

    .hr-stops {
      display: flex;
      align-items: center;
      gap: 3px;
      white-space: nowrap;
      transition: opacity 0.25s ease, transform 0.25s ease;
      position: relative;
      z-index: 0;
    }

    .hr-stop--prev,
    .hr-stop--next {
      font-family: 'Inter', sans-serif;
      font-size: 8px;
      font-weight: 400;
      color: rgba(255,255,255,0.25);
      max-width: 50px;
      overflow: hidden;
      text-overflow: clip;
      flex-shrink: 1;
    }

    .hr-stop--current {
      font-family: 'Inter', sans-serif;
      font-size: 9px;
      font-weight: 700;
      color: #FF6B35;
      max-width: 130px;
      flex-shrink: 0;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .hr-sep {
      font-size: 7px;
      color: rgba(255, 107, 53, 0.2);
      flex-shrink: 0;
    }
  `;
  document.head.appendChild(style);
}

function _buildContainer() {
  const header = document.getElementById('app-header');
  if (!header) return;

  const pos = getComputedStyle(header).position;
  if (pos === 'static') header.style.position = 'relative';

  _containerEl = document.createElement('div');
  _containerEl.id     = 'header-reader';
  _containerEl.hidden = true;
  _containerEl.innerHTML = `<div class="hr-stops"></div>`;
  header.appendChild(_containerEl);
}

export function updateReader(ligne, arrets, currentIdx) {
  if (!_containerEl || !arrets?.length) return;

  const prev    = arrets[currentIdx - 1];
  const current = arrets[currentIdx];
  const next    = arrets[currentIdx + 1];

  if (!current) return;

  const stopsEl = _containerEl.querySelector('.hr-stops');
  if (!stopsEl) return;

  let html = '';

  if (prev) {
    html += `<span class="hr-stop hr-stop--prev">${_esc(_nom(prev))}</span>`;
    html += `<span class="hr-sep">›</span>`;
  }

  html += `<span class="hr-stop hr-stop--current">${_esc(_nom(current))}</span>`;

  if (next) {
    html += `<span class="hr-sep">›</span>`;
    html += `<span class="hr-stop hr-stop--next">${_esc(_nom(next))}</span>`;
  }

  stopsEl.style.opacity   = '0';
  stopsEl.style.transform = 'translateY(3px)';
  stopsEl.innerHTML = html;

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      stopsEl.style.opacity   = '1';
      stopsEl.style.transform = 'translateY(0)';
    });
  });

  show();
}

export function show() {
  if (_containerEl) _containerEl.hidden = false;
}

export function hide() {
  if (_containerEl) _containerEl.hidden = true;
}

function _nom(arret) {
  return arret?.nom || arret?.name || '';
}

function _esc(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}