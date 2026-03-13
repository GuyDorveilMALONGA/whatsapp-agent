/**
 * js/constants.js — V4.0
 * Source unique de vérité — configuration et données statiques.
 *
 * V4.0 — Corrections depuis site officiel demdikk.sn/reseau-urbain-dakar/ :
 *   - LIGNE_NAMES : terminus corrigés d'après le site officiel Dem Dikk
 *   - Ajout lignes manquantes : 5, 6, 7, 8, 9, 10, 13, 18, 20, 23
 *   - Suppressions : lignes fantômes non présentes sur le site
 *   - ARRETS_CONNUS : terminus réels alignés sur le site officiel
 *   - Numérotation officielle respectée (ex : ligne 1 = Parcelles ↔ Leclerc)
 */

// ── API ───────────────────────────────────────────────────

export const API_BASE      = 'https://web-production-7a366.up.railway.app';
export const WA_NUMBER     = '221XXXXXXXXX';   // ← remplacer par le vrai numéro
export const REFRESH_SEC   = 30;
export const SESSION_PREFIX = 'web_';

// ── LIGNES DEM DIKK — V4.0 (données officielles demdikk.sn) ──────────────────
// Format : identifiant_exact_JSON → 'Terminus A ↔ Terminus B'

export const LIGNE_NAMES = {
  // ── Lignes Urbaines ───────────────────────────────────
  '1':       'Parcelles Assainies ↔ Place Leclerc',
  '4':       'Liberté 5 (Dieuppeul) ↔ Place Leclerc',
  '7':       'Ouakam ↔ Palais 2',
  '8':       'Aéroport LSS ↔ Palais 2',
  '9':       'Liberté 6 ↔ Palais 2',
  '10':      'Liberté 5 (Dieuppeul) ↔ Palais 2',
  '13':      'Liberté 5 (Dieuppeul) ↔ Palais 2',
  '18':      'Liberté 5 (Dieuppeul) ↔ Centre-Ville',
  '20':      'Dieuppeul ↔ Centre-Ville',
  '23':      'Parcelles Assainies ↔ Palais 1',
  '121':     'Scat Urbam ↔ Leclerc',
  '319':     'Liberté 6 ↔ Ouakam',
  '501':     'Palais 2 ↔ Leclerc',
  '502':     'Gare Colobane ↔ Gare Colobane (circulaire)',
  '503':     'Gare Colobane ↔ Gare Colobane (circulaire)',
  'TO1':     'Ouakam ↔ Palais 2 (Taf Taf)',

  // ── Lignes Banlieue ───────────────────────────────────
  '2':       'Daroukhane ↔ Place Leclerc',
  '5':       'Guédiawaye ↔ Palais 1',
  '6':       'Guédiawaye ↔ Palais 1',
  '11':      'Keur Massar ↔ Lat Dior',
  '12':      'Guédiawaye ↔ Palais 1',
  '15':      'Rufisque ↔ Palais 1',
  '16A':     'Malika ↔ Palais 1',
  '16B':     'Malika ↔ Palais 1',
  '208':     'Bayakh ↔ Rufisque',
  '213':     'Rufisque ↔ Dieuppeul',
  '217':     'Thiaroye ↔ Aéroport LSS',
  '218':     'Thiaroye ↔ Aéroport LSS',
  '219':     'Daroukhane ↔ Ouakam',
  '220':     'Rufisque ↔ Guédiawaye',
  '221':     'Gadaye ↔ Almadies',
  '227':     'Keur Massar ↔ Terminus Parcelles',
  '232':     'Baux Maraichers ↔ Aéroport LSS',
  '233':     'Baux Maraichers ↔ Palais 1',
  '234':     'Jaxaay ↔ Leclerc',
  '311':     'Lac Rose ↔ Croisement Keur Massar',
  '327':     'Keur Massar ↔ Terminus Parcelles',
  'TAF TAF': 'Ouakam ↔ AIBD (Diamniadio)',
  'RUF-YENNE': 'Terminus Rufisque ↔ Yenne',
};

/** Ensemble des identifiants valides — généré automatiquement */
export const LIGNES_CONNUES = new Set(Object.keys(LIGNE_NAMES));

// ── ARRÊTS CONNUS ─────────────────────────────────────────
// Terminus et arrêts majeurs vérifiés depuis demdikk.sn
// Note : 'lines' est indicatif pour l'autocomplete UI
// Source de vérité complète = routes_geometry_v13.json (3129 arrêts)

export const ARRETS_CONNUS = [
  // ── Centre-ville / Plateau ────────────────────────────
  { name: 'Place de l\'Indépendance',   aliases: ['independance', 'place indépendance'],     lat: 14.6771, lng: -17.4401, lines: ['1','2','4','7','8','9','10','13','15','16A','16B','23','121','234','501'] },
  { name: 'Terminus Leclerc',           aliases: ['leclerc', 'place leclerc'],                lat: 14.6700, lng: -17.4368, lines: ['1','2','4','121','234','501'] },
  { name: 'Palais 1',                   aliases: ['palais', 'palais 1'],                      lat: 14.6660, lng: -17.4390, lines: ['5','6','12','15','16A','16B','23','233'] },
  { name: 'Palais 2',                   aliases: ['palais 2'],                                lat: 14.6655, lng: -17.4382, lines: ['7','8','9','10','13','501','TO1'] },
  { name: 'Sandaga',                    aliases: ['marché sandaga', 'rond point sandaga'],    lat: 14.6847, lng: -17.4395, lines: ['2','11','20'] },
  { name: 'Petersen',                   aliases: [],                                          lat: 14.6788, lng: -17.4401, lines: ['13','121'] },
  { name: 'Gare de Dakar',              aliases: ['gare dakar', 'gare ter'],                  lat: 14.6882, lng: -17.4439, lines: ['13','15','18','234'] },
  { name: 'Terminus Lat Dior',          aliases: ['lat dior'],                                lat: 14.6860, lng: -17.4410, lines: ['11'] },
  { name: 'Embarcadère',                aliases: ['embarcadere'],                             lat: 14.6718, lng: -17.4395, lines: ['1','2','4'] },

  // ── Médina / Colobane / HLM ───────────────────────────
  { name: 'Poste Médina',               aliases: ['medina', 'poste medina'],                  lat: 14.6940, lng: -17.4490, lines: ['1','2','4','7','9','11','20','23'] },
  { name: 'Difoncé',                    aliases: ['difonce'],                                 lat: 14.6920, lng: -17.4470, lines: ['1','2','4','7','23'] },
  { name: 'Colobane',                   aliases: ['gare colobane', 'rond point colobane'],    lat: 14.6921, lng: -17.4512, lines: ['2','11','15','502','503'] },
  { name: 'Gare Colobane',              aliases: ['terminus colobane'],                       lat: 14.6930, lng: -17.4518, lines: ['502','503'] },
  { name: 'Marché HLM',                 aliases: ['hlm', 'marché hlm'],                      lat: 14.7120, lng: -17.4560, lines: ['2','13','18'] },
  { name: 'Marché Tilène',              aliases: ['tilene', 'marché tilène', 'rond point sham'], lat: 14.6850, lng: -17.4470, lines: ['1','4','6','7','8','23'] },

  // ── Liberté / Dieuppeul ───────────────────────────────
  { name: 'Terminus Liberté 5 (Dieuppeul)', aliases: ['liberté 5', 'dieuppeul', 'lib5', 'terminus dieuppeul'], lat: 14.7190, lng: -17.4630, lines: ['4','10','13','18','23','213'] },
  { name: 'Rond Point Liberté 6',       aliases: ['liberté 6', 'lib6', 'rp6'],               lat: 14.7167, lng: -17.4677, lines: ['1','6','9','18','213','219','232','233','319'] },

  // ── UCAD / Fann / Point E ─────────────────────────────
  { name: 'UCAD',                       aliases: ['université', 'universite', 'ucad'],        lat: 14.6934, lng: -17.4659, lines: ['7','8','12','23','502'] },
  { name: 'Point E',                    aliases: ['pointe'],                                  lat: 14.6968, lng: -17.4622, lines: ['4','8'] },
  { name: 'Ecole Normale',              aliases: ['ecole normale', 'ens'],                    lat: 14.7010, lng: -17.4660, lines: ['1','8','12','20','23'] },

  // ── Grand Yoff / Castor / Patte d'Oie ────────────────
  { name: 'Grand Yoff',                 aliases: ['grand-yoff', 'marché grand yoff'],         lat: 14.7312, lng: -17.4589, lines: ['8','213'] },
  { name: 'Station Castor',             aliases: ['castor'],                                  lat: 14.6985, lng: -17.4550, lines: ['2','8','12','13','18','23'] },
  { name: 'Patte d\'Oie',               aliases: ['patte doie'],                             lat: 14.7089, lng: -17.4734, lines: ['5','8','12','213','217','218'] },
  { name: 'Jet d\'Eau',                 aliases: ['jet deau', 'rond point jet d\'eau'],       lat: 14.7023, lng: -17.4445, lines: ['6','9','18','20','23'] },
  { name: 'Foire',                      aliases: ['foire internationale', 'vdn foire'],       lat: 14.7230, lng: -17.4870, lines: ['217','218','232','233','TAF TAF'] },
  { name: 'VDN',                        aliases: ['vdn'],                                     lat: 14.7150, lng: -17.4800, lines: ['217','218','232','233','TAF TAF'] },
  { name: 'Scat Urbam',                 aliases: ['scat urbam', 'mairie grand yoff'],         lat: 14.7350, lng: -17.4600, lines: ['121'] },

  // ── Parcelles / Guédiawaye ────────────────────────────
  { name: 'Terminus Parcelles Assainies', aliases: ['parcelles', 'parcelles assainies'],      lat: 14.7450, lng: -17.4610, lines: ['1','23','227','327'] },
  { name: 'Terminus Guédiawaye',        aliases: ['guédiawaye', 'guediawaye'],                lat: 14.7700, lng: -17.4010, lines: ['2','5','6','12','16A','220','221','227'] },
  { name: 'Hôpital Dalal Diam',         aliases: ['dalal diam'],                              lat: 14.7735, lng: -17.3862, lines: ['5','6','219','221','227','327'] },
  { name: 'Cambérène',                  aliases: ['camberene', 'croisement camberene'],       lat: 14.7380, lng: -17.4780, lines: ['6','12','15'] },

  // ── Yoff / Aéroport / Almadies / Ngor ────────────────
  { name: 'Terminus Aéroport LSS',      aliases: ['aéroport', 'aeroport', 'lss', 'aéroport lss'], lat: 14.7397, lng: -17.4902, lines: ['8','217','218','232','233'] },
  { name: 'Yoff',                       aliases: ['yoff village'],                            lat: 14.7460, lng: -17.4950, lines: ['217','218','232','233','TAF TAF'] },
  { name: 'Terminus Almadies',          aliases: ['almadies'],                                lat: 14.7450, lng: -17.5280, lines: ['221'] },
  { name: 'Ngor Village',               aliases: ['ngor'],                                    lat: 14.7460, lng: -17.5150, lines: ['221'] },
  { name: 'Terminus Ouakam',            aliases: ['ouakam'],                                  lat: 14.7264, lng: -17.5027, lines: ['7','219','319','TO1','TAF TAF'] },

  // ── Banlieue est (Pikine / Thiaroye / Mbao) ──────────
  { name: 'Bountou Pikine',             aliases: ['pikine'],                                  lat: 14.7514, lng: -17.3964, lines: ['2','12','217','218'] },
  { name: 'Poste Thiaroye',             aliases: ['thiaroye', 'depot thiaroye'],              lat: 14.7430, lng: -17.3760, lines: ['11','15','16B','213','217','218','234'] },
  { name: 'Terminus Keur Massar',       aliases: ['keur massar', 'keurmassar'],               lat: 14.7810, lng: -17.3600, lines: ['11','227','311','327'] },
  { name: 'Station Keur Massar',        aliases: ['station keur massar'],                     lat: 14.7820, lng: -17.3580, lines: ['16B','220','234','311'] },
  { name: 'Croisement Keur Massar',     aliases: ['croisement keur massar'],                  lat: 14.7800, lng: -17.3560, lines: ['15','234','311'] },
  { name: 'Fass Mbao',                  aliases: ['fass mbao', 'mbao'],                       lat: 14.7550, lng: -17.3300, lines: ['11','15','16B','234'] },
  { name: 'Diamaguène',                 aliases: ['diamaguene'],                              lat: 14.7480, lng: -17.3490, lines: ['11','15','16B','213','234'] },

  // ── Rufisque / banlieue lointaine ─────────────────────
  { name: 'Terminus Rufisque',          aliases: ['rufisque'],                                lat: 14.7163, lng: -17.2744, lines: ['2','15','208','213','220','RUF-YENNE'] },
  { name: 'Daroukhane',                 aliases: ['daroukhane'],                              lat: 14.7780, lng: -17.3900, lines: ['2','219'] },
  { name: 'Terminus Malika',            aliases: ['malika'],                                  lat: 14.7830, lng: -17.3450, lines: ['16A','16B','220','221','227'] },
  { name: 'Terminus Gadaye',            aliases: ['gadaye', 'filaos'],                        lat: 14.7900, lng: -17.3750, lines: ['16A','221'] },
  { name: 'Terminus Jaxaay',            aliases: ['jaxaay'],                                  lat: 14.7705, lng: -17.2824, lines: ['220','234'] },

  // ── Lignes express ────────────────────────────────────
  { name: 'AIBD',                       aliases: ['aéroport international', 'blaise diagne'], lat: 14.7415, lng: -17.0902, lines: ['TAF TAF'] },
  { name: 'Diamniadio',                 aliases: ['diamniadio yenne'],                        lat: 14.7200, lng: -17.0800, lines: ['TAF TAF','RUF-YENNE'] },
  { name: 'Yenne',                      aliases: [],                                          lat: 14.6200, lng: -17.1800, lines: ['RUF-YENNE'] },
  { name: 'Lac Rose',                   aliases: ['lac rose', 'lac retba'],                   lat: 14.8350, lng: -17.2350, lines: ['311'] },

  // ── Baux Maraichers / Hann ────────────────────────────
  { name: 'Baux Maraichers',            aliases: ['baux maraichers', 'baux-maraichers'],      lat: 14.7150, lng: -17.4100, lines: ['232','233'] },
  { name: 'Hann Maristes',              aliases: ['hann', 'maristes'],                        lat: 14.7250, lng: -17.4150, lines: ['232','233'] },
];