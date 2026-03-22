/**
 * sw.js — Xëtu PWA Service Worker V6
 * V6 : désactivation automatique en localhost (dev/test)
 *
 * STRATÉGIE RÉSEAU FIRST (plus de précache agressif) :
 * - Toujours essayer le réseau en premier
 * - Cache = fallback hors-ligne uniquement
 * - Plus jamais besoin d'incrémenter la version pour forcer un refresh
 */

const CACHE_NAME = 'xetu-v14';

// ── Dev guard : se désinscrire immédiatement en localhost ──
// Permet de tester sans SW qui intercepte les fichiers modifiés.
const IS_LOCAL = (
  self.location.hostname === 'localhost' ||
  self.location.hostname === '127.0.0.1' ||
  self.location.hostname === '0.0.0.0' ||
  self.location.port === '5500' ||
  self.location.port === '5501' ||
  self.location.port === '8080' ||
  self.location.port === '3000'
);

if (IS_LOCAL) {
  // S'auto-désinstaller : vider les caches + se désinscrire
  self.addEventListener('install', () => {
    self.skipWaiting();
  });
  self.addEventListener('activate', (event) => {
    event.waitUntil(
      caches.keys()
        .then((keys) => Promise.all(keys.map(k => caches.delete(k))))
        .then(() => self.registration.unregister())
        .then(() => self.clients.matchAll())
        .then((clients) => clients.forEach(c => c.navigate(c.url)))
    );
  });
  // Pas de fetch handler en local — laisser passer tout le trafic
} else {

  // ── PROD uniquement ─────────────────────────────────────

  self.addEventListener('install', (event) => {
    self.skipWaiting();
  });

  self.addEventListener('activate', (event) => {
    // Supprimer TOUS les anciens caches
    event.waitUntil(
      caches.keys()
        .then((keys) => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
        .then(() => self.clients.claim())
    );
  });

  self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Ne pas intercepter : API Railway, Supabase, WebSocket, tuiles carto
    if (url.hostname.includes('railway.app'))    return;
    if (url.hostname.includes('supabase.co'))    return;
    if (url.hostname.includes('cartocdn.com'))   return;
    if (url.hostname.includes('stadiamaps.com')) return;
    if (event.request.url.startsWith('ws://') || event.request.url.startsWith('wss://')) return;

    // Stratégie Network First : réseau → cache si hors-ligne
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // Mettre en cache uniquement les réponses valides GET
          if (response.ok && event.request.method === 'GET') {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
  });

}