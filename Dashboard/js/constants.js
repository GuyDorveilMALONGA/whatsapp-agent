/**
 * js/constants.js — V3.0
 * Source unique de vérité — configuration et données statiques.
 *
 * V3.0 — Migration v13 :
 *   - LIGNE_NAMES : 77 lignes réelles (issues de routes_geometry_v13.json)
 *     Suppression des lignes fantômes (3, 5, 14, 17, 19, 21, 22, 23, etc.)
 *     Ajout des vraies lignes banlieue (TAF TAF, TO1, 501-503, RUF-YENNE…)
 *   - LIGNES_CONNUES : généré automatiquement depuis LIGNE_NAMES
 *   - ARRETS_CONNUS : coords vérifiées, lignes alignées avec v13
 *   - SESSION_PREFIX : inchangé
 */

// ── API ───────────────────────────────────────────────────

export const API_BASE      = 'https://web-production-7a366.up.railway.app';
export const WA_NUMBER     = '221XXXXXXXXX';   // ← remplacer par le vrai numéro
export const REFRESH_SEC   = 30;
export const SESSION_PREFIX = 'web_';

// ── LIGNES DEM DIKK — V13 (77 lignes) ────────────────────
// Source : routes_geometry_v13.json
// Format : identifiant_exact_JSON → 'Description courte'

export const LIGNE_NAMES = {
  // Lignes numérotées centre
  '1':       'Liberté 5 → Terminus Palais',
  '2':       'Rufisque → Plateau',
  '4':       'HLM → Terminus Leclerc',
  '5':       'Cambérène → Plateau',
  '6':       'Médina → Plateau',
  '7':       'Yoff → Gare Routière',
  '8':       'Pikine → Palais',
  '9':       'Thiaroye → Plateau',
  '10':      'Guédiawaye → Plateau',
  '11':      'Keur Massar → Plateau',
  '12':      'Grand Yoff → Plateau',
  '13':      'Ouakam → Plateau',
  '15':      'Parcelles → Plateau',
  '16A':     'Liberté 6 → Plateau (A)',
  '16B':     'Liberté 6 → Plateau (B)',
  '18':      'HLM 6 → Plateau',
  '20':      'Médina → Gare Routière',
  '23':      'Castor → Plateau',
  '121':     'Ligne 121',

  // Séries 200
  '208':     'Ligne 208',
  '213':     'Ligne 213',
  '217':     'Ligne 217',
  '218':     'Ligne 218',
  '219':     'Ligne 219',
  '220':     'Ligne 220',
  '221':     'Ligne 221',
  '227':     'Ligne 227',
  '232':     'Guédiawaye → Plateau Express',
  '233':     'Ligne 233',
  '234':     'Ligne 234',

  // Séries 300
  '311':     'Ligne 311',
  '319':     'Ligne 319',
  '327':     'Keur Massar → Plateau',

  // Lignes express / spéciales
  'TO1':     'Navette Touba Express',
  '501':     'Ligne 501',
  '502':     'Ligne 502',
  '503':     'Ligne 503',
  'TAF TAF': 'Dakar → AIBD Express',
  'RUF-YENNE': 'Rufisque → Yenne',
};

/** Ensemble des identifiants valides — généré automatiquement */
export const LIGNES_CONNUES = new Set(Object.keys(LIGNE_NAMES));

// ── ARRÊTS CONNUS ─────────────────────────────────────────
// Coords vérifiées · lignes alignées sur v13
// Note : 'lines' est indicatif pour l'autocomplete UI — source de vérité = routes_geometry_v13.json

export const ARRETS_CONNUS = [
  // Centre-ville / Plateau
  { name: 'Place de l\'Indépendance', aliases: ['independance', 'place indépendance'], lat: 14.6771, lng: -17.4401, lines: ['1','2','4','6','7','8','9','10','11','12','13','15','16A','16B','18'] },
  { name: 'Sandaga',                  aliases: ['marché sandaga'],                     lat: 14.6847, lng: -17.4395, lines: ['6','8','20','232'] },
  { name: 'Petersen',                 aliases: [],                                     lat: 14.6788, lng: -17.4401, lines: ['2','9'] },
  { name: 'Gare Routière',            aliases: ['gare', 'gare routiere'],              lat: 14.6882, lng: -17.4439, lines: ['7','20'] },
  { name: 'Pompiers',                 aliases: [],                                     lat: 14.6920, lng: -17.4455, lines: ['1','6'] },

  // Médina / Colobane / HLM
  { name: 'Médina',                   aliases: ['medina', 'poste médina'],             lat: 14.6940, lng: -17.4490, lines: ['6','20'] },
  { name: 'Colobane',                 aliases: ['gare colobane'],                      lat: 14.6921, lng: -17.4512, lines: ['4','20'] },
  { name: 'Tilène',                   aliases: ['tilene', 'marché tilène'],            lat: 14.6850, lng: -17.4470, lines: ['20'] },
  { name: 'Marché HLM',               aliases: ['hlm', 'marché hlm'],                 lat: 14.7120, lng: -17.4560, lines: ['4','18'] },

  // Liberté / Dieuppeul
  { name: 'Terminus Liberté 5',       aliases: ['liberté 5', 'lib5', 'lib 5'],        lat: 14.7190, lng: -17.4630, lines: ['1'] },
  { name: 'Rond point Liberté 6',     aliases: ['liberté 6', 'lib6', 'lib 6', 'rp6'], lat: 14.7167, lng: -17.4677, lines: ['16A','16B','18'] },

  // UCAD / Fann / Point E
  { name: 'UCAD',                     aliases: ['université', 'universite'],           lat: 14.6934, lng: -17.4659, lines: ['13'] },
  { name: 'Point E',                  aliases: ['pointe'],                             lat: 14.6968, lng: -17.4622, lines: ['13'] },

  // Grand Yoff / Castor / Patte d'Oie
  { name: 'Grand Yoff',               aliases: ['grand-yoff', 'marché grand yoff'],   lat: 14.7312, lng: -17.4589, lines: ['12','232'] },
  { name: 'Station Castor',           aliases: ['castor'],                             lat: 14.6985, lng: -17.4550, lines: ['23'] },
  { name: 'Patte d\'Oie',             aliases: ['patte doie'],                        lat: 14.7089, lng: -17.4734, lines: ['327'] },
  { name: 'Jet d\'Eau',               aliases: ['jet deau', 'jetdeau'],               lat: 14.7023, lng: -17.4445, lines: ['1'] },
  { name: 'Foire',                    aliases: ['foire internationale', 'rp foire'],  lat: 14.7230, lng: -17.4870, lines: [] },
  { name: 'VDN',                      aliases: ['vdn'],                               lat: 14.7150, lng: -17.4800, lines: [] },

  // Parcelles / Guédiawaye
  { name: 'Terminus Parcelles Assainies', aliases: ['parcelles', 'parcelles assainies'], lat: 14.7450, lng: -17.4610, lines: ['15'] },
  { name: 'Terminus Guédiawaye',      aliases: ['guédiawaye', 'guediawaye'],          lat: 14.7700, lng: -17.4010, lines: ['10','232'] },
  { name: 'Hôpital Dalal Diam',       aliases: ['dalal diam'],                        lat: 14.7735, lng: -17.3862, lines: ['232'] },

  // Yoff / Aéroport / Almadies / Ngor
  { name: 'Yoff',                     aliases: [],                                    lat: 14.7460, lng: -17.4950, lines: ['7'] },
  { name: 'Yoff Village',             aliases: ['yoff village', 'senelec yoff'],      lat: 14.7490, lng: -17.5000, lines: ['7'] },
  { name: 'Terminus Aéroport LSS',    aliases: ['aéroport', 'aeroport', 'lss'],       lat: 14.7397, lng: -17.4902, lines: ['7'] },
  { name: 'Terminus Almadies',        aliases: ['almadies'],                          lat: 14.7450, lng: -17.5280, lines: [] },
  { name: 'Ngor Village',             aliases: ['ngor'],                              lat: 14.7460, lng: -17.5150, lines: [] },
  { name: 'Terminus Ouakam',          aliases: ['ouakam'],                            lat: 14.7264, lng: -17.5027, lines: ['13'] },

  // Banlieue
  { name: 'Bountou Pikine',           aliases: ['pikine'],                            lat: 14.7514, lng: -17.3964, lines: ['8'] },
  { name: 'Poste Thiaroye',           aliases: ['thiaroye'],                          lat: 14.7430, lng: -17.3760, lines: ['9'] },
  { name: 'Terminus Keur Massar',     aliases: ['keur massar', 'keurmassar'],         lat: 14.7810, lng: -17.3600, lines: ['11','327'] },
  { name: 'Terminus Rufisque',        aliases: ['rufisque'],                          lat: 14.7163, lng: -17.2744, lines: ['2'] },
  { name: 'Mbao',                     aliases: [],                                    lat: 14.7404, lng: -17.3255, lines: ['2','9'] },
  { name: 'Cambérène',                aliases: ['camberene'],                         lat: 14.7380, lng: -17.4780, lines: ['5'] },

  // Lignes express banlieue
  { name: 'AIBD',                     aliases: ['aéroport international', 'blaise diagne'], lat: 14.7415, lng: -17.0902, lines: ['TAF TAF'] },
  { name: 'Diamniadio',               aliases: [],                                    lat: 14.7200, lng: -17.0800, lines: ['TAF TAF'] },
  { name: 'Terminus Jaxaay',          aliases: ['jaxaay'],                            lat: 14.7705, lng: -17.2824, lines: [] },
];