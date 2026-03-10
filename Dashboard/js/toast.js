/**
 * js/toast.js
 * Système de notifications toast réutilisable.
 * API : Toast.success(), Toast.error(), Toast.info()
 */

const MAX_TOASTS = 3;
const AUTO_DISMISS_MS = 4000;

let _container = null;

function _getContainer() {
  if (!_container) {
    _container = document.getElementById('toast-container');
    if (!_container) {
      _container = document.createElement('div');
      _container.id = 'toast-container';
      _container.setAttribute('aria-live', 'polite');
      _container.setAttribute('aria-atomic', 'false');
      document.body.appendChild(_container);
    }
  }
  return _container;
}

function _removeToast(el) {
  el.classList.add('removing');
  el.addEventListener('animationend', () => el.remove(), { once: true });
  // Fallback si animationend ne se déclenche pas
  setTimeout(() => el.remove(), 400);
}

function _show(type, message, options = {}) {
  const container = _getContainer();

  // Limiter à MAX_TOASTS
  const existing = container.querySelectorAll('.toast');
  if (existing.length >= MAX_TOASTS) {
    _removeToast(existing[0]);
  }

  const icons = { success: '✅', error: '❌', info: 'ℹ️' };

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.setAttribute('role', type === 'error' ? 'alert' : 'status');

  let actionsHtml = '';
  if (options.retry) {
    actionsHtml += `<button class="toast-retry" data-action="retry">Réessayer</button>`;
  }
  actionsHtml += `<button class="toast-dismiss" aria-label="Fermer" data-action="dismiss">×</button>`;

  toast.innerHTML = `
    <span class="toast-icon" aria-hidden="true">${icons[type]}</span>
    <span class="toast-message">${message}</span>
    ${actionsHtml}
  `;

  // Gestion des clics (retry + dismiss)
  toast.addEventListener('click', (e) => {
    const action = e.target.closest('[data-action]')?.dataset.action;
    if (action === 'dismiss') _removeToast(toast);
    if (action === 'retry' && options.retry) {
      _removeToast(toast);
      options.retry();
    }
  });

  // Swipe-to-dismiss (mobile)
  let startX = 0;
  toast.addEventListener('touchstart', (e) => { startX = e.touches[0].clientX; }, { passive: true });
  toast.addEventListener('touchend', (e) => {
    if (Math.abs(e.changedTouches[0].clientX - startX) > 80) _removeToast(toast);
  }, { passive: true });

  container.appendChild(toast);

  // Auto-dismiss
  const timer = setTimeout(() => _removeToast(toast), AUTO_DISMISS_MS);
  toast.addEventListener('mouseenter', () => clearTimeout(timer));

  return toast;
}

const Toast = {
  success: (message) => _show('success', message),
  error:   (message, options = {}) => _show('error', message, options),
  info:    (message) => _show('info', message),
};

export default Toast;
