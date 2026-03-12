<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<meta name="theme-color" content="#0A0F1E">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Xëtu">
<meta name="description" content="Xëtu — Radar Bus Dem Dikk en temps réel à Dakar">

<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/assets/icons/icon-192.png">
<link rel="icon" type="image/png" sizes="192x192" href="/assets/icons/icon-192.png">

<title>Xëtu — Radar Bus Dakar</title>

<!-- Leaflet -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>

<!-- App CSS -->
<link rel="stylesheet" href="css/variables.css">
<link rel="stylesheet" href="css/base.css">
<link rel="stylesheet" href="css/layout.css">
<link rel="stylesheet" href="css/components.css">
<link rel="stylesheet" href="css/map.css">
</head>
<body>

<!-- HEADER -->
<header id="app-header">
  <div class="logo">
    <img src="/assets/icons/icon-192.png" class="logo-icon" alt="Xëtu" width="32" height="32">
    <div>
      <div class="logo-text">Xëtu</div>
      <div class="logo-sub">Radar Bus · Dakar</div>
    </div>
  </div>
  <div class="header-right">
    <button id="btn-install" class="btn-install" aria-label="Installer l'application" hidden>
      Installer
    </button>
    <div class="live-badge" aria-label="En direct">
      <div class="live-dot" aria-hidden="true"></div>
      EN DIRECT
    </div>
    <div class="refresh-timer" id="timer" aria-label="Prochain rafraîchissement">30s</div>
  </div>
</header>

<!-- STATS BAR -->
<div class="stats-bar" role="region" aria-label="Statistiques en temps réel">
  <div class="stat-item">
    <span class="stat-icon" aria-hidden="true">🚌</span>
    <div>
      <div class="stat-val" id="stat-bus" aria-label="Bus actifs">—</div>
      <div class="stat-label">Bus actifs</div>
    </div>
  </div>
  <div class="stat-item">
    <span class="stat-icon" aria-hidden="true">📍</span>
    <div>
      <div class="stat-val" id="stat-sig" aria-label="Signalements aujourd'hui">—</div>
      <div class="stat-label">Signalements / jour</div>
    </div>
  </div>
  <div class="stat-item">
    <span class="stat-icon" aria-hidden="true">👥</span>
    <div>
      <div class="stat-val" id="stat-contrib" aria-label="Contributeurs actifs">—</div>
      <div class="stat-label">Contributeurs</div>
    </div>
  </div>
</div>

<!-- FILTRES PAR LIGNE -->
<div id="filter-bar" class="filter-bar" role="tablist" aria-label="Filtrer par ligne de bus"></div>

<!-- MAIN -->
<div class="main">

  <!-- Carte -->
  <div id="map" role="application" aria-label="Carte des bus en temps réel à Dakar"></div>

  <!-- Sidebar desktop -->
  <aside class="sidebar" aria-label="Panneau d'information">
    <div class="sidebar-tabs" role="tablist">
      <button class="tab-btn active" data-tab="buses"
        role="tab" aria-selected="true" aria-controls="tab-buses">
        Bus actifs
      </button>
      <button class="tab-btn" data-tab="leaderboard"
        role="tab" aria-selected="false" aria-controls="tab-leaderboard">
        Top signaleurs
      </button>
    </div>

    <div class="tab-content active" id="tab-buses" role="tabpanel" aria-label="Bus actifs">
      <div class="empty-state" id="buses-loading">
        <div class="empty-text">Chargement des bus...</div>
      </div>
    </div>

    <div class="tab-content" id="tab-leaderboard" role="tabpanel" aria-label="Top signaleurs">
      <div class="empty-state" id="lb-loading">
        <div class="empty-text">Chargement...</div>
      </div>
    </div>

    <div class="bottom-cta">
      <button class="btn-signaler" id="btn-signaler"
              aria-label="Signaler un bus directement">
        Signaler un bus
      </button>
    </div>
  </aside>
</div>

<!-- BOTTOM SHEET MOBILE -->
<div id="bottom-sheet" class="bottom-sheet" aria-label="Panneau mobile" role="dialog">
  <div class="sheet-handle-wrap" id="sheet-handle" aria-label="Faire glisser pour redimensionner">
    <div class="sheet-handle" aria-hidden="true"></div>
    <div class="sheet-peek-row">
      <div class="sheet-peek-label" id="sheet-summary">Chargement...</div>
      <button class="btn-signaler-peek" id="btn-signaler-mobile"
              aria-label="Signaler un bus directement">
        Signaler
      </button>
    </div>
  </div>
  <div class="sheet-tabs" role="tablist">
    <button class="sheet-tab-btn active" data-sheet-tab="buses"
      role="tab" aria-selected="true">Bus</button>
    <button class="sheet-tab-btn" data-sheet-tab="leaderboard"
      role="tab" aria-selected="false">Top</button>
  </div>
  <div class="sheet-content" id="sheet-content">
    <div class="empty-state">
      <div class="empty-text">Chargement...</div>
    </div>
  </div>
</div>

<!-- TOAST CONTAINER -->
<div id="toast-container" aria-live="polite" aria-atomic="false"></div>

<!-- SCRIPT -->
<script type="module" src="js/app.js"></script>

</body>
</html>