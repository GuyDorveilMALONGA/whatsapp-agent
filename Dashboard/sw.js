/**
 * sw.js — Xëtu PWA Service Worker V5
 * Fix carte noire : home.js V3.0 + app.js V2.3 + signal.js V3.1
 *
 * STRATÉGIE RÉSEAU FIRST (plus de précache agressif) :
 * - Toujours essayer le réseau en premier
 * - Cache = fallback hors-ligne uniquement
 * - Plus jamais besoin d'incrémenter la version pour forcer un refresh
 */

const CACHE_NAME = 'xetu-v12';

// Plus de PRECACHE_URLS — on ne précache plus rien au install.
// Les fichiers sont cachés dynamiquement après chaque fetch réseau réussi.
// Résultat : le navigateur voit toujours les nouveaux fichiers dès le premier chargement.

self.addEventListener('install', (event) => {
  self.skipWaiting(); // Prend le contrôle immédiatement
});

self.addEventListener('activate', (event) => {
  // Supprimer TOUS les anciens caches (xetu-v1 à xetu-v11)
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Ne pas intercepter : API Railway, Supabase, WebSocket, tuiles carto
  if (url.hostname.includes('railway.app'))   return;
  if (url.hostname.includes('supabase.co'))   return;
  if (url.hostname.includes('cartocdn.com'))  return;
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