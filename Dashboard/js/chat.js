/**
 * js/chat.js — V2.0
 * UI chat — bulles de messages, suggestions rapides, typing indicator.
 *
 * MIGRATIONS V2.0 :
 *   - showWelcome(text, suggestions, firstVisit) — affiche le welcome
 *     uniquement si firstVisit=true (cohérent avec ws.js V2 + websocket.py V1.5)
 *   - showTyping() ne s'appelle plus dans _doSend() — piloté par
 *     { type: "typing", active } venant du serveur via ws.js onTyping
 *   - appendMessage ne masque plus le typing — c'est onTyping(false) qui le fait
 *   - Nouveau : Chat.setTyping(active) — API publique pour ws.js
 *
 * RÈGLE : ne parle jamais à map.js, ui.js, mobile.js directement.
 *         Reçoit ses données via l'API publique.
 *         Communique vers l'extérieur uniquement via les callbacks injectés.
 *
 * API publique :
 *   Chat.init({ onSend, onClose })
 *   Chat.open()
 *   Chat.close()
 *   Chat.toggle()
 *   Chat.showWelcome(text, suggestions, firstVisit)
 *   Chat.appendMessage(role, text)   — 'user' | 'bot'
 *   Chat.setTyping(active)           — NOUVEAU : piloté par le serveur
 *   Chat.setSuggestions(list)
 *   Chat.setStatus(status)           — 'connecting' | 'open' | 'closed' | 'failed'
 *   Chat.isOpen()
 */

// ── Constantes ────────────────────────────────────────────

const MAX_INPUT_LENGTH = 500;

// ── État interne ──────────────────────────────────────────

let _isOpen     = false;
let _onSend     = null;
let _onClose    = null;
let _typingEl   = null;
let _inputEl    = null;
let _messagesEl = null;
let _sendBtn    = null;
let _statusDot  = null;
let _fab        = null;

// ── INIT ─────────────────────────────────────────────────

export function init({ onSend, onClose } = {}) {
  _onSend  = onSend;
  _onClose = onClose;

  _buildDOM();
  _attachEvents();
}

// ── DOM ───────────────────────────────────────────────────

function _buildDOM() {
  _fab = document.createElement('button');
  _fab.id        = 'chat-fab';
  _fab.className = 'chat-fab';
  _fab.setAttribute('aria-label', 'Ouvrir le chat Xëtu');
  _fab.innerHTML = '💬';
  document.body.appendChild(_fab);

  const win = document.createElement('div');
  win.id        = 'chat-window';
  win.className = 'chat-window';
  win.setAttribute('role', 'dialog');
  win.setAttribute('aria-label', 'Chat avec Xëtu');
  win.setAttribute('aria-hidden', 'true');
  win.hidden = true;

  win.innerHTML = `
    <div class="chat-header">
      <div class="chat-header-info">
        <span class="chat-header-avatar" aria-hidden="true">🚌</span>
        <div>
          <div class="chat-header-name">Xëtu</div>
          <div class="chat-header-status">
            <span class="chat-status-dot" id="chat-status-dot"></span>
            <span class="chat-status-label" id="chat-status-label">Connexion...</span>
          </div>
        </div>
      </div>
      <button class="chat-close-btn" id="chat-close-btn" aria-label="Fermer le chat">✕</button>
    </div>

    <div class="chat-messages" id="chat-messages" role="log" aria-live="polite" aria-label="Messages">
    </div>

    <div class="chat-suggestions" id="chat-suggestions" aria-label="Suggestions rapides">
    </div>

    <div class="chat-composer">
      <input
        class="chat-input"
        id="chat-input"
        type="text"
        placeholder="Bus 15 à Liberté 5…"
        maxlength="${MAX_INPUT_LENGTH}"
        autocomplete="off"
        autocorrect="off"
        spellcheck="false"
        aria-label="Message"
      />
      <button class="chat-send-btn" id="chat-send-btn" aria-label="Envoyer" disabled>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
        </svg>
      </button>
    </div>
  `;

  document.body.appendChild(win);

  _messagesEl = win.querySelector('#chat-messages');
  _inputEl    = win.querySelector('#chat-input');
  _sendBtn    = win.querySelector('#chat-send-btn');
  _statusDot  = win.querySelector('#chat-status-dot');
}

// ── EVENTS ────────────────────────────────────────────────

function _attachEvents() {
  _fab.addEventListener('click', toggle);

  document.getElementById('chat-close-btn')
    .addEventListener('click', close);

  _inputEl.addEventListener('input', () => {
    _sendBtn.disabled = _inputEl.value.trim().length === 0;
  });

  _inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      _doSend();
    }
  });

  _sendBtn.addEventListener('click', _doSend);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _isOpen) close();
  });

  if (window.visualViewport) {
    const _onViewportChange = () => {
      if (!_isOpen) return;
      const win = document.getElementById('chat-window');
      if (!win) return;

      const vv        = window.visualViewport;
      const keyboardH = window.innerHeight - vv.height - vv.offsetTop;

      if (keyboardH > 100) {
        win.style.bottom    = (keyboardH + 8) + 'px';
        win.style.top       = 'auto';
        win.style.maxHeight = (vv.height - 70) + 'px';
      } else {
        win.style.bottom    = '';
        win.style.maxHeight = '';
      }
      if (_messagesEl) _messagesEl.scrollTop = _messagesEl.scrollHeight;
    };

    window.visualViewport.addEventListener('resize', _onViewportChange);
    window.visualViewport.addEventListener('scroll', _onViewportChange);
  }
}

function _doSend() {
  const text = _inputEl.value.trim();
  if (!text || text.length > MAX_INPUT_LENGTH) return;

  appendMessage('user', text);
  _inputEl.value    = '';
  _sendBtn.disabled = true;
  _clearSuggestions();

  // Ne pas appeler showTyping() ici — le serveur envoie { type: "typing", active: true }
  // juste après avoir reçu le message. C'est onTyping() dans ws.js qui pilote.

  _onSend?.(text);
}

// ── OPEN / CLOSE / TOGGLE ─────────────────────────────────

export function open() {
  if (_isOpen) return;
  _isOpen = true;

  const win = document.getElementById('chat-window');
  win.hidden = false;
  win.setAttribute('aria-hidden', 'false');
  win.classList.add('chat-window--open');

  _fab.setAttribute('aria-label', 'Fermer le chat');
  _fab.innerHTML = '✕';
  _fab.classList.add('chat-fab--active');

  _inputEl.focus();
}

export function close() {
  if (!_isOpen) return;
  _isOpen = false;

  const win = document.getElementById('chat-window');
  win.classList.remove('chat-window--open');

  win.addEventListener('transitionend', () => {
    win.hidden = true;
    win.setAttribute('aria-hidden', 'true');
  }, { once: true });

  _fab.setAttribute('aria-label', 'Ouvrir le chat Xëtu');
  _fab.innerHTML = '💬';
  _fab.classList.remove('chat-fab--active');

  _onClose?.();
}

export function toggle() {
  _isOpen ? close() : open();
}

export function isOpen() {
  return _isOpen;
}

// ── WELCOME ───────────────────────────────────────────────

/**
 * Appelé par ws.js onWelcome(text, suggestions, firstVisit).
 * - firstVisit=true  → affiche la bulle de bienvenue + suggestions
 * - firstVisit=false → affiche uniquement les suggestions (reconnexion silencieuse)
 */
export function showWelcome(text, suggestions = [], firstVisit = false) {
  if (firstVisit && text) {
    appendMessage('bot', text);
  }
  setSuggestions(suggestions);
}

// ── MESSAGES ─────────────────────────────────────────────

/**
 * @param {'user'|'bot'} role
 * @param {string} text — Markdown minimal (*bold*, _italic_)
 */
export function appendMessage(role, text) {
  // Ne masque plus le typing ici — c'est setTyping(false) qui s'en charge
  const wrap = document.createElement('div');
  wrap.className = `chat-msg chat-msg--${role}`;
  wrap.setAttribute('role', 'listitem');

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  bubble.innerHTML = _formatText(text);

  wrap.appendChild(bubble);
  _messagesEl.appendChild(wrap);
  _scrollToBottom();
}

// ── TYPING ────────────────────────────────────────────────

/**
 * Piloté par { type: "typing", active } venant du serveur.
 * ws.js appelle Chat.setTyping(active) via le handler onTyping.
 */
export function setTyping(active) {
  if (active) {
    _showTyping();
  } else {
    _hideTyping();
  }
}

function _showTyping() {
  if (_typingEl) return;

  _typingEl = document.createElement('div');
  _typingEl.className = 'chat-msg chat-msg--bot chat-typing';
  _typingEl.setAttribute('aria-label', 'Xëtu est en train d\'écrire');
  _typingEl.innerHTML = `
    <div class="chat-bubble chat-bubble--typing">
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    </div>
  `;
  _messagesEl.appendChild(_typingEl);
  _scrollToBottom();
}

function _hideTyping() {
  if (_typingEl) {
    _typingEl.remove();
    _typingEl = null;
  }
}

// Gardées pour compatibilité ascendante si appelées ailleurs
export const showTyping = () => _showTyping();
export const hideTyping = () => _hideTyping();

// ── SUGGESTIONS ──────────────────────────────────────────

export function setSuggestions(list = []) {
  const container = document.getElementById('chat-suggestions');
  if (!container) return;
  container.innerHTML = '';

  list.forEach(text => {
    const chip = document.createElement('button');
    chip.className   = 'chat-suggestion-chip';
    chip.textContent = text;
    chip.addEventListener('click', () => {
      _inputEl.value    = text;
      _sendBtn.disabled = false;
      _doSend();
    });
    container.appendChild(chip);
  });
}

function _clearSuggestions() {
  const container = document.getElementById('chat-suggestions');
  if (container) container.innerHTML = '';
}

// ── STATUS WS ─────────────────────────────────────────────

export function setStatus(status) {
  const label = document.getElementById('chat-status-label');
  if (!label || !_statusDot) return;

  const map = {
    connecting: { text: 'Connexion...', cls: 'status--connecting' },
    open:       { text: 'En ligne',     cls: 'status--open'       },
    closed:     { text: 'Hors ligne',   cls: 'status--closed'     },
    failed:     { text: 'Non connecté', cls: 'status--closed'     },
  };

  const conf = map[status] ?? map.closed;
  label.textContent = conf.text;
  _statusDot.className = `chat-status-dot ${conf.cls}`;
}

// ── HELPERS ───────────────────────────────────────────────

function _scrollToBottom() {
  requestAnimationFrame(() => {
    _messagesEl.scrollTop = _messagesEl.scrollHeight;
  });
}

function _formatText(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*([^*]+)\*/g, '<strong>$1</strong>')
    .replace(/_([^_]+)_/g, '<em>$1</em>')
    .replace(/\n/g, '<br>');
}