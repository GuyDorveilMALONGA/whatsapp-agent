/**
 * js/toast.js
 * Notifications toast légères — success, error, info.
 *
 * API :
 *   Toast.success(msg)
 *   Toast.error(msg, { retry, fallbackUrl, fallbackLabel })
 *   Toast.info(msg)
 *
 * Dépend de : rien (module autonome)
 */

// ── Conteneur singleton ───────────────────────────────────

function _getContainer() {
  let el = document.getElementById('toast-container');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast-container';
    el.setAttribute('aria-live', 'polite');
    el.setAttribute('aria-atomic', 'false');
    el.style.cssText = `
      position: fixed;
      bottom: 1.5rem;
      right: 1.5rem;
      z-index: 9999;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      pointer-events: none;
    `;
    document.body.appendChild(el);
  }
  return el;
}

// ── Création d'un toast ───────────────────────────────────

function _show(msg, type = 'info', options = {}) {
  const container = _getContainer();

  const toast = document.createElement('div');
  toast.setAttribute('role', 'alert');
  toast.style.cssText = `
    background: ${type === 'success' ? '#1a7f4b' : type === 'error' ? '#b91c1c' : '#1e3a5f'};
    color: #fff;
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
    font-size: 0.9rem;
    max-width: 320px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    pointer-events: auto;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    animation: toastIn 0.2s ease;
  `;

  // Message principal
  const msgEl = document.createElement('span');
  msgEl.textContent = msg;
  toast.appendChild(msgEl);

  // Bouton retry (optionnel)
  if (options.retry) {
    const btn = document.createElement('button');
    btn.textContent = '🔄 Réessayer';
    btn.style.cssText = `
      background: rgba(255,255,255,0.2);
      border: none;
      color: #fff;
      padding: 0.3rem 0.6rem;
      border-radius: 0.3rem;
      cursor: pointer;
      font-size: 0.85rem;
      align-self: flex-start;
    `;
    btn.addEventListener('click', () => {
      options.retry();
      _dismiss(toast);
    });
    toast.appendChild(btn);
  }

  // Lien fallback (optionnel)
  if (options.fallbackUrl) {
    const link = document.createElement('a');
    link.href = options.fallbackUrl;
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = options.fallbackLabel || 'Voir';
    link.style.cssText = `
      color: #fde68a;
      font-size: 0.85rem;
      text-decoration: underline;
    `;
    toast.appendChild(link);
  }

  container.appendChild(toast);

  // Auto-dismiss
  const delay = type === 'error' ? 6000 : 3500;
  setTimeout(() => _dismiss(toast), delay);
}

function _dismiss(toast) {
  toast.style.opacity = '0';
  toast.style.transition = 'opacity 0.3s ease';
  setTimeout(() => toast.remove(), 300);
}

// ── API publique ──────────────────────────────────────────

export function success(msg) {
  _show(msg, 'success');
}

export function error(msg, options = {}) {
  _show(msg, 'error', options);
}

export function info(msg) {
  _show(msg, 'info');
}

// Export default pour compatibilité import Toast from './toast.js'
const Toast = { success, error, info };
export default Toast;