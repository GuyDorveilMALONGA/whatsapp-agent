/**
 * js/chat.js — V1.0 App Passager
 * Écran Chat : interface plein écran avec Xëtu via WebSocket.
 * Adapté depuis chat.js V2.0 du dashboard (suppression FAB + modal).
 */

import * as store from './store.js';
import * as Ws    from './ws.js';

const MAX_INPUT = 500;

// ── Init ─────────────────────────────────────────────────

export function initChat() {
  _attachEvents();
  _subscribeStore();
}

// ── Events ────────────────────────────────────────────────

function _attachEvents() {
  const input   = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send-btn');
  if (!input || !sendBtn) return;

  input.addEventListener('input', () => {
    sendBtn.disabled = input.value.trim().length === 0;
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      _doSend();
    }
  });

  sendBtn.addEventListener('click', _doSend);

  // Scroll sur focus clavier mobile
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', () => {
      const msgs = document.getElementById('chat-messages');
      if (msgs) msgs.scrollTop = msgs.scrollHeight;
    });
  }
}

// ── Envoi message ─────────────────────────────────────────

function _doSend() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text || text.length > MAX_INPUT) return;

  appendMessage('user', text);
  input.value = '';
  document.getElementById('chat-send-btn').disabled = true;

  _clearSuggestions();
  Ws.sendChat(text);
}

// ── Messages ──────────────────────────────────────────────

export function appendMessage(role, text) {
  const msgs = document.getElementById('chat-messages');
  if (!msgs) return;

  const wrap   = document.createElement('div');
  wrap.className = `chat-msg chat-msg--${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  bubble.innerHTML = _formatText(text);

  wrap.appendChild(bubble);
  msgs.appendChild(wrap);
  _scrollToBottom();
}

// ── Typing ────────────────────────────────────────────────

let _typingEl = null;

export function setTyping(active) {
  if (active) _showTyping();
  else        _hideTyping();
}

function _showTyping() {
  if (_typingEl) return;
  const msgs = document.getElementById('chat-messages');
  if (!msgs) return;

  _typingEl = document.createElement('div');
  _typingEl.className = 'chat-msg chat-msg--bot';
  _typingEl.setAttribute('aria-label', 'Xëtu écrit…');
  _typingEl.innerHTML = `
    <div class="chat-bubble chat-bubble--typing">
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    </div>`;

  msgs.appendChild(_typingEl);
  _scrollToBottom();
}

function _hideTyping() {
  if (_typingEl) { _typingEl.remove(); _typingEl = null; }
}

// ── Suggestions ───────────────────────────────────────────

export function setSuggestions(list = []) {
  const container = document.getElementById('chat-suggestions');
  if (!container) return;
  container.innerHTML = '';

  list.forEach(text => {
    const chip = document.createElement('button');
    chip.className   = 'chat-suggestion-chip';
    chip.textContent = text;
    chip.addEventListener('click', () => {
      const input = document.getElementById('chat-input');
      if (input) { input.value = text; }
      document.getElementById('chat-send-btn').disabled = false;
      _doSend();
    });
    container.appendChild(chip);
  });
}

function _clearSuggestions() {
  const c = document.getElementById('chat-suggestions');
  if (c) c.innerHTML = '';
}

// ── Statut WS ─────────────────────────────────────────────

export function setStatus(status) {
  const dot   = document.getElementById('chat-status-dot');
  const label = document.getElementById('chat-status-label');
  if (!dot || !label) return;

  const map = {
    open:       { cls: 'status--open',       text: 'En ligne'    },
    connecting: { cls: 'status--connecting', text: 'Connexion…'  },
    closed:     { cls: 'status--closed',     text: 'Hors ligne'  },
    failed:     { cls: 'status--closed',     text: 'Non connecté'},
  };

  const conf = map[status] ?? map.closed;
  dot.className   = `chat-status-dot ${conf.cls}`;
  label.textContent = conf.text;
}

// ── Store subscriptions ───────────────────────────────────

function _subscribeStore() {
  store.subscribe('lastBotMessage', (text) => {
    if (text) {
      _hideTyping();
      appendMessage('bot', text);
    }
  });

  store.subscribe('chatTyping', (active) => {
    setTyping(active);
  });

  store.subscribe('chatWelcome', ({ text, suggestions, firstVisit }) => {
    if (firstVisit && text) appendMessage('bot', text);
    setSuggestions(suggestions);
  });

  store.subscribe('wsStatus', (status) => {
    setStatus(status);
  });
}

// ── Helpers ───────────────────────────────────────────────

function _scrollToBottom() {
  requestAnimationFrame(() => {
    const msgs = document.getElementById('chat-messages');
    if (msgs) msgs.scrollTop = msgs.scrollHeight;
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
