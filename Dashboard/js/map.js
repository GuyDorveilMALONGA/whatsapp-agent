/**
 * js/map.js
 * Gestion carte Leaflet — markers, popups compacts, interactions.
 * Dépend de : store.js, utils.js, constants.js
 *
 * FIX : marker.openPopup() appelé directement au clic (ne dépend plus du store)
 */

import * as store from './store.js';
import { getAgeColor, getAgeClass, formatAgeShort, formatAge, buildWhatsAppUrl } from './utils.js';
import { LIGNE_NAMES, WA_NUMBER } from './constants.js';

let _map = null;
let _markers = {};
let _onBusSelect = null;

// Fournisseurs de tuiles par ordre de priorité
const TILE_PROVIDERS = [
  {
    url: 'https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png',
    opts: { attribution: '© Stadia Maps © OpenMapTiles © OpenStreetMap', maxZoom: 20 },
  },
  {
    url: 'https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png',
    opts: { attribution: '© OpenStreetMap France', maxZoom: 20, subdomains: 'abc' },
  },
  {
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    opts: { attribution: '© OpenStreetMap contributors', maxZoom: 19 },
  },
];

let _tileLayer = null;

function _loadTileProvider(index) {
  if (index >= TILE_PROVIDERS.length) {
    console.error('[Map] Aucun fournisseur de tuiles disponible.');
    return;
  }
  if (_tileLayer) _map.removeLayer(_tileLayer);

  const p = TILE_PROVIDERS[index];
  _tileLayer = L.tileLayer(p.url, p.opts);
  _tileLayer.on('tileerror', () => {
    console.warn(`[Map] Fournisseur ${index} échoue, essai suivant...`);
    _loadTileProvider(index + 1);
  });
  _tileLayer.addTo(_map);
}

export function init(containerId, onBusSelect) {
  _onBusSelect = onBusSelect;

  _map = L.map(containerId, {
    center: [14.716, -17.467],
    zoom: 13,
    zoomControl: true,
    attributionControl: true,
  });

  _loadTileProvider(0);

  store.subscribe('buses', (buses) => {
    const filtered = _applyFilter(buses, store.get('filteredLine'));
    _syncMarkers(filtered, store.get('selectedBus')?.id ?? null);
  });

  store.subscribe('filteredLine', (line) => {
    const filtered = _applyFilter(store.get('buses'), line);
    _syncMarkers(filtered, store.get('selectedBus')?.id ?? null);
  });

  store.subscribe('selectedBus', (bus) => {
    if (bus) flyToBus(bus);
    const filtered = _applyFilter(store.get('buses'), store.get('filteredLine'));
    _syncMarkers(filtered, bus?.id ?? null);
  });
}

function _applyFilter(buses, line) {
  if (!line) return buses;
  return buses.filter(b => b.ligne === line);
}

function _syncMarkers(buses, selectedId) {
  const newIds = new Set(buses.map(b => String(b.id)));
  Object.keys(_markers).forEach(id => {
    if (!newIds.has(String(id))) {
      _map.removeLayer(_markers[id]);
      delete _markers[id];
    }
  });
  buses.forEach(bus => {
    if (_markers[bus.id]) _map.removeLayer(_markers[bus.id]);
    _markers[bus.id] = _createMarker(bus, String(selectedId) === String(bus.id));
  });
}

function _createMarker(bus, isSelected) {
  const color = getAgeColor(bus.minutes_ago);
  const size  = isSelected ? 44 : 36;

  const icon = L.divIcon({
    className: '',
    html: `<div class="bus-marker"
      role="img"
      aria-label="Bus ${bus.ligne} à ${bus.position}, ${formatAgeShort(bus.minutes_ago)}"
      style="
        width:${size}px;height:${size}px;
        background:${color};
        box-shadow:0 0 ${isSelected ? 20 : 10}px ${color}80;
        font-size:${isSelected ? 13 : 11}px;
      ">${bus.ligne}</div>`,
    iconSize:   [size, size],
    iconAnchor: [size / 2, size / 2],
  });

  const marker = L.marker([bus.lat, bus.lng], { icon })
    .addTo(_map)
    .bindPopup(_buildPopupHtml(bus), { maxWidth: 260 });

  // FIX : ouvrir le popup directement au clic, sans passer par le store
  // Évite le bug string vs number sur bus.id qui empêchait le popup de s'ouvrir
  marker.on('click', () => {
    marker.openPopup();
    if (_onBusSelect) _onBusSelect(bus.id);
  });

  return marker;
}

function _buildPopupHtml(bus) {
  const ageShort = formatAgeShort(bus.minutes_ago);
  const ageClass = getAgeClass(bus.minutes_ago);
  const ageFull  = formatAge(bus.minutes_ago);
  const lineName = LIGNE_NAMES[bus.ligne] || `Ligne ${bus.ligne}`;

  return `
    <div class="popup-content">
      <div class="popup-header">
        <span class="popup-ligne">Bus ${bus.ligne}</span>
        <span class="popup-name">${lineName}</span>
      </div>
      <div class="popup-pos">📍 ${bus.position}</div>
      <div class="popup-meta">
        <span class="popup-age ${ageClass}" title="${ageFull}">${ageShort}</span>
        <span>· Signalé par ${bus.reporter}</span>
      </div>
      <div class="popup-actions">
        <button class="popup-btn-details" onclick="window._onPopupDetails(${bus.id})">
          Détails ▸
        </button>
        <button class="popup-btn-confirm" onclick="window._onPopupConfirm(${bus.id}, this)"
          aria-label="Confirmer la présence du bus ${bus.ligne} à ${bus.position}">
          ✅ Confirmer
        </button>
      </div>
    </div>
  `;
}

export function flyToBus(bus) {
  _map.flyTo([bus.lat, bus.lng], 15, { duration: 0.8 });
  const marker = _markers[bus.id];
  if (marker) marker.openPopup();
}

export function pulseMarker(busId) {
  const marker = _markers[busId];
  if (!marker) return;
  const el = marker.getElement()?.querySelector('.bus-marker');
  if (el) {
    el.classList.remove('pulse');
    void el.offsetWidth;
    el.classList.add('pulse');
    setTimeout(() => el.classList.remove('pulse'), 3000);
  }
}

export function getMap() { return _map; }