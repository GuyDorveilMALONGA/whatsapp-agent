/**
 * js/constants.js
 * Source unique de vérité pour les valeurs statiques.
 * Aucune dépendance externe.
 */

// ── Configuration API ─────────────────────────────────────

export const API_BASE    = 'https://web-production-ccab8.up.railway.app';
export const WA_NUMBER   = '221XXXXXXXXX';
export const REFRESH_SEC = 30;

// ── Couleurs sémantiques ──────────────────────────────────

export const COULEURS = {
  fresh:  '#00D67F',
  ok:     '#FFD166',
  old:    '#FF4757',
};

// ── Noms des lignes ───────────────────────────────────────

export const LIGNE_NAMES = {
  '1':   'Liberté 5 → Terminus Palais',
  '2':   'Rufisque → Plateau',
  '4':   'HLM → Terminus Leclerc',
  '5':   'Pikine → Plateau',
  '6':   'Thiaroye → Plateau',
  '7':   'Yoff → Gare Routière',
  '8':   'Pikine → Palais',
  '9':   'Grand Yoff → Palais',
  '10':  'Ouakam → Plateau',
  '11':  'Keur Massar → Plateau',
  '12':  'Malika → Plateau',
  '13':  'Fass → Palais',
  '15':  'Parcelles → Plateau',
  '16A': 'Guédiawaye → Plateau A',
  '16B': 'Guédiawaye → Plateau B',
  '18':  'Ngor → Plateau',
  '20':  'Almadies → Plateau',
  '23':  'Yoff → Plateau',
  '26':  'Pikine → Corniche',
  '121': 'Liberté 5 → Médina',
  '208': 'Pikine → Colobane',
  '213': 'Guédiawaye → Foire',
  '217': 'Keur Massar → Médina',
  '218': 'Malika → Médina',
  '219': 'Rufisque → Médina',
  '220': 'Thiaroye → HLM',
  '221': 'Pikine → Colobane',
  '227': 'Keur Massar → Sandaga',
  '232': 'Guédiawaye → Plateau',
  '233': 'Rufisque → Plateau',
  '234': 'Thiaroye → Plateau',
  '311': 'Keur Massar → Plateau',
  '319': 'Liberté 6 → Plateau',
  '327': 'Keur Massar → Plateau',
  'TO1': 'Terminus Leclerc → Ouakam',
  '501': 'Dakar → Thiès',
  '502': 'Dakar → Mbour',
  '503': 'Dakar → Kaolack',
  'TAF TAF': 'Centre-ville boucle',
  'RUF-YENNE': 'Rufisque → Yenne',
};

// ── Lignes valides du réseau Dem Dikk ────────────────────

export const LIGNES_CONNUES = new Set(Object.keys(LIGNE_NAMES));

// ── Arrêts connus (100+ avec aliases et lignes) ───────────

export const ARRETS_CONNUS = [
  // ── Terminus principaux ──
  { id: 'leclerc',   name: 'Terminus Leclerc',       aliases: ['leclerc', 'terminus leclerc'],                       lines: ['4', 'TO1'],          coords: [14.6641, -17.4411] },
  { id: 'palais2',   name: 'Terminus Palais 2',       aliases: ['palais 2', 'palais2', 'terminus palais'],            lines: ['1', '2', '8'],       coords: [14.6740, -17.4400] },
  { id: 'lib5',      name: 'Liberté 5',               aliases: ['liberte5', 'liberté 5', 'lib 5', 'dieuppeul'],      lines: ['15', '7', '8', '1'], coords: [14.7167, -17.4677] },
  { id: 'lib6',      name: 'Liberté 6',               aliases: ['liberte6', 'liberté 6', 'lib 6'],                   lines: ['15', '319'],         coords: [14.7200, -17.4600] },
  { id: 'aeroport',  name: 'Terminus Aéroport LSS',   aliases: ['aeroport', 'aéroport', 'lss', 'diass'],             lines: ['7'],                 coords: [14.7394, -17.4902] },
  { id: 'parcelles', name: 'Terminus Parcelles',       aliases: ['parcelles', 'parcelles assainies', 'pa'],           lines: ['15', '9'],           coords: [14.7682, -17.4477] },
  { id: 'guediawaye',name: 'Terminus Guédiawaye',      aliases: ['guediawaye', 'guédiawaye', 'gw'],                   lines: ['16A', '16B', '232'], coords: [14.7832, -17.3993] },
  { id: 'ouakam',    name: 'Terminus Ouakam',          aliases: ['ouakam'],                                            lines: ['10', 'TO1'],         coords: [14.7272, -17.4844] },
  { id: 'rufisque',  name: 'Terminus Rufisque',        aliases: ['rufisque', 'rufo'],                                  lines: ['2', '219', '233'],   coords: [14.7157, -17.2726] },
  { id: 'malika',    name: 'Terminus Malika',          aliases: ['malika'],                                            lines: ['12', '218'],         coords: [14.7803, -17.1977] },

  // ── Arrêts centre-ville ──
  { id: 'sandaga',   name: 'Sandaga',                  aliases: ['sandaga', 'marche sandaga', 'marché sandaga'],      lines: ['2', '8', '15'],      coords: [14.6847, -17.4395] },
  { id: 'ucad',      name: 'UCAD',                     aliases: ['ucad', 'université', 'fann'],                       lines: ['7', '4'],            coords: [14.6934, -17.4659] },
  { id: 'colobane',  name: 'Colobane',                  aliases: ['colobane'],                                          lines: ['4', '208', '221'],   coords: [14.6921, -17.4512] },
  { id: 'hlm',       name: 'HLM',                      aliases: ['hlm', 'h.l.m'],                                     lines: ['4', '220'],          coords: [14.6995, -17.4581] },
  { id: 'medina',    name: 'Médina',                   aliases: ['medina', 'médina'],                                  lines: ['4', '217', '218'],   coords: [14.6900, -17.4460] },
  { id: 'plateau',   name: 'Plateau',                  aliases: ['plateau', 'centre-ville'],                           lines: ['1', '2', '4', '7'],  coords: [14.6741, -17.4415] },
  { id: 'independance', name: 'Place de l\'Indépendance', aliases: ['independance', 'indépendance', 'place ind'],     lines: ['2', '7'],            coords: [14.6716, -17.4376] },
  { id: 'petersen',  name: 'Petersen',                 aliases: ['petersen'],                                          lines: ['2', '6'],            coords: [14.6788, -17.4401] },
  { id: 'tilene',    name: 'Tilène',                   aliases: ['tilene', 'tilène'],                                  lines: ['4', '8'],            coords: [14.6856, -17.4518] },
  { id: 'pompiers',  name: 'Pompiers',                 aliases: ['pompiers'],                                          lines: ['4'],                 coords: [14.6798, -17.4432] },

  // ── Arrêts nord ──
  { id: 'grand_yoff', name: 'Grand Yoff',             aliases: ['grand yoff', 'grandyoff', 'gy'],                    lines: ['9', '232'],          coords: [14.7312, -17.4589] },
  { id: 'castor',    name: 'Castor',                   aliases: ['castor'],                                            lines: ['9', '213'],          coords: [14.7156, -17.4612] },
  { id: 'jet_eau',   name: "Jet d'eau",                aliases: ["jet d'eau", 'jet deau', 'jet eau'],                 lines: ['1', '15'],           coords: [14.7023, -17.4445] },
  { id: 'foire',     name: 'Foire',                    aliases: ['foire', 'cices'],                                    lines: ['213'],               coords: [14.7195, -17.4725] },
  { id: 'vdn',       name: 'VDN',                      aliases: ['vdn', 'voie de dégagement nord'],                   lines: ['7', '213'],          coords: [14.7389, -17.4721] },
  { id: 'patte_oie', name: "Patte d'Oie",             aliases: ["patte d'oie", 'patte doie', 'pdo'],                 lines: ['327', '311'],        coords: [14.7089, -17.4734] },
  { id: 'point_e',   name: 'Point E',                  aliases: ['point e', 'pointe', 'point-e'],                     lines: ['7'],                 coords: [14.6982, -17.4679] },
  { id: 'yoff',      name: 'Yoff Village',             aliases: ['yoff', 'yoff village'],                             lines: ['7', '18', '20'],     coords: [14.7483, -17.4940] },
  { id: 'almadies',  name: 'Almadies',                 aliases: ['almadies'],                                          lines: ['20'],                coords: [14.7432, -17.5148] },
  { id: 'ngor',      name: 'Ngor',                     aliases: ['ngor'],                                              lines: ['18'],                coords: [14.7450, -17.5050] },

  // ── Arrêts banlieue ──
  { id: 'pikine',    name: 'Pikine',                   aliases: ['pikine'],                                            lines: ['5', '8', '208'],     coords: [14.7527, -17.3900] },
  { id: 'thiaroye',  name: 'Thiaroye',                 aliases: ['thiaroye'],                                          lines: ['6', '220', '234'],   coords: [14.7418, -17.3542] },
  { id: 'keur_massar', name: 'Keur Massar',            aliases: ['keur massar', 'keurmassar', 'km'],                  lines: ['11', '217', '227'],  coords: [14.7657, -17.3178] },
  { id: 'yeumbeul',  name: 'Yeumbeul',                 aliases: ['yeumbeul'],                                          lines: ['11'],                coords: [14.7721, -17.2900] },
  { id: 'mbao',      name: 'Mbao',                     aliases: ['mbao'],                                              lines: ['11', '12'],          coords: [14.7611, -17.2600] },

  // ── Autres arrêts fréquents ──
  { id: 'pompel',    name: 'Pompel',                   aliases: ['pompel'],                                            lines: ['15'],                coords: [14.7410, -17.4560] },
  { id: 'castors',   name: 'Castors',                  aliases: ['castors'],                                           lines: ['15'],                coords: [14.7340, -17.4570] },
  { id: 'hlm_grand_yoff', name: 'HLM Grand Yoff',     aliases: ['hlm grand yoff', 'hlm gy'],                         lines: ['9'],                 coords: [14.7280, -17.4560] },
  { id: 'golf_sud',  name: 'Golf Sud',                 aliases: ['golf sud', 'golf'],                                  lines: ['232'],               coords: [14.7600, -17.4200] },
  { id: 'camberene', name: 'Cambérène',                aliases: ['camberene', 'cambérène'],                           lines: ['15'],                coords: [14.7780, -17.4380] },
  { id: 'wakhinane', name: 'Wakhinane',                aliases: ['wakhinane', 'wakhinal'],                            lines: ['232'],               coords: [14.7700, -17.4000] },
  { id: 'sam_notaire', name: 'Sam Notaire',            aliases: ['sam notaire', 'samnotaire'],                        lines: ['232'],               coords: [14.7750, -17.3900] },
  { id: 'diamaguene', name: 'Diamaguène',              aliases: ['diamaguene', 'diamaguène'],                         lines: ['16A', '16B'],        coords: [14.7900, -17.3800] },
  { id: 'thiaroye_gare', name: 'Thiaroye Gare',       aliases: ['thiaroye gare', 'gare thiaroye'],                   lines: ['6', '234'],          coords: [14.7350, -17.3480] },
  { id: 'hamo4',     name: 'HAMO 4',                   aliases: ['hamo4', 'hamo 4', 'hamo'],                          lines: ['15'],                coords: [14.7720, -17.4480] },
  { id: 'nord_foire', name: 'Nord Foire',              aliases: ['nord foire', 'nordfoire'],                          lines: ['213'],               coords: [14.7280, -17.4640] },
  { id: 'liberteP',  name: 'Liberté Prolongée',        aliases: ['liberte prolongee', 'lib prolongee'],               lines: ['9'],                 coords: [14.7220, -17.4620] },
  { id: 'pikine_icotaf', name: 'Pikine Icotaf',        aliases: ['pikine icotaf', 'icotaf'],                          lines: ['8'],                 coords: [14.7500, -17.3700] },
];
