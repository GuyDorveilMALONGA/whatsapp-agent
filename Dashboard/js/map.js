/**
 * XËTU — js/map.js
 * Gère exclusivement Leaflet. Aucune connaissance du reste de l'UI.
 * Markers stockés dans Map() pour des opérations O(1).
 */
const XetuMap = (() => {

  let mapInstance = null;

  // Map() plutôt qu'objet plain : add/has/delete en O(1)
  // Critique pour une flotte de 39 lignes mise à jour toutes les 30s
  const activeMarkers = new Map();

  const init = (containerId = 'map') => {
    if (mapInstance) return;

    mapInstance = L.map(containerId, {
      center: [14.7167, -17.4677],
      zoom: 13,
      zoomControl: false,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '© OpenStreetMap © CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(mapInstance);

    L.control.zoom({ position: 'bottomright' }).addTo(mapInstance);
  };

  const _createIcon = (ligne, confidenceClass) => {
    const colors = {
      good:    '#00C97A',
      warning: '#F5A623',
      danger:  '#F54040',
    };
    const bgColor  = colors[confidenceClass] || colors.danger;
    const safeText = Utils.escapeHTML(String(ligne));

    return L.divIcon({
      html: `<div style="
        background:${bgColor};
        color:white;
        font-family:'JetBrains Mono',monospace;
        font-weight:700;
        font-size:12px;
        padding:5px 10px;
        border-radius:8px;
        box-shadow:0 3px 12px rgba(0,0,0,.18);
        border:2px solid rgba(255,255,255,.5);
        white-space:nowrap;
      ">${safeText}</div>`,
      className: '',
      iconAnchor: [22, 14],
    });
  };

  const _buildPopupContent = (bus) => {
    const cls   = Utils.getConfidenceClass(bus.confiance, bus.minutes_depuis_signalement);
    const color = Utils.CONFIDENCE_COLORS[cls];
    const label = Utils.CONFIDENCE_LABELS[cls];

    // Toutes les données API passent par escapeHTML
    const safeLigne    = Utils.escapeHTML(bus.ligne);
    const safePosition = Utils.escapeHTML(bus.position_actuelle || 'Position inconnue');
    const safeAgo      = Utils.escapeHTML(Utils.timeAgo(bus.minutes_depuis_signalement));
    const safeRepart   = Utils.escapeHTML(String(bus.repart_dans || '?'));

    return `
      <div class="popup-body">
        <div class="popup-header">
          <div class="popup-bus-number">${safeLigne}</div>
          <div>
            <div class="popup-position">${safePosition}</div>
            <div class="popup-time-ago">${safeAgo}</div>
          </div>
        </div>
        <div class="popup-divider"></div>
        <div class="popup-meta-row">
          <span style="color:${color}">●</span>
          Confiance&nbsp;<strong style="color:${color}">${label}</strong>
        </div>
        ${bus.au_terminus
          ? `<div class="popup-terminus">⚑ Terminus · repart ~${safeRepart} min</div>`
          : ''}
      </div>`;
  };

  /**
   * Diff intelligent : ne recrée que les markers modifiés.
   * Supprime les bus disparus, met à jour les existants, ajoute les nouveaux.
   */
  const updateFleet = (busesData) => {
    if (!mapInstance) return;

    // 1. Supprimer les bus absents de la nouvelle réponse
    const currentIds = new Set(busesData.map(b => b.id_unique || b.ligne));
    for (const [id, marker] of activeMarkers.entries()) {
      if (!currentIds.has(id)) {
        mapInstance.removeLayer(marker);
        activeMarkers.delete(id);
      }
    }

    // 2. Mettre à jour ou créer
    busesData.forEach(bus => {
      if (!bus.lat || !bus.lon) return;

      const id      = bus.id_unique || bus.ligne;
      const cls     = Utils.getConfidenceClass(bus.confiance, bus.minutes_depuis_signalement);
      const icon    = _createIcon(bus.ligne, cls);
      const popup   = _buildPopupContent(bus);

      if (activeMarkers.has(id)) {
        activeMarkers.get(id)
          .setLatLng([bus.lat, bus.lon])
          .setIcon(icon)
          .setPopupContent(popup);
      } else {
        const marker = L.marker([bus.lat, bus.lon], { icon })
          .bindPopup(popup, { maxWidth: 240 })
          .addTo(mapInstance);
        activeMarkers.set(id, marker);
      }
    });
  };

  const focusOn = (lat, lon, zoom = 15) => {
    if (mapInstance && lat && lon) {
      mapInstance.flyTo([lat, lon], zoom, { duration: 1.2 });
    }
  };

  const openMarkerPopup = (busId) => {
    activeMarkers.get(busId)?.openPopup();
  };

  return { init, updateFleet, focusOn, openMarkerPopup };

})();
