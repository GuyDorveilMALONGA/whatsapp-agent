/**
 * js/ws.js
 * Client WebSocket Xëtu — connexion, protocole JSON, reconnexion.
 * V1.5 : PING_INTERVAL_MS 50s → 25s pour rester dans le heartbeat 120s
 *
 * PROTOCOLE :
 *   Émis   : { type: "chat", text }
 *            { type: "report", ligne, arret, observation }
 *            { type: "ping" }
 *   Reçus  : { type: "welcome", text, suggestions, first_visit }
 *            { type: "chat_response", text }
 *            { type: "typing", active }
 *            { type: "report_ack", success, id?, error? }
 *            { type: "error", message }
 *            { type: "pong" }
 *
 * API publique :
 *   Ws.init(handlers)  — démarre la connexion
 *   Ws.send(payload)   — envoie un message JSON
 *   Ws.sendChat(text)  — envoie un chat
 *   Ws.disconnect()    — ferme proprement
 *   Ws.getStatus()     — 'connecting' | 'open' | 'closed'
 *
 * Dépend de : store.js, constants.js
 * RÈGLE : ne parle jamais à map.js, ui.js, mobile.js, chat.js directement.
 *         Notifie via handlers injectés à l'init.
 */

import * as store from './store.js';
import { API_BASE, SESSION_PREFIX } from './constants.js';
import { generateUUID } from './utils.js';

// ── Constantes ────────────────────────────────────────────

const RECONNECT_BASE_MS   = 1_500;
const RECONNECT_MAX_MS    = 30_000;
const RECONNECT_FACTOR    = 1.8;
const PING_INTERVAL_MS    = 25_000; // FIX V1.5 : 50s → 25s (serveur timeout = 120s)
const MAX_RECONNECT_TRIES = 10;

// ── WS URL ────────────────────────────────────────────────
const WS_BASE = API_BASE.replace(/^https/, 'wss').replace(/^http/, 'ws');

// ── État interne ──────────────────────────────────────────

let _ws                  = null;
let _sessionId           = null;
let _handlers            = {};
let _reconnectTry        = 0;
let _reconnectTimer      = null;
let _pingTimer           = null;
let _intentionallyClosed = false;

// ── SESSION ID ────────────────────────────────────────────

function _getOrCreateSessionId() {
  if (_sessionId) return _sessionId;

  try {
    const stored = sessionStorage.getItem('xetu_session_id');
    if (stored) {
      _sessionId = stored;
    } else {
      _sessionId = `${SESSION_PREFIX}${generateUUID()}`;
      sessionStorage.setItem('xetu_session_id', _sessionId);
    }
  } catch {
    if (!_sessionId) {
      _sessionId = `${SESSION_PREFIX}${generateUUID()}`;
    }
  }

  return _sessionId;
}

// ── INIT ─────────────────────────────────────────────────

export function init(handlers = {}) {
  _handlers            = handlers;
  _intentionallyClosed = false;
  _connect();
}

// ── CONNEXION ─────────────────────────────────────────────

function _connect() {
  const sessionId = _getOrCreateSessionId();
  const url       = `${WS_BASE}/ws/${sessionId}`;

  _setStatus('connecting');

  try {
    _ws = new WebSocket(url);
  } catch (err) {
    console.error('[WS] Impossible de créer WebSocket:', err);
    _scheduleReconnect();
    return;
  }

  _ws.addEventListener('open',    _onOpen);
  _ws.addEventListener('message', _onMessage);
  _ws.addEventListener('close',   _onClose);
  _ws.addEventListener('error',   _onError);
}

// ── HANDLERS WS ───────────────────────────────────────────

function _onOpen() {
  console.info('[WS] Connecté — session:', _sessionId?.slice(0, 24));
  _reconnectTry = 0;
  _setStatus('open');
  _startPing();
  _handlers.onOpen?.(_sessionId);
}

function _onMessage(event) {
  let payload;
  try {
    payload = JSON.parse(event.data);
  } catch {
    console.warn('[WS] Message non-JSON reçu:', event.data);
    return;
  }

  _handlers.onMessage?.(payload);

  switch (payload.type) {
    case 'welcome':
      _handlers.onWelcome?.(
        payload.text        ?? '',
        payload.suggestions ?? [],
        payload.first_visit ?? false,
      );
      break;

    case 'chat_response':
      _handlers.onChatResponse?.(payload.text);
      break;

    case 'typing':
      _handlers.onTyping?.(payload.active ?? false);
      break;

    case 'report_ack':
      _handlers.onReportAck?.(payload);
      break;

    case 'error':
      _handlers.onError?.(payload.message);
      break;

    case 'pong':
      break;

    default:
      console.debug('[WS] Type non géré:', payload.type);
  }
}

function _onClose(event) {
  _stopPing();
  _setStatus('closed');
  _handlers.onClose?.(event.wasClean);

  if (_intentionallyClosed) return;

  console.info(`[WS] Connexion fermée (code=${event.code}) — reconnexion...`);
  _scheduleReconnect();
}

function _onError() {
  console.warn('[WS] Erreur WebSocket');
}

// ── RECONNEXION EXPONENTIELLE ─────────────────────────────

function _scheduleReconnect() {
  if (_reconnectTry >= MAX_RECONNECT_TRIES) {
    console.error('[WS] Trop de tentatives. Abandon.');
    _setStatus('failed');
    _handlers.onError?.('Connexion impossible. Rafraîchis la page.');
    return;
  }

  const delay = Math.min(
    RECONNECT_BASE_MS * Math.pow(RECONNECT_FACTOR, _reconnectTry),
    RECONNECT_MAX_MS,
  );

  _reconnectTry++;
  _handlers.onReconnecting?.(_reconnectTry);
  console.info(`[WS] Reconnexion #${_reconnectTry} dans ${Math.round(delay / 1000)}s`);

  if (_reconnectTimer) clearTimeout(_reconnectTimer);
  _reconnectTimer = setTimeout(_connect, delay);
}

// ── PING / PONG ───────────────────────────────────────────

function _startPing() {
  _stopPing();
  _pingTimer = setInterval(() => {
    if (_ws?.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'ping' }));
    }
  }, PING_INTERVAL_MS);
}

function _stopPing() {
  if (_pingTimer) {
    clearInterval(_pingTimer);
    _pingTimer = null;
  }
}

// ── ENVOI ─────────────────────────────────────────────────

export function send(payload) {
  if (_ws?.readyState !== WebSocket.OPEN) {
    console.warn('[WS] send() ignoré — WebSocket non ouvert');
    return false;
  }
  try {
    _ws.send(JSON.stringify(payload));
    return true;
  } catch (err) {
    console.error('[WS] Erreur send:', err);
    return false;
  }
}

export function sendChat(text) {
  return send({ type: 'chat', text });
}

export function sendReport(ligne, arret, observation = null) {
  return send({ type: 'report', ligne, arret, observation });
}

// ── DÉCONNEXION ───────────────────────────────────────────

export function disconnect() {
  _intentionallyClosed = true;
  _stopPing();
  if (_reconnectTimer) clearTimeout(_reconnectTimer);
  _ws?.close(1000, 'Client disconnect');
  _setStatus('closed');
}

// ── STATUS ────────────────────────────────────────────────

function _setStatus(status) {
  store.set('wsStatus', status);
}

export function getStatus() {
  return store.get('wsStatus') ?? 'closed';
}

export function getSessionId() {
  return _sessionId;
}