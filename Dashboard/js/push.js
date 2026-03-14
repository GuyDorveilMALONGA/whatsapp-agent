/**
 * js/push.js — V1.0
 * Gestion des notifications push PWA Xëtu
 */

import { API_BASE } from './constants.js';
import { getSessionId } from './ws.js';

// ── Récupère la clé publique VAPID depuis le backend ──────

async function _getVapidPublicKey() {
  const res = await fetch(`${API_BASE}/api/push/vapid-public-key`);
  if (!res.ok) throw new Error('Impossible de récupérer la clé VAPID');
  const { publicKey } = await res.json();
  return publicKey;
}

// ── Convertit la clé base64 en Uint8Array ─────────────────

function _urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64  = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw     = atob(base64);
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}

// ── Abonne l'utilisateur aux notifications push ───────────

export async function subscribeToPush() {
  try {
    // Vérifie le support navigateur
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      console.warn('[Push] Non supporté sur ce navigateur');
      return false;
    }

    // Demande la permission
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      console.info('[Push] Permission refusée');
      return false;
    }

    // Récupère le Service Worker actif
    const registration = await navigator.serviceWorker.ready;

    // Récupère la clé VAPID publique
    const vapidPublicKey    = await _getVapidPublicKey();
    const applicationServerKey = _urlBase64ToUint8Array(vapidPublicKey);

    // Crée l'abonnement push
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly:      true,
      applicationServerKey,
    });

    const { endpoint, keys } = subscription.toJSON();
    const phone = getSessionId();

    // Envoie l'abonnement au backend
    const res = await fetch(`${API_BASE}/api/push/subscribe`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        phone,
        endpoint,
        keys: {
          p256dh: keys.p256dh,
          auth:   keys.auth,
        },
      }),
    });

    if (!res.ok) throw new Error('Erreur enregistrement backend');

    console.info('[Push] Abonnement enregistré ✅');
    return true;

  } catch (err) {
    console.error('[Push] Erreur subscribeToPush:', err);
    return false;
  }
}

// ── Vérifie si l'utilisateur est déjà abonné ─────────────

export async function isPushSubscribed() {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    return !!subscription;
  } catch {
    return false;
  }
}

// ── Désabonne l'utilisateur ───────────────────────────────

export async function unsubscribeFromPush() {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) return true;

    const phone    = getSessionId();
    const endpoint = subscription.endpoint;

    await subscription.unsubscribe();

    await fetch(
      `${API_BASE}/api/push/unsubscribe?phone=${encodeURIComponent(phone)}&endpoint=${encodeURIComponent(endpoint)}`,
      { method: 'DELETE' }
    );

    console.info('[Push] Désabonnement OK ✅');
    return true;
  } catch (err) {
    console.error('[Push] Erreur unsubscribeFromPush:', err);
    return false;
  }
}