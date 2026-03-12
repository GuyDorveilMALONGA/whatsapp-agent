/**
 * js/constants.js
 * Source unique de vérité — configuration et données statiques.
 *
 * MIGRATIONS Phase 3 :
 *   - SESSION_PREFIX ajouté (utilisé par ws.js pour générer session_id)
 * FIX :
 *   - ARRETS_CONNUS : 'nom' renommé en 'name' pour correspondre à modal.js
 */

// ── API ───────────────────────────────────────────────────

export const API_BASE = 'https://web-production-7a366.up.railway.app';
export const WA_NUMBER    = '221XXXXXXXXX';   // ← remplacer par le vrai numéro
export const REFRESH_SEC  = 30;

/** Préfixe session WebSocket — doit correspondre au regex backend */
export const SESSION_PREFIX = 'web_';

// ── LIGNES DEM DIKK ───────────────────────────────────────

export const LIGNE_NAMES = {
  '1':   'Liberté 5 → Terminus Palais',
  '2':   'Rufisque → Plateau',
  '3':   'HLM → Gare Routière',
  '4':   'HLM → Terminus Leclerc',
  '5':   'Cambérène → Plateau',
  '6':   'Médina → Plateau',
  '7':   'Yoff → Gare Routière',
  '8':   'Pikine → Palais',
  '9':   'Thiaroye → Plateau',
  '10':  'Guédiawaye → Plateau',
  '11':  'Keur Massar → Plateau',
  '12':  'Grand Yoff → Plateau',
  '13':  'Ouakam → Plateau',
  '14':  'Almadies → Plateau',
  '15':  'Parcelles → Plateau',
  '16':  'Liberté 6 → Plateau',
  '17':  'Dieuppeul → Plateau',
  '18':  'HLM 6 → Plateau',
  '19':  'Fass → Plateau',
  '20':  'Médina → Gare Routière',
  '21':  'Niary Tally → Plateau',
  '22':  'Sacré-Cœur → Plateau',
  '23':  'Castor → Plateau',
  '24':  'Point E → Plateau',
  '25':  'UCAD → Plateau',
  '26':  'VDN → Plateau',
  '27':  'Patte d\'Oie → Plateau',
  '28':  'Jet d\'Eau → Plateau',
  '29':  'Pompiers → Plateau',
  '30':  'Foire → Plateau',
  '31':  'Embarcadère → Plateau',
  '32':  'Liberté 4 → Plateau',
  '33':  'Liberté 3 → Plateau',
  '34':  'Colobane → Plateau',
  '35':  'Tilène → Plateau',
  '36':  'Petersen → Plateau',
  '37':  'Sandaga → Plateau',
  '38':  'Gare Routière → Plateau',
  '232': 'Guédiawaye → Plateau',
  '327': 'Keur Massar → Plateau',
  'DDD': 'Navette Dem Dikk Express',
};

export const LIGNES_CONNUES = new Set(Object.keys(LIGNE_NAMES));

// ── ARRÊTS CONNUS ─────────────────────────────────────────
// FIX : 'nom' → 'name' pour correspondre à l'autocomplete de modal.js

export const ARRETS_CONNUS = [
  { name: 'Liberté 5',      aliases: ['lib5', 'liberte 5'],        lat: 14.7190, lng: -17.4630, lines: ['1','15','16','32','33'] },
  { name: 'Liberté 6',      aliases: ['lib6', 'liberte 6'],        lat: 14.7167, lng: -17.4677, lines: ['16','17','18'] },
  { name: 'HLM',            aliases: ['hlm grand yoff'],           lat: 14.7120, lng: -17.4560, lines: ['3','4','17','18'] },
  { name: 'Sandaga',        aliases: ['march sandaga'],            lat: 14.6847, lng: -17.4395, lines: ['37','38','6','8'] },
  { name: 'Plateau',        aliases: ['centre plateau'],           lat: 14.6771, lng: -17.4401, lines: ['1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16'] },
  { name: 'Parcelles',      aliases: ['parcelles assainies'],      lat: 14.7450, lng: -17.4610, lines: ['15','11'] },
  { name: 'Colobane',       aliases: ['col'],                      lat: 14.6921, lng: -17.4512, lines: ['34','35'] },
  { name: 'Médina',         aliases: ['medina'],                   lat: 14.6940, lng: -17.4490, lines: ['6','19','20'] },
  { name: 'Gare Routière',  aliases: ['gare', 'gare routiere'],    lat: 14.6882, lng: -17.4439, lines: ['7','20','30','31'] },
  { name: 'UCAD',           aliases: ['universite'],               lat: 14.6934, lng: -17.4659, lines: ['25','13'] },
  { name: 'Yoff',           aliases: [],                           lat: 14.7460, lng: -17.4950, lines: ['7','14'] },
  { name: 'Pikine',         aliases: ['pikine terminus'],          lat: 14.7514, lng: -17.3964, lines: ['8','9'] },
  { name: 'Thiaroye',       aliases: [],                           lat: 14.7430, lng: -17.3760, lines: ['9'] },
  { name: 'Guédiawaye',     aliases: ['guediawaye'],               lat: 14.7700, lng: -17.4010, lines: ['10','232'] },
  { name: 'Grand Yoff',     aliases: ['grand-yoff'],               lat: 14.7312, lng: -17.4589, lines: ['12','232'] },
  { name: 'Castor',         aliases: [],                           lat: 14.6985, lng: -17.4550, lines: ['23','24'] },
  { name: 'Point E',        aliases: ['pointe'],                   lat: 14.6968, lng: -17.4622, lines: ['24','25'] },
  { name: 'VDN',            aliases: ['vdn'],                      lat: 14.7150, lng: -17.4800, lines: ['26'] },
  { name: 'Patte d\'Oie',   aliases: ['patte doie'],               lat: 14.7089, lng: -17.4734, lines: ['27','327'] },
  { name: 'Jet d\'Eau',     aliases: ['jet deau', 'jetdeau'],      lat: 14.7023, lng: -17.4445, lines: ['28','1'] },
  { name: 'Pompiers',       aliases: [],                           lat: 14.7005, lng: -17.4480, lines: ['29'] },
  { name: 'Foire',          aliases: ['foire international'],      lat: 14.7230, lng: -17.4870, lines: ['30'] },
  { name: 'Embarcadère',    aliases: ['embarcadere'],              lat: 14.6730, lng: -17.4290, lines: ['31'] },
  { name: 'Petersen',       aliases: [],                           lat: 14.6788, lng: -17.4401, lines: ['36','2'] },
  { name: 'Tilène',         aliases: ['tilene'],                   lat: 14.6850, lng: -17.4470, lines: ['35'] },
  { name: 'Ouakam',         aliases: [],                           lat: 14.7264, lng: -17.5027, lines: ['13'] },
  { name: 'Almadies',       aliases: [],                           lat: 14.7450, lng: -17.5280, lines: ['14'] },
  { name: 'Niary Tally',    aliases: ['niarytally'],               lat: 14.6980, lng: -17.4520, lines: ['21'] },
  { name: 'Sacré-Cœur',     aliases: ['sacre coeur', 'sacré cœur'], lat: 14.7056, lng: -17.4644, lines: ['22'] },
  { name: 'Keur Massar',    aliases: ['keurmassar'],               lat: 14.7810, lng: -17.3600, lines: ['11','327'] },
  { name: 'Rufisque',       aliases: [],                           lat: 14.7163, lng: -17.2744, lines: ['2'] },
  { name: 'Mbao',           aliases: [],                           lat: 14.7404, lng: -17.3255, lines: ['9','2'] },
  { name: 'Aéroport',       aliases: ['aeroport', 'lss'],          lat: 14.7397, lng: -17.4902, lines: ['7','14'] },
  { name: 'Hôpital',        aliases: ['hopital', 'chu'],           lat: 14.6940, lng: -17.4580, lines: ['6','25'] },
  { name: 'Cambérène',      aliases: ['camberene'],                lat: 14.7380, lng: -17.4780, lines: ['5'] },
  { name: 'Dieuppeul',      aliases: [],                           lat: 14.7040, lng: -17.4600, lines: ['17','22'] },
  { name: 'Liberté 4',      aliases: ['lib4'],                     lat: 14.7215, lng: -17.4605, lines: ['32'] },
  { name: 'Liberté 3',      aliases: ['lib3'],                     lat: 14.7238, lng: -17.4580, lines: ['33'] },
  { name: 'HLM 6',          aliases: ['hlm6'],                     lat: 14.7085, lng: -17.4540, lines: ['18'] },
  { name: 'Fass',           aliases: [],                           lat: 14.6910, lng: -17.4430, lines: ['19'] },
];