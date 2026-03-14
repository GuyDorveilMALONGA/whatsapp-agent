/**
 * sw.js — Service Worker Xëtu
 * V2.1 — Fix : filtrage des requêtes non-HTTP (chrome-extension://, etc.)
 * Stratégie :
 *   - Tiles OSM       → cache-first (longue durée)
 *   - CSS / JS / HTML → cache-first (versionnés)
 *   - /api/*          → network-first avec fallback cache
 *   - Navigation      → index.html depuis cache
 */

const CACHE_VERSION   = 'xetu-v2';
const CACHE_STATIC    = `${CACHE_VERSION}-static`;
const CACHE_TILES     = `${CACHE_VERSION}-tiles`;
const CACHE_API       = `${CACHE_VERSION}-api`;

// Fichiers à précacher au install
const PRECACHE_ASSETS = [
  '/',
  '/index.html',
  '/css/variables.css',
  '/css/base.css',
  '/css/layout.css',
  '/css/components.css',
  '/css/map.css',
  '/js/app.js',
  '/js/store.js',
  '/js/constants.js',
  '/js/utils.js',
  '/js/toast.js',
  '/js/api.js',
  '/js/map.js',
  '/js/ui.js',
  '/js/mobile.js',
  '/js/modal.js',
  '/js/ws.js',
  '/js/chat.js',
  '/assets/icons/icon-192.png',
  '/assets/icons/icon-512.png',
  // Leaflet depuis CDN — on les met aussi en cache
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js',
];

// Durée max du cache tiles (7 jours)
const TILES_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
// Max entrées dans le cache tiles
const TILES_MAX_ENTRIES = 500;

// ── INSTALL ───────────────────────────────────────────────

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_STATIC)
      .then(cache => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
      .catch(err => console.warn('[SW] Précache partiel :', err))
  );
});

// ── ACTIVATE ──────────────────────────────────────────────

self.addEventListener('activate', (event) => {
  const currentCaches = [CACHE_STATIC, CACHE_TILES, CACHE_API];
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(key => !currentCaches.includes(key))
          .map(key => {
            console.log('[SW] Purge ancien cache :', key);
            return caches.delete(key);
          })
      ))
      .then(() => self.clients.claim())
  );
});

// ── FETCH ─────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = request.url;

  // FIX V2.1 : ignorer toutes les requêtes non-HTTP/HTTPS
  // (chrome-extension://, moz-extension://, etc.)
  if (!url.startsWith('http://') && !url.startsWith('https://')) return;

  // WebSocket → jamais intercepté
  if (url.startsWith('ws://') || url.startsWith('wss://')) return;

  const parsedUrl = new URL(url);

  // Tiles OSM → cache-first (très longue durée)
  if (_isTile(parsedUrl)) {
    event.respondWith(_cachFirst_tiles(request));
    return;
  }

  // API Railway → network-first avec fallback cache
  if (_isAPI(parsedUrl)) {
    event.respondWith(_networkFirst_api(request));
    return;
  }

  // Navigation (HTML) → index.html depuis cache
  if (request.mode === 'navigate') {
    event.respondWith(_navigationHandler(request));
    return;
  }

  // Tout le reste (CSS, JS, fonts CDN) → cache-first
  event.respondWith(_cacheFirst_static(request));
});

// ── STRATÉGIES ────────────────────────────────────────────

/**
 * Cache-first pour les tiles OSM avec gestion de la taille du cache.
 */
async function _cachFirst_tiles(request) {
  const cache = await caches.open(CACHE_TILES);
  const cached = await cache.match(request);

  if (cached) {
    const dateHeader = cached.headers.get('date');
    if (dateHeader) {
      const age = Date.now() - new Date(dateHeader).getTime();
      if (age < TILES_MAX_AGE_MS) return cached;
    } else {
      return cached;
    }
  }

  try {
    const response = await fetch(request);
    if (response.ok) {
      await _trimCache(CACHE_TILES, TILES_MAX_ENTRIES);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return cached || new Response('Tile indisponible offline', { status: 503 });
  }
}

/**
 * Cache-first pour les fichiers statiques (CSS, JS, fonts).
 */
async function _cacheFirst_static(request) {
  const cache  = await caches.open(CACHE_STATIC);
  const cached = await cache.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    return new Response('Ressource indisponible offline', { status: 503 });
  }
}

/**
 * Network-first pour l'API — fallback sur cache si réseau KO.
 */
async function _networkFirst_api(request) {
  const cache = await caches.open(CACHE_API);

  try {
    const response = await Promise.race([
      fetch(request),
      _timeout(6000),
    ]);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) {
      const headers = new Headers(cached.headers);
      headers.set('X-Xetu-Cache', 'stale');
      return new Response(cached.body, { status: 200, headers });
    }
    return new Response(
      JSON.stringify({ error: 'offline', buses: [], leaderboard: [], stats: {} }),
      { status: 200, headers: { 'Content-Type': 'application/json', 'X-Xetu-Cache': 'empty' } }
    );
  }
}

/**
 * Navigation : toujours servir index.html depuis le cache.
 */
async function _navigationHandler(request) {
  const cache = await caches.open(CACHE_STATIC);

  try {
    const response = await Promise.race([
      fetch(request),
      _timeout(4000),
    ]);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await cache.match('/index.html') || await cache.match('/');
    return cached || new Response('<h1>Xëtu — Hors ligne</h1><p>Reconnecte-toi pour accéder au radar.</p>', {
      status: 200,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }
}

// ── HELPERS ───────────────────────────────────────────────

function _isTile(url) {
  return (
    url.hostname.includes('tile.openstreetmap.org') ||
    url.hostname.includes('tiles.') ||
    url.pathname.match(/\/\d+\/\d+\/\d+\.png$/)
  );
}

function _isAPI(url) {
  return (
    url.hostname.includes('railway.app') ||
    url.pathname.startsWith('/api/')
  );
}

function _timeout(ms) {
  return new Promise((_, reject) =>
    setTimeout(() => reject(new Error('SW timeout')), ms)
  );
}

async function _trimCache(cacheName, maxEntries) {
  const cache = await caches.open(cacheName);
  const keys  = await cache.keys();
  if (keys.length > maxEntries) {
    const toDelete = keys.slice(0, keys.length - maxEntries);
    await Promise.all(toDelete.map(k => cache.delete(k)));
  }
}

// ── MESSAGE (skip waiting depuis app.js) ──────────────────

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// ── PUSH NOTIFICATIONS ────────────────────────────────────

self.addEventListener('push', (event) => {
  if (!event.data) return;

  let data = {};
  try {
    data = event.data.json();
  } catch {
    data = { title: 'Xëtu', body: event.data.text() };
  }

  const title   = data.title   || 'Xëtu 🚌';
  const options = {
    body:    data.body    || 'Nouveau signalement bus',
    icon:    '/assets/icons/icon-192.png',
    badge:   '/assets/icons/icon-192.png',
    tag:     data.tag     || 'xetu-notif',
    renotify: true,
    data:    { url: data.url || '/' },
    actions: [
      { action: 'open',    title: 'Voir sur la carte' },
      { action: 'dismiss', title: 'Fermer' },
    ],
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// ── CLICK NOTIFICATION ────────────────────────────────────

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  const url = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Si l'app est déjà ouverte → focus
        for (const client of clientList) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            return client.focus();
          }
        }
        // Sinon → ouvre un nouvel onglet
        if (clients.openWindow) {
          return clients.openWindow(url);
        }
      })
  );
});