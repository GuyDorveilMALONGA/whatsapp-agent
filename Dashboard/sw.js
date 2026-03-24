/**
 * sw.js — Xëtu PWA Service Worker
 * xetu-v6 : stratégie cache /api/buses pour mode offline démo
 */

const CACHE_VERSION = 'xetu-v25';
const CACHE_NAME    = CACHE_VERSION;
const DATA_CACHE    = 'xetu-data-v1'; // cache données API — survit aux updates SW

const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/css/variables.css',
  '/css/base.css',
  '/css/components.css',
  '/css/map.css',
  '/css/overlay-styles.css',
  '/css/signal-grid.css',
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
  '/js/reader.js',
  '/css/variables-light.css',
  '/js/theme.js',
];

// ── Install ───────────────────────────────────────────────

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS).catch((err) => {
        console.warn('[SW] Précache partiel:', err);
      });
    })
  );
});

// ── Activate — purger anciens caches SAUF xetu-data-v1 ───

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter(k => k !== CACHE_NAME && k !== DATA_CACHE)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch ─────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // ── Stratégie spéciale : API data — network first + timeout 3G, cache fallback
  // Couvre /api/buses et /api/leaderboard — données critiques pour la démo
  const isDataApi = url.pathname.includes('/api/buses') || url.pathname.includes('/api/leaderboard');
  if (isDataApi) {
    event.respondWith(
      // Timeout 5s pour 3G Dakar — évite l'attente infinie
      Promise.race([
        fetch(event.request.clone()),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 5000)),
      ])
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(DATA_CACHE).then(cache => cache.put(event.request, clone));
          }
          return response;
        })
        .catch((err) => {
          console.warn(`[SW] ${url.pathname} offline (${err.message}) — fallback cache`);
          return caches.match(event.request).then(cached => {
            if (cached) return cached;
            // Pas de cache — réponse vide valide pour éviter crash JS
            return new Response(JSON.stringify({ buses: [], leaderboard: [], stats: {}, _cached: false }), {
              headers: { 'Content-Type': 'application/json' }
            });
          });
        })
    );
    return;
  }

  // ── Ignorer les requêtes externes ────────────────────────
  if (url.hostname.includes('railway.app') || url.hostname.includes('supabase.co')) return;
  if (event.request.url.startsWith('ws://') || event.request.url.startsWith('wss://')) return;
  if (url.hostname.includes('cartocdn.com') || url.hostname.includes('stadiamaps.com')) return;
  if (url.hostname.includes('tile.openstreetmap.org')) return;

  // ── Stratégie générale : network first, cache fallback ───
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

// ── Push notifications ────────────────────────────────────

self.addEventListener('push', (event) => {
  console.log('[SW] Push reçu');
  let data = {};
  try {
    data = event.data?.json() || {};
  } catch {
    data = { body: event.data?.text() || '' };
  }
  const title   = data.title || 'Xëtu 🚌';
  const options = {
    body:    data.body || 'Un bus a été signalé sur votre ligne',
    icon:    '/assets/icons/icon-192.png',
    badge:   '/assets/icons/icon-192.png',
    tag:     data.ligne  || 'xetu-bus',
    data:    { url: data.url || '/' },
    vibrate: [200, 100, 200],
  };
  console.log('[SW] showNotification:', title, options.body);
  event.waitUntil(self.registration.showNotification(title, options));
});

// ── Notification click ────────────────────────────────────

self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification cliquée:', event.notification.tag);
  event.notification.close();
  const targetUrl = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.focus();
          return;
        }
      }
      return clients.openWindow(targetUrl);
    })
  );
});