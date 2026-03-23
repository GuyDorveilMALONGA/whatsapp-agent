/**
 * js/chat.js — V2.1
 * V2.1 :
 *  - Suggestions par défaut FR/Wolof, rotation aléatoire, 3 à la fois
 *  - Suggestions contextuelles après chaque réponse bot
 *  - Réapparition des suggestions quand chat est vide (état initial)
 *  - FIX bug 3 messages : welcome WS ignoré, message en HTML uniquement
 */

import * as store from './store.js';
import * as Ws    from './ws.js';

const MAX_INPUT = 500;

// ── Suggestions ───────────────────────────────────────────

const DEFAULT_SUGGESTIONS = [
  'Bus 4 est où ? · Fan la bus 4 bi nekk ?',
  'Bus 1 est où ? · Fan la bus 1 bi nekk ?',
  'Comment aller à Sandaga ?',
  'Naka laay def ba àgg Sandaga ?',
  'Arrêts du bus 4',
  'Préviens-moi pour le bus 4',
];

function _pickSuggestions(n = 3) {
  const shuffled = [...DEFAULT_SUGGESTIONS].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, n);
}

function _contextualSuggestions(botText) {
  if (!botText) return _pickSuggestions();

  const lower = botText.toLowerCase();

  // Mentionné une ligne → suggestion ciblée
  const ligneMatch = lower.match(/bus\s+(\d+[a-z]?)/);
  if (ligneMatch) {
    const ligne = ligneMatch[1];
    return [
      `Bus ${ligne} est où ?`,
      'Autres options ?',
      'Comment aller à Sandaga ?',
    ];
  }

  // Itinéraire détecté
  if (lower.includes('itinéraire') || lower.includes('correspondance') || lower.includes('changer')) {
    return [
      'Autres options ?',
      'Bus bi ngi fi ?',
      'Combien de temps ?',
    ];
  }

  // Arrêt ou horaire
  if (lower.includes('arrêt') || lower.includes('heure') || lower.includes('fréquence')) {
    return [
      'Bus bi ngi fi ?',
      'Préviens-moi pour le bus 10',
      'Comment aller à Sandaga ?',
    ];
  }

  return _pickSuggestions();
}

function _isInitialState() {
  const msgs = document.getElementById('chat-messages');
  if (!msgs) return true;
  // État initial = uniquement le message de bienvenue statique (1 enfant)
  return msgs.children.length <= 1;
}

// ── Init ──────────────────────────────────────────────────

export function initChat() {
  _attachEvents();
  _subscribeStore();
  // Afficher les suggestions par défaut au démarrage
  setSuggestions(_pickSuggestions());
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
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _doSend(); }
  });
  sendBtn.addEventListener('click', _doSend);

  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', () => {
      const msgs = document.getElementById('chat-messages');
      if (msgs) msgs.scrollTop = msgs.scrollHeight;
    });
  }
}

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

// ── Typing indicator ──────────────────────────────────────

let _typingEl = null;

export function setTyping(active) {
  active ? _showTyping() : _hideTyping();
}

function _showTyping() {
  if (_typingEl) return;
  const msgs = document.getElementById('chat-messages');
  if (!msgs) return;
  _typingEl = document.createElement('div');
  _typingEl.className = 'chat-msg chat-msg--bot';
  _typingEl.innerHTML = `<div class="chat-bubble chat-bubble--typing">
    <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
  </div>`;
  msgs.appendChild(_typingEl);
  _scrollToBottom();
}

function _hideTyping() {
  if (_typingEl) { _typingEl.remove(); _typingEl = null; }
}

// ── Suggestions ───────────────────────────────────────────

export function setSuggestions(list = []) {
  const c = document.getElementById('chat-suggestions');
  if (!c) return;
  c.innerHTML = '';
  list.forEach(text => {
    const chip = document.createElement('button');
    chip.className   = 'chat-suggestion-chip';
    chip.textContent = text;
    chip.addEventListener('click', () => {
      const input = document.getElementById('chat-input');
      if (input) input.value = text;
      document.getElementById('chat-send-btn').disabled = false;
      _doSend();
    });
    c.appendChild(chip);
  });
}

function _clearSuggestions() {
  const c = document.getElementById('chat-suggestions');
  if (c) c.innerHTML = '';
}

// ── Statut connexion ──────────────────────────────────────

export function setStatus(status) {
  const dot   = document.getElementById('chat-status-dot');
  const label = document.getElementById('chat-status-label');
  if (!dot || !label) return;
  const map = {
    open:       { cls: 'status--open',       text: 'Mi ngi ci biir' },
    connecting: { cls: 'status--connecting', text: 'Connexion…'     },
    closed:     { cls: 'status--closed',     text: 'Hors ligne'     },
    failed:     { cls: 'status--closed',     text: 'Non connecté'   },
  };
  const conf = map[status] ?? map.closed;
  dot.className     = `chat-status-dot ${conf.cls}`;
  label.textContent = conf.text;
}

// ── Store subscriptions ───────────────────────────────────

function _subscribeStore() {
  store.subscribe('lastBotMessage', (text) => {
    if (!text) return;
    _hideTyping();
    appendMessage('bot', text);
    // Suggestions contextuelles après chaque réponse bot
    setSuggestions(_contextualSuggestions(text));
  });

  store.subscribe('chatTyping', (active) => setTyping(active));

  // Suggestions du WS (onWelcome) — prioritaires sur les defaults
  store.subscribe('chatSuggestions', (list) => {
    if (list?.length) setSuggestions(list);
  });

  store.subscribe('wsStatus', (status) => {
    setStatus(status);
    // Si retour en ligne depuis état vide → réafficher les suggestions
    if (status === 'open' && _isInitialState()) {
      setSuggestions(_pickSuggestions());
    }
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
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*([^*]+)\*/g, '<strong>$1</strong>')
    .replace(/_([^_]+)_/g, '<em>$1</em>')
    .replace(/\n/g, '<br>');
}