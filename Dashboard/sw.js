/**
 * sw.js — Xëtu PWA Service Worker V5
 * xetu-v10 : position deterministe synchronisee : fix vitesse anim + reader reset auto + DEMO_MODE=false — localStorage pour âge réel des bus démo
 */

const CACHE_VERSION = 'xetu-v10';
const CACHE_NAME    = CACHE_VERSION;

const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/css/variables.css',
  '/css/base.css',
  '/css/components.css',
  '/css/map.css',
  '/css/overlay-styles.css',
  '/js/app.js',
  '/js/home.js',
  '/js/reader.js',
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

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      cache.addAll(PRECACHE_URLS).catch((err) => {
        console.warn('[SW] Précache partiel:', err);
      })
    )
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  if (url.hostname.includes('railway.app') || url.hostname.includes('supabase.co')) return;
  if (event.request.url.startsWith('ws://') || event.request.url.startsWith('wss://')) return;
  if (url.hostname.includes('cartocdn.com') || url.hostname.includes('stadiamaps.com')) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});