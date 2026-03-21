/**
 * sw.js — Xëtu PWA Service Worker
 * VERSION BUMP → force la mise à jour sur les appareils qui ont installé la PWA
 * Chaque sprint : incrémenter CACHE_VERSION
 */

const CACHE_VERSION = 'xetu-v5'; // ← incrémente à chaque sprint
const CACHE_NAME    = CACHE_VERSION;

const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/css/variables.css',
  '/css/base.css',
  '/css/components.css',
  '/css/map.css',
  '/js/app.js',
  '/js/home.js',
  '/js/signal.js',
  '/js/chat.js',
  '/js/mylines.js',
  '/js/api.js',
  '/js/store.js',
  '/js/utils.js',
  '/js/ws.js',
  '/js/push.js',
  '/js/geoloc.js',
  '/js/toast.js',
  '/js/constants.js',
];

// ── Install ───────────────────────────────────────────────

self.addEventListener('install', (event) => {
  // Forcer l'activation immédiate sans attendre la fermeture des onglets
  self.skipWaiting();

  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS).catch((err) => {
        console.warn('[SW] Précache partiel:', err);
      });
    })
  );
});

// ── Activate — purger les anciens caches ──────────────────

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    ).then(() => {
      // Prendre le contrôle de tous les clients immédiatement
      return self.clients.claim();
    })
  );
});

// ── Fetch — Network first, cache fallback ─────────────────

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Ne pas intercepter les requêtes API Railway
  if (url.hostname.includes('railway.app') || url.hostname.includes('supabase.co')) {
    return;
  }
  // Ne pas intercepter les WebSocket
  if (event.request.url.startsWith('ws://') || event.request.url.startsWith('wss://')) {
    return;
  }
  // Ne pas intercepter les tuiles de carte
  if (url.hostname.includes('cartocdn.com') || url.hostname.includes('stadiamaps.com')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Mettre en cache la réponse réseau
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => {
        // Fallback cache si hors ligne
        return caches.match(event.request).then(cached => {
          if (cached) return cached;
          // Page offline par défaut
          if (event.request.mode === 'navigate') {
            return caches.match('/index.html');
          }
        });
      })
  );
});

// ── Push notifications ────────────────────────────────────

self.addEventListener('push', (event) => {
  if (!event.data) return;
  let data = {};
  try { data = event.data.json(); } catch { data = { title: 'Xëtu', body: event.data.text() }; }

  event.waitUntil(
    self.registration.showNotification(data.title || 'Xëtu', {
      body:  data.body  || 'Un bus a été signalé',
      icon:  '/assets/icons/icon-192.png',
      badge: '/assets/icons/icon-192.png',
      data:  data.url ? { url: data.url } : {},
      vibrate: [200, 100, 200],
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(windowClients => {
      for (const client of windowClients) {
        if (client.url === url && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
