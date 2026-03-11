/**
 * js/utils.js
 * Fonctions utilitaires pures — aucune dépendance externe.
 * Pas de DOM, pas d'API, pas de Leaflet ici.
 */

// ── AGE / COULEUR ─────────────────────────────────────────

export function getAgeClass(minutesAgo) {
  if (minutesAgo <= 5)  return 'age-fresh';
  if (minutesAgo <= 15) return 'age-ok';
  return 'age-old';
}

export function getAgeColor(minutesAgo) {
  if (minutesAgo <= 5)  return '#00D67F';
  if (minutesAgo <= 15) return '#FFD166';
  return '#FF4757';
}

export function formatAge(minutesAgo) {
  if (minutesAgo < 1)  return "À l'instant · Récent";
  if (minutesAgo <= 5) return `${minutesAgo} min · Récent`;
  if (minutesAgo <= 15) return `${minutesAgo} min`;
  return `${minutesAgo} min · Ancien`;
}

export function formatAgeShort(minutesAgo) {
  if (minutesAgo < 1)  return "à l'instant";
  return `il y a ${minutesAgo} min`;
}

// ── LEADERBOARD ───────────────────────────────────────────

export function getRankClass(rank) {
  if (rank === 1) return 'gold';
  if (rank === 2) return 'silver';
  if (rank === 3) return 'bronze';
  return 'other';
}

export function getRankSymbol(rank) {
  if (rank === 1) return '🥇';
  if (rank === 2) return '🥈';
  if (rank === 3) return '🥉';
  return String(rank);
}

export function getBadgeClass(index) {
  return ['badge-orange', 'badge-green', 'badge-yellow'][index % 3];
}

// ── WHATSAPP / TELEGRAM ───────────────────────────────────

export function buildWhatsAppUrl(phoneNumber, message) {
  return `https://wa.me/${phoneNumber}?text=${encodeURIComponent(message)}`;
}

export function buildTelegramUrl(botUsername, message) {
  return `https://t.me/${botUsername}?text=${encodeURIComponent(message)}`;
}

// ── safeFetch ─────────────────────────────────────────────

export async function safeFetch(url, options = {}, retries = 3) {
  for (let attempt = 0; attempt < retries; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 8000);
    try {
      const res = await fetch(url, { ...options, signal: ctrl.signal });
      clearTimeout(timer);
      if (res.status === 429) {
        const data = await res.json().catch(() => ({}));
        throw { code: 'rate_limited', message: 'Trop de requêtes', retryAfter: data.retry_after };
      }
      if (!res.ok) throw { code: `http_${res.status}`, message: `Erreur serveur (${res.status})`, status: res.status };
      // FIX : certains endpoints retournent 200 avec body vide ou non-JSON
      const text = await res.text();
      return text ? JSON.parse(text) : { status: 'ok' };
    } catch (err) {
      clearTimeout(timer);
      const isLast = attempt === retries - 1;
      if (isLast) {
        if (err.name === 'AbortError') throw { code: 'timeout', message: 'Délai dépassé. Vérifiez votre connexion.' };
        throw err.code ? err : { code: 'network', message: 'Erreur réseau. Vérifiez votre connexion.' };
      }
      await new Promise(r => setTimeout(r, 1000 * Math.pow(2, attempt)));
    }
  }
}

// ── TEXTE ─────────────────────────────────────────────────

export function normalizeText(str) {
  if (str == null) return '';
  return String(str)
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/['']/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

// ── UUID ──────────────────────────────────────────────────

export function generateUUID() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

export function formatTimestamp(isoStr) {
  const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 60000);
  if (diff < 1)   return "à l'instant";
  if (diff === 1) return 'il y a 1 min';
  if (diff < 60)  return `il y a ${diff} min`;
  return `il y a ${Math.floor(diff / 60)}h`;
}

export function buildWhatsAppSignalUrl(waNumber, ligne, arret) {
  return buildWhatsAppUrl(waNumber, `Bus ${ligne} à ${arret}`);
}