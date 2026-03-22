/**
 * js/push.js — V2.0
 * V2.0 :
 *  - Détection iOS standalone (Add to Home Screen requis)
 *  - Logs console détaillés pour debug en démo
 *  - subscribeToPush() appelé uniquement si l'utilisateur a des abonnements actifs
 */

import { API_BASE } from './constants.js';
import { getSessionId } from './ws.js';

// ── Détection iOS ─────────────────────────────────────────

function _isIOS() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent);
}

function _isStandalone() {
  return navigator.standalone === true
    || window.matchMedia('(display-mode: standalone)').matches;
}

export function checkIOSPushSupport() {
  if (_isIOS() && !_isStandalone()) {
    console.info('[Push] iOS détecté en mode navigateur — push non disponible');
    return false;
  }
  return true;
}

// ── Clé VAPID ─────────────────────────────────────────────

async function _getVapidPublicKey() {
  console.log('[Push] Récupération clé VAPID…');
  const res = await fetch(`${API_BASE}/api/push/vapid-public-key`);
  if (!res.ok) throw new Error(`VAPID key fetch failed: HTTP ${res.status}`);
  const { publicKey } = await res.json();
  console.log('[Push] Clé VAPID reçue ✅');
  return publicKey;
}

function _urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64  = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw     = atob(base64);
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}

// ── Subscribe ─────────────────────────────────────────────

export async function subscribeToPush() {
  console.log('[Push] subscribeToPush() START');

  try {
    // 1. Support navigateur
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      console.warn('[Push] ❌ PushManager non supporté');
      return false;
    }
    console.log('[Push] ✅ PushManager supporté');

    // 2. iOS standalone check
    if (_isIOS() && !_isStandalone()) {
      console.warn('[Push] ❌ iOS non installée — push bloqué');
      // Afficher un toast si Toast est disponible
      const event = new CustomEvent('xetu:push-ios-required');
      window.dispatchEvent(event);
      return false;
    }

    // 3. Permission
    console.log('[Push] Demande permission notification…');
    const permission = await Notification.requestPermission();
    console.log('[Push] Permission:', permission);
    if (permission !== 'granted') {
      console.info('[Push] ❌ Permission refusée');
      return false;
    }

    // 4. SW ready
    console.log('[Push] Attente SW ready…');
    const registration = await navigator.serviceWorker.ready;
    console.log('[Push] ✅ SW ready');

    // 5. Vérifier si déjà abonné
    const existing = await registration.pushManager.getSubscription();
    if (existing) {
      console.info('[Push] Déjà abonné — endpoint:', existing.endpoint.slice(-20));
      return true;
    }

    // 6. Clé VAPID
    const vapidPublicKey       = await _getVapidPublicKey();
    const applicationServerKey = _urlBase64ToUint8Array(vapidPublicKey);

    // 7. Subscribe
    console.log('[Push] Création abonnement PushManager…');
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly:      true,
      applicationServerKey,
    });
    console.log('[Push] ✅ Abonnement créé:', subscription.endpoint.slice(-20));

    // 8. Envoyer au backend
    const { endpoint, keys } = subscription.toJSON();
    const phone = getSessionId();
    console.log('[Push] Envoi au backend — phone:', phone?.slice(-8));

    const res = await fetch(`${API_BASE}/api/push/subscribe`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        phone,
        endpoint,
        keys: { p256dh: keys.p256dh, auth: keys.auth },
      }),
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Backend error ${res.status}: ${body}`);
    }

    console.info('[Push] ✅ Abonnement enregistré côté backend');
    return true;

  } catch (err) {
    console.error('[Push] ❌ Erreur subscribeToPush:', err);
    return false;
  }
}

// ── isPushSubscribed ──────────────────────────────────────

export async function isPushSubscribed() {
  try {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return false;
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    const result = !!subscription;
    console.log('[Push] isPushSubscribed:', result);
    return result;
  } catch (err) {
    console.warn('[Push] isPushSubscribed error:', err);
    return false;
  }
}

// ── Unsubscribe ───────────────────────────────────────────

export async function unsubscribeFromPush() {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) return true;

    const phone    = getSessionId();
    const endpoint = subscription.endpoint;

    await subscription.unsubscribe();
    console.log('[Push] Désabonnement navigateur OK');

    await fetch(
      `${API_BASE}/api/push/unsubscribe?phone=${encodeURIComponent(phone)}&endpoint=${encodeURIComponent(endpoint)}`,
      { method: 'DELETE' }
    );

    console.info('[Push] ✅ Désabonnement complet');
    return true;
  } catch (err) {
    console.error('[Push] ❌ Erreur unsubscribeFromPush:', err);
    return false;
  }
}
