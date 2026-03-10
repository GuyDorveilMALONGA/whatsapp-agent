/**
 * js/map.js
 * Gestion carte Leaflet — markers, popups compacts, interactions.
 * Dépend de : store.js, utils.js, constants.js
 * NE touche PAS à la sidebar, au chat, ni à l'API.
 */

import * as store from './store.js';
import { getAgeColor, getAgeClass, formatAgeShort, formatAge, buildWhatsAppUrl } from './utils.js';
import { LIGNE_NAMES, WA_NUMBER } from './constants.js';

let _map = null;
let _markers = {};
let _onBusSelect = null;

export function init(containerId, onBusSelect) {
  _onBusSelect = onBusSelect;

  _map = L.map(containerId, {
    center: [14.716, -17.467],
    zoom: 13,
    zoomControl: true,
    attributionControl: true,
  });

  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '© OpenStreetMap © CARTO',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(_map);

  // Abonnements store
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
    // Re-render markers pour refléter la sélection
    const filtered = _applyFilter(store.get('buses'), store.get('filteredLine'));
    _syncMarkers(filtered, bus?.id ?? null);
  });
}

function _applyFilter(buses, line) {
  if (!line) return buses;
  return buses.filter(b => b.ligne === line);
}

function _syncMarkers(buses, selectedId) {
  const newIds = new Set(buses.map(b => b.id));

  // Supprimer les markers obsolètes
  Object.keys(_markers).forEach(id => {
    if (!newIds.has(Number(id))) {
      _map.removeLayer(_markers[id]);
      delete _markers[id];
    }
  });

  // Ajouter / mettre à jour
  buses.forEach(bus => {
    if (_markers[bus.id]) _map.removeLayer(_markers[bus.id]);
    _markers[bus.id] = _createMarker(bus, selectedId === bus.id);
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

  marker.on('click', () => {
    if (_onBusSelect) _onBusSelect(bus.id);
  });

  return marker;
}

/**
 * Popup compact : 3 lignes max + 2 actions.
 * RÈGLE : Popup = résumé. Détails = panel.
 */
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
    // Force reflow pour relancer l'animation
    void el.offsetWidth;
    el.classList.add('pulse');
    setTimeout(() => el.classList.remove('pulse'), 3000);
  }
}

export function getMap() { return _map; }
