/**
 * js/map.js
 * Gestion de la carte Leaflet — markers, popups, interactions.
 * Dépend de : utils.js (chargé avant)
 */

const MapManager = (() => {

  let _map = null;
  let _markers = {};
  let _onBusSelect = null; // callback → app.js

  /**
   * Initialise la carte Leaflet.
   * @param {string} containerId - id de l'élément DOM
   * @param {Function} onBusSelect - callback(busId)
   */
  function init(containerId, onBusSelect) {
    _onBusSelect = onBusSelect;

    _map = L.map(containerId, {
      center: [14.716, -17.467],
      zoom: 13,
      zoomControl: true,
      attributionControl: true,
    });

    // Tuiles dark CartoDB
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '© OpenStreetMap © CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(_map);
  }

  /**
   * Crée ou met à jour les markers depuis les données bus.
   * @param {Array} buses
   * @param {number|null} selectedId
   */
  function updateMarkers(buses, selectedId) {
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
      if (_markers[bus.id]) {
        _map.removeLayer(_markers[bus.id]);
      }
      _markers[bus.id] = _createMarker(bus, selectedId === bus.id);
    });
  }

  /**
   * Crée un marker Leaflet pour un bus.
   * @param {object} bus
   * @param {boolean} isSelected
   * @returns {L.Marker}
   */
  function _createMarker(bus, isSelected) {
    const color = Utils.getAgeColor(bus.minutes_ago);
    const size  = isSelected ? 44 : 36;

    const icon = L.divIcon({
      className: '',
      html: `<div class="bus-marker" style="
        width:${size}px;
        height:${size}px;
        background:${color};
        box-shadow:0 0 ${isSelected ? 20 : 12}px ${color}80;
        font-size:${isSelected ? 13 : 11}px;
        display:flex;
        align-items:center;
        justify-content:center;
        border-radius:50%;
        font-family:'Syne',sans-serif;
        font-weight:800;
        color:white;
        border:2px solid rgba(255,255,255,0.3);
        cursor:pointer;
        transition:transform 0.2s;
      ">${bus.ligne}</div>`,
      iconSize:   [size, size],
      iconAnchor: [size / 2, size / 2],
    });

    const marker = L.marker([bus.lat, bus.lng], { icon })
      .addTo(_map)
      .bindPopup(_buildPopupHtml(bus), { maxWidth: 220 });

    marker.on('click', () => {
      if (_onBusSelect) _onBusSelect(bus.id);
    });

    return marker;
  }

  /**
   * Construit le HTML du popup d'un bus.
   * @param {object} bus
   * @returns {string}
   */
  function _buildPopupHtml(bus) {
    const age = Utils.formatAge(bus.minutes_ago);
    const waUrl = Utils.buildWhatsAppUrl(
      Config.WA_NUMBER,
      `Bus ${bus.ligne} à ${bus.position}`
    );
    return `
      <div class="popup-content">
        <div class="popup-ligne">Bus ${bus.ligne}</div>
        <div class="popup-pos">📍 ${bus.position}</div>
        <div class="popup-meta">Signalé par ${bus.reporter} · ${age}</div>
        <button class="popup-wa" onclick="window.open('${waUrl}','_blank')">
          📍 Je vois ce bus aussi
        </button>
      </div>
    `;
  }

  /**
   * Centre la carte sur un bus et ouvre son popup.
   * @param {object} bus
   */
  function flyToBus(bus) {
    _map.flyTo([bus.lat, bus.lng], 15, { duration: 0.8 });
    const marker = _markers[bus.id];
    if (marker) marker.openPopup();
  }

  /**
   * Expose la référence Leaflet si besoin.
   */
  function getMap() { return _map; }

  return { init, updateMarkers, flyToBus, getMap };

})();
