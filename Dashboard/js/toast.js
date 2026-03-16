/**
 * js/toast.js — V1.0 App Passager
 * Notifications toast légères.
 */

const DURATION = 3000;

function _show(message, type) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast--out');
    toast.addEventListener('animationend', () => toast.remove(), { once: true });
  }, DURATION);
}

export function success(msg) { _show(msg, 'success'); }
export function error(msg)   { _show(msg, 'error');   }
export function info(msg)    { _show(msg, 'info');     }

export default { success, error, info };
